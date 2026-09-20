"""Parameter Validator — 임계값·파라미터의 범위/단위 검증 (Registry 계약 기반).

capability 검증을 통과해 factor가 canonical ID로 정규화된 뒤 실행된다.
"""

from __future__ import annotations

from typing import List

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry.capability_registry import MAX_POSITIONS_RANGE
from strategy_conversation.registry.indicator_registry import REGISTRY


def validate_parameters(intent: StrategyIntent) -> List[str]:
    errors: List[str] = []
    strategy = intent.strategy
    if strategy is None:
        return errors

    for role, conditions in (("진입", strategy.entry_conditions), ("청산", strategy.exit_conditions)):
        for cond in conditions:
            spec = REGISTRY.get(cond.factor)
            if spec is None or spec.supported == "UNSUPPORTED":
                continue  # capability 단계에서 이미 오류 처리됨
            if cond.value is not None and spec.value_range is not None:
                lo, hi = spec.value_range
                if not (lo <= cond.value <= hi):
                    errors.append(
                        f"{role} 조건 '{spec.display_name}' 임계값 {cond.value}이(가) "
                        f"유효 범위({lo}~{hi})를 벗어났습니다"
                    )
            for name, value in cond.parameters.items():
                pspec = spec.parameters.get(name)
                if pspec is None:
                    errors.append(f"'{spec.display_name}'에 알 수 없는 파라미터 '{name}'")
                    continue
                if value is None:
                    continue
                if pspec.minimum is not None and value < pspec.minimum:
                    errors.append(
                        f"'{spec.display_name}' 파라미터 {name}={value}은(는) 최소 {pspec.minimum} 이상이어야 합니다"
                    )
                if pspec.maximum is not None and value > pspec.maximum:
                    errors.append(
                        f"'{spec.display_name}' 파라미터 {name}={value}은(는) 최대 {pspec.maximum} 이하여야 합니다"
                    )

    for rank in strategy.ranking:
        if rank.lookback_days is not None and not (5 <= rank.lookback_days <= 500):
            errors.append(f"랭킹 산정 기간 {rank.lookback_days}거래일은 유효 범위(5~500)를 벗어났습니다")
        if rank.quantile_groups is not None and not (2 <= rank.quantile_groups <= 10):
            errors.append(f"분위 그룹 수 {rank.quantile_groups}은(는) 2~10 범위여야 합니다")
        if rank.skip_days is not None:
            limit = rank.lookback_days
            if rank.skip_days < 1 or (limit is not None and rank.skip_days >= limit):
                errors.append(
                    f"최근 제외 기간 {rank.skip_days}거래일은 산정 기간보다 짧아야 합니다"
                )
                rank.skip_days = None

    portfolio = strategy.portfolio
    if portfolio.selection_count is not None:
        lo, hi = MAX_POSITIONS_RANGE
        if not (lo <= portfolio.selection_count <= hi):
            errors.append(f"종목 수 {portfolio.selection_count}은(는) {lo}~{hi} 범위여야 합니다")
    if portfolio.selection_percent is not None and not (0 < portfolio.selection_percent <= 100):
        errors.append(f"편입 비율 {portfolio.selection_percent}%은(는) 0 초과 100 이하여야 합니다")
    if portfolio.hold_period_days is not None and portfolio.hold_period_days < 1:
        errors.append("보유 기간은 1거래일 이상이어야 합니다")
    if portfolio.weighting_lookback_days is not None \
            and not (5 <= portfolio.weighting_lookback_days <= 500):
        errors.append(
            f"변동성 산정 기간 {portfolio.weighting_lookback_days}거래일은 유효 범위(5~500)를 벗어났습니다"
        )
        portfolio.weighting_lookback_days = None
    mf = strategy.market_filter
    if mf is not None:
        if mf.ma_period is not None and not (5 <= mf.ma_period <= 500):
            errors.append(f"이동평균 기간 {mf.ma_period}일은 유효 범위(5~500)를 벗어났습니다")
            mf.ma_period = None
        if mf.volatility_period is not None and not (5 <= mf.volatility_period <= 250):
            errors.append(f"시장 변동성 산정 기간 {mf.volatility_period}일은 유효 범위(5~250)를 벗어났습니다")
            mf.volatility_period = None
        if mf.volatility_multiple is not None and not (1 < mf.volatility_multiple <= 10):
            errors.append(
                f"시장 변동성 급등 배수 {mf.volatility_multiple:g}배는 1 초과 10 이하여야 합니다")
            mf.volatility_multiple = None
        if mf.exposure_pct is not None and not (0 <= mf.exposure_pct < 100):
            errors.append(f"약세 국면 투자 비중 {mf.exposure_pct:g}%는 0 이상 100 미만이어야 합니다")
            mf.exposure_pct = None

    risk = strategy.risk_management
    for label, value in (
        ("손절", risk.stop_loss), ("익절", risk.take_profit),
        ("트레일링 스탑", risk.trailing_stop), ("MDD 한도", risk.max_mdd_limit),
    ):
        if value is not None and not (0 < value <= 100):
            errors.append(f"{label} 비율 {value}%은(는) 0 초과 100 이하여야 합니다")

    bt = strategy.backtest
    if bt.initial_capital is not None and bt.initial_capital <= 0:
        errors.append("초기 자본금은 0보다 커야 합니다")
    for label, value in (
        ("수수료율", bt.fee_rate), ("슬리피지율", bt.slippage_rate), ("거래세율", bt.sell_tax_rate),
    ):
        if value is not None and not (0 <= value <= 10):
            errors.append(f"{label} {value}%은(는) 0~10% 범위여야 합니다")

    return errors
