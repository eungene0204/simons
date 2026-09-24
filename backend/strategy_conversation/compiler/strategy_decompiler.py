"""Strategy Decompiler — ParsedStrategy(내부 DSL) → StrategySpec(LLM 초안 표현).

수정(modify) 경로에서 기존 전략을 LLM Interpreter의 draft로 주입하기 위한 역매핑.
compile_strategy의 결정론적 역함수이며, 라운드트립(decompile→compile)이 원본을
보존해야 한다(test_strategy_conversation 라운드트립 가드).

StrategySpec이 표현할 수 없는 ParsedStrategy 필드(entry_filters·description)는 여기서
다루지 않는다 — 호출부(primary.run_primary_modification)가
컴파일 후 원본에서 이월 보존하고, 그 밖의 표현 불가 신호(rsi rebound 등)는
라운드트립 가드가 이관을 거부(폴백)한다.
"""

from __future__ import annotations

from typing import Optional

from engine.nl_parser import ParsedStrategy, TechnicalSignal
from strategy_conversation.interpreter.models import (
    BacktestSpec,
    CashPoolSpec,
    EntryTranchesSpec,
    MacroFilterSpec,
    MarketFilterSpec,
    PartialTakeProfitSpec,
    PositionSizingSpec,
    PortfolioSpec,
    RankingSpec,
    RiskSpec,
    SeasonalitySpec,
    StrategyCondition,
    StrategySpec,
    TaaModelSpec,
    UniverseSpec,
    VolatilityTargetSpec,
)


def _decompile_technical(sig: TechnicalSignal) -> StrategyCondition:
    factor = f"technical.{sig.indicator}"
    operator: Optional[str] = None
    value: Optional[float] = None
    parameters: dict = {}

    if sig.indicator in ("ma_crossover", "ema"):
        if sig.mode in ("above", "below"):
            # 지속 상태(정배열·가격 vs 이동평균). 두 선짜리 상태에서 short_period를 버리면
            # 재컴파일이 '가격 vs 한 선'으로 되돌아가 수정 라운드트립이 다른 전략을 만든다.
            operator = ">" if sig.mode == "above" else "<"
        else:
            operator = "crosses_above" if sig.signal_type == "buy" else "crosses_below"
        if sig.short_period is not None:
            parameters["short_period"] = float(sig.short_period)
        if sig.long_period is not None:
            parameters["long_period"] = float(sig.long_period)
    elif sig.indicator == "macd":
        operator = "crosses_above" if sig.signal_type == "buy" else "crosses_below"
    elif sig.indicator == "breakout":
        operator = "crosses_above"
        if sig.lookback_period is not None:
            parameters["lookback_period"] = float(sig.lookback_period)
    elif sig.indicator in ("ai_model", "ai_drop_model"):
        operator = ">="
        if sig.threshold is not None:
            parameters["threshold"] = float(sig.threshold)
    elif sig.indicator == "trading_value":
        operator = sig.operator
        value = sig.value
    elif sig.indicator == "bollinger_bands":
        # 볼린저는 방향을 operator가 아니라 signal_type으로 표현한다(엔진: buy=하단 터치,
        # sell=상단 터치, signals.py). 그대로 operator=None으로 되짚으면 진입/청산이 둘 다
        # "값 없는 같은 팩터"가 되어 StrategySpec의 미러 청산 가드가 청산을 삼키고,
        # 라운드트립 불일치로 **모든 수정 요청**이 인터프리터에 닿기도 전에 폴백한다
        # (2026-07-31 사고: 볼린저 상/하단 전략에서 "코스닥으로 유니버스 변경"이 해석 실패).
        # 그 가드의 예외 조항이 요구하는 방향 표기를 여기서 결정론적으로 복원한다.
        operator = "crosses_below" if sig.signal_type == "buy" else "crosses_above"
        if sig.period is not None:
            parameters["period"] = float(sig.period)
    else:
        # rsi/stochastic/cci/adx/williams_r/mfi/roc/volume_spike/bollinger_bands
        operator = sig.operator
        value = sig.value
        if sig.period is not None:
            parameters["period"] = float(sig.period)

    if sig.timeframe in ("weekly", "monthly"):
        parameters["timeframe"] = sig.timeframe          # 다중 타임프레임(v16.29) 왕복
    return StrategyCondition(
        factor=factor, operator=operator, value=value, parameters=parameters,
        value_source="USER_CONFIRMED",
    )



