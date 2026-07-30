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
    PortfolioSpec,
    RankingSpec,
    RiskSpec,
    StrategyCondition,
    StrategySpec,
    UniverseSpec,
)


def _decompile_technical(sig: TechnicalSignal) -> StrategyCondition:
    factor = f"technical.{sig.indicator}"
    operator: Optional[str] = None
    value: Optional[float] = None
    parameters: dict = {}

    if sig.indicator in ("ma_crossover", "ema"):
        if sig.indicator == "ema" and sig.mode in ("above", "below"):
            operator = ">" if sig.mode == "above" else "<"
            if sig.long_period is not None:
                parameters["long_period"] = float(sig.long_period)
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
    else:
        # rsi/stochastic/cci/adx/williams_r/mfi/roc/volume_spike/bollinger_bands
        operator = sig.operator
        value = sig.value
        if sig.period is not None:
            parameters["period"] = float(sig.period)

    return StrategyCondition(
        factor=factor, operator=operator, value=value, parameters=parameters,
        value_source="USER_CONFIRMED",
    )


def decompile_strategy(parsed: ParsedStrategy) -> StrategySpec:
    sectors = parsed.sector
    if sectors is None:
        sectors = []
    elif isinstance(sectors, str):
        sectors = [sectors]

    entry_conditions = [
        StrategyCondition(
            factor=f"fundamental.{f.metric}", operator=f.operator, value=f.value,
            value_source="USER_CONFIRMED",
        )
        for f in parsed.fundamental_filters
    ] + [_decompile_technical(sig) for sig in parsed.entry_signals]
    exit_conditions = [_decompile_technical(sig) for sig in parsed.exit_signals]

    ranking = []
    if parsed.ranking_metric is not None:
        ranking.append(RankingSpec(
            metric=f"ranking.{parsed.ranking_metric}",
            lookback_days=parsed.ranking_lookback_days,
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
            listing_from=parsed.listing_from,
            listing_to=parsed.listing_to,
        ),
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
        ranking=ranking,
        portfolio=PortfolioSpec(
            selection_count=parsed.max_positions,
            rebalance_frequency=(
                None if parsed.rebalancing_period == "none" else parsed.rebalancing_period
            ),
            hold_period_days=parsed.hold_period_days,
        ),
        risk_management=RiskSpec(
            stop_loss=parsed.stop_loss_pct,
            take_profit=parsed.take_profit_pct,
            trailing_stop=parsed.trailing_stop_pct,
            max_mdd_limit=parsed.max_mdd_limit_pct,
        ),
        backtest=BacktestSpec(
            period=parsed.backtest_period,
            start_date=parsed.backtest_start_date,
            end_date=parsed.backtest_end_date,
            execution_timing=parsed.execution_timing,
            initial_capital=parsed.initial_capital,
            fee_rate=parsed.fee_rate,
            slippage_rate=parsed.slippage_rate,
        ),
    )
