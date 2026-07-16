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

    portfolio = strategy.portfolio
    if portfolio.selection_count is not None:
        lo, hi = MAX_POSITIONS_RANGE
        if not (lo <= portfolio.selection_count <= hi):
            errors.append(f"종목 수 {portfolio.selection_count}은(는) {lo}~{hi} 범위여야 합니다")
    if portfolio.hold_period_days is not None and portfolio.hold_period_days < 1:
        errors.append("보유 기간은 1거래일 이상이어야 합니다")

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
    for label, value in (("수수료율", bt.fee_rate), ("슬리피지율", bt.slippage_rate)):
        if value is not None and not (0 <= value <= 10):
            errors.append(f"{label} {value}%은(는) 0~10% 범위여야 합니다")

    return errors