def _canonical_ranking_id(engine_metric: str) -> str:
    """엔진 랭킹 키 → 온톨로지 정본 id. 'return'/'volatility'는 가격 산출 랭킹(ranking.*),
    나머지는 재무 팩터(fundamental.*). 컴파일러 engine_binding의 역방향."""
    if engine_metric in ("return", "volatility", "residual_reversal", "pead"):
        return f"ranking.{engine_metric}"
    return f"fundamental.{engine_metric}"

def decompile_strategy(parsed: ParsedStrategy) -> StrategySpec:
    sectors = parsed.sector
    if sectors is None:
        sectors = []
    elif isinstance(sectors, str):
        sectors = [sectors]

    entry_conditions = [
        StrategyCondition(
            factor=f"fundamental.{f.metric}", operator=f.operator, value=f.value,
            # 거래대금 평균 기간(v16.14)도 왕복한다 — 빠지면 수정 턴마다 20일로 되돌아간다.
            parameters={"period": float(f.period)} if f.period is not None else {},
            value_source="USER_CONFIRMED",
        )
        for f in parsed.fundamental_filters
    ] + [_decompile_technical(sig) for sig in parsed.entry_signals]
    # 조건부 납입액 규칙(v16.21)은 금액 꼬리표가 붙은 진입 조건으로 되돌린다(컴파일러의 역방향) —
    # 빠지면 수정 턴마다 규칙이 사라진다.
    for rule in parsed.contribution_rules:
        cond = _decompile_technical(rule.signal)
        cond.buy_amount, cond.buy_amount_mode = rule.amount, rule.mode
        entry_conditions.append(cond)
    exit_conditions = [_decompile_technical(sig) for sig in parsed.exit_signals]

    ranking = []
    if parsed.ranking_metric == "composite" and parsed.ranking_components:
        # 복합 순위 합산(FR-BT-063) — 구성 지표 하나가 RankingSpec 하나(컴파일러의 역방향:
        # 항목 2개 이상 = 합산). 분위 그룹은 첫 항목에 싣는다(컴파일러가 첫 non-null을 취함).
        # 기간 없는 가격 지표는 전략 공통 ranking_lookback_days를 이어받는다(엔진과 동일 계약).
        for i, comp in enumerate(parsed.ranking_components):
            ranking.append(RankingSpec(
                metric=_canonical_ranking_id(comp.metric),
                lookback_days=(
                    (comp.lookback_days or parsed.ranking_lookback_days)
                    if comp.metric in ("return", "volatility") else None
                ),
                direction=comp.direction,
                quantile_groups=parsed.ranking_quantile_groups if i == 0 else None,
                # 12-1 모멘텀·묶음 점수(v16.14)도 왕복한다.
                skip_days=comp.skip_days,
                group=comp.group,
                weight=comp.weight,
            ))
    elif parsed.ranking_metric is not None:
        # 'return'/'volatility'=가격 산출 랭킹(ranking.*), 그 외=재무 팩터 랭킹(fundamental.*)
        # — 컴파일러 _build_parsed의 역방향. 방향 미저장(None)=top(기본).
        ranking.append(RankingSpec(
            metric=_canonical_ranking_id(parsed.ranking_metric),
            lookback_days=parsed.ranking_lookback_days,
            direction=parsed.ranking_direction or "top",
            # 분위 그룹도 왕복한다 — 누락되면 수정 턴에서 그룹 비교가 조용히 풀린다.
            quantile_groups=parsed.ranking_quantile_groups,
            skip_days=parsed.ranking_skip_days,
            accumulation_days=parsed.ranking_accumulation_days,
            # 발표 자격 창도 왕복한다 — 누락되면 수정 턴에서 편입 지연·제외가 조용히 풀린다.
            entry_delay_days=parsed.ranking_entry_delay_days,
            expiry_days=parsed.ranking_expiry_days,
        ))

    return StrategySpec(
        universe=UniverseSpec(
            markets=list(parsed.universe),
            sectors=sectors,
            # 지정 종목은 코드로 왕복한다 — 수정 요청 초안에서 소실되면 지정이 풀린다.
            symbols=list(parsed.target_symbols),
            # ETF 테마도 왕복한다 — 누락되면 etf_theme 있는 전략의 모든 수정이
            # 라운드트립 불일치(표현 불가)로 레거시 레인에 떨어진다(2026-07-27
            # '삼성전자 투자 etf' 사고: 인터프리터가 입력을 읽기도 전에 폴백).
            etf_theme=parsed.etf_theme,
            # 테마 유니버스 출처도 왕복한다 — 초안의 symbols는 해석이 끝난 종목코드라
            # 그것만으로는 "이 종목들이 어느 테마에서 왔는지"를 알 수 없다. 이 표기가
            # 있어야 수정 인터프리터가 테마 교체를 /universe/theme 패치로 표현한다.
            theme=parsed.theme_universe,
            # 신규 상장 제한도 왕복한다 — 누락되면 수정 요청마다 유니버스 제한이 풀리고,
            # 기준 일수를 되묻는 중이면 그 개념 자체가 다음 턴에 증발한다.
            new_listing_only=parsed.new_listing_only,
            market_cap_top_n=parsed.universe_market_cap_top_n,
            # 업종 제외도 왕복한다 — 누락되면 수정 턴마다 제외가 풀린다.
            exclude_sectors=list(parsed.exclude_sectors or []),
            liquidity_exclude_bottom_percent=parsed.universe_liquidity_exclude_bottom_pct,
            liquidity_lookback_days=parsed.universe_liquidity_lookback_days,
            # 사전 필터 확장(v16.32)도 왕복한다 — 누락되면 수정 턴마다 필터가 풀린다.
            market_cap_exclude_bottom_percent=parsed.universe_market_cap_exclude_bottom_pct,
            exclude_loss_making=parsed.universe_exclude_loss_making,
            listing_from=parsed.listing_from,
            listing_to=parsed.listing_to,
        ),
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
        entry_logic=parsed.entry_logic,
        ranking=ranking,
        portfolio=PortfolioSpec(
            # 분위 그룹 모드(FR-BT-060b)의 종목 수 자리는 그룹당 상한이다 — max_positions
            # (물질화 기본값 10)를 쓰면 재컴파일이 cap=10을 만들어 라운드트립이 깨진다
            # (모든 분위 전략의 수정이 레거시 레인으로 폴백).
            selection_count=(
                parsed.ranking_group_cap
                if parsed.ranking_quantile_groups
                else parsed.max_positions
            ),
            # 비율 선정도 왕복한다 — 누락되면 수정 턴에서 비율 편입이 개수(10)로 둔갑한다.
            selection_percent=parsed.max_positions_pct,
            rebalance_frequency=(
                None if parsed.rebalancing_period == "none" else parsed.rebalancing_period
            ),
            # 방식도 왕복시킨다 — 누락되면 수정 턴마다 비중 유지 전략이 종목 교체로
            # 되돌아간다(사용자가 말한 값이 조용히 사라지는 경로).
            rebalance_method=(
                None if parsed.rebalance_method == "reconstitute" else parsed.rebalance_method
            ),
            hold_period_days=parsed.hold_period_days,
            # 비중 방식(v16.14) — 동일 비중(기본)은 비워 두어 기존 초안과 같게 둔다.
            weighting=(
                parsed.allocation_type if parsed.allocation_type != "equal" else None
            ),
            weighting_lookback_days=parsed.allocation_lookback_days,
            max_weight_percent=parsed.max_position_weight_pct,
            max_sector_weight_percent=parsed.max_sector_weight_pct,
            # 경쟁 격차 1차(v16.28)도 왕복한다 — 누락되면 수정 턴마다 설정이 풀린다.
            target_weights=dict(parsed.target_weights) if parsed.target_weights else None,
            rebalance_band_percent=parsed.rebalance_threshold_pct,
            min_hold_period_days=parsed.min_holding_days,
            cash_asset=parsed.cash_asset,
            absolute_momentum_threshold_percent=parsed.absolute_momentum_threshold_pct,
        ),
        market_filter=(
            MarketFilterSpec(
                index=parsed.market_regime.index,
                triggers=parsed.market_regime.triggers,
                ma_period=parsed.market_regime.ma_period,
                volatility_period=parsed.market_regime.volatility_period,
                volatility_multiple=parsed.market_regime.volatility_multiple,
                exposure_pct=parsed.market_regime.exposure_pct,
            )
            if parsed.market_regime is not None else None
        ),
        # 계절 필터·목표 변동성(v16.25)도 왕복한다 — 누락되면 수정 턴마다 설정이 풀린다.
        seasonality=(SeasonalitySpec(invest_months=list(parsed.seasonal_months))
                     if parsed.seasonal_months else None),
        volatility_target=(VolatilityTargetSpec(target_percent=parsed.volatility_target.target_pct)
                           if parsed.volatility_target is not None else None),
        macro_filters=[
            MacroFilterSpec(series=m.series, mode=m.mode, operator=m.operator, value=m.value,
                            period=m.period, exposure_pct=m.exposure_pct)
            for m in parsed.macro_filters
        ],
        taa=(TaaModelSpec(model=parsed.taa.model, offensive=list(parsed.taa.offensive),
                          defensive=list(parsed.taa.defensive), canary=list(parsed.taa.canary),
                          top_n=parsed.taa.top_n)
             if parsed.taa is not None else None),
        risk_management=RiskSpec(
            stop_loss=parsed.stop_loss_pct,
            take_profit=parsed.take_profit_pct,
            trailing_stop=parsed.trailing_stop_pct,
            max_mdd_limit=parsed.max_mdd_limit_pct,
            stop_cooldown_days=parsed.stop_cooldown_days,
            trailing_stop_activation=parsed.trailing_stop_activation_pct,
            partial_take_profits=[
                PartialTakeProfitSpec(profit_percent=p.profit_pct, sell_percent=p.sell_pct)
                for p in parsed.partial_take_profits
            ],
            position_sizing=(PositionSizingSpec(
                method=parsed.position_sizing.method,
                risk_per_trade_percent=parsed.position_sizing.risk_per_trade_pct,
                atr_period=parsed.position_sizing.atr_period,
                atr_multiple=parsed.position_sizing.atr_multiple,
                kelly_fraction=parsed.position_sizing.kelly_fraction,
            ) if parsed.position_sizing is not None else None),
        ),
        backtest=BacktestSpec(
            period=parsed.backtest_period,
            start_date=parsed.backtest_start_date,
            end_date=parsed.backtest_end_date,
            execution_timing=parsed.execution_timing,
            initial_capital=parsed.initial_capital,
            fee_rate=parsed.fee_rate,
            slippage_rate=parsed.slippage_rate,
            sell_tax_rate=parsed.sell_tax_rate,
            contribution_amount=parsed.contribution_amount,
            contribution_period=parsed.contribution_period,
            withdrawal_amount=parsed.withdrawal_amount,
            withdrawal_period=parsed.withdrawal_period,
            benchmark=parsed.benchmark,
            entry_limit_percent=parsed.entry_limit_pct,
            exit_limit_percent=parsed.exit_limit_pct,
            entry_tranches=(EntryTranchesSpec(count=parsed.entry_tranches.count,
                                              step_percent=parsed.entry_tranches.step_pct)
                            if parsed.entry_tranches is not None else None),
            slippage_model=parsed.slippage_model,
            slippage_impact_coeff=parsed.slippage_impact_coeff,
            cash_pool=CashPoolSpec(
                reserve_pct=parsed.cash_pool.reserve_pct, reserve_amount=parsed.cash_pool.reserve_amount,
                reserve_stated=parsed.cash_pool.reserve_stated, max_buy_pct=parsed.cash_pool.max_buy_pct,
            ) if parsed.cash_pool is not None else None,
        ),
    )
