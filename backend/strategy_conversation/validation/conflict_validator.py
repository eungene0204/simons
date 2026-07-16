"""Logical Conflict Validator — 모순 조건 탐지.

충돌이 발견되면 임의로 수정하지 않고 오류/경고로 사용자에게 알린다.
같은 역할(진입/청산) 안의 수치 조건들은 AND 결합으로 본다(엔진 의미론과 동일).
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from strategy_conversation.interpreter.models import StrategyCondition, StrategyIntent
from strategy_conversation.registry.capability_registry import REBALANCE_FREQUENCY_DAYS
from strategy_conversation.registry.indicator_registry import REGISTRY


def _interval_for(op: str, value: float) -> Tuple[float, float]:
    """비교 조건을 [lo, hi] 폐구간 근사로 변환한다(공집합 판정용)."""
    if op in ("<", "<="):
        return (-math.inf, value)
    return (value, math.inf)


def _check_and_intersection(role: str, conditions: List[StrategyCondition], errors: List[str]) -> None:
    by_factor: Dict[str, List[StrategyCondition]] = {}
    for cond in conditions:
        if cond.operator in ("<", "<=", ">", ">=") and cond.value is not None:
            by_factor.setdefault(cond.factor, []).append(cond)
    for factor, conds in by_factor.items():
        if len(conds) < 2:
            continue
        lo, hi = -math.inf, math.inf
        for cond in conds:
            c_lo, c_hi = _interval_for(cond.operator, cond.value)
            lo, hi = max(lo, c_lo), min(hi, c_hi)
        if lo > hi:
            spec = REGISTRY.get(factor)
            name = spec.display_name if spec else factor
            described = " AND ".join(f"{name} {c.operator} {c.value}" for c in conds)
            errors.append(f"{role} 조건이 서로 모순되어 만족하는 종목이 없습니다: {described}")


def validate_conflicts(intent: StrategyIntent) -> Tuple[List[str], List[str]]:
    """(errors, warnings)를 반환한다."""
    errors: List[str] = []
    warnings: List[str] = []
    strategy = intent.strategy
    if strategy is None:
        return errors, warnings

    _check_and_intersection("진입", strategy.entry_conditions, errors)
    _check_and_intersection("청산", strategy.exit_conditions, errors)

    # 크로스오버 단기/장기 파라미터 순서
    for cond in strategy.entry_conditions + strategy.exit_conditions:
        short = cond.parameters.get("short_period")
        long = cond.parameters.get("long_period")
        if short is not None and long is not None and short >= long:
            errors.append(
                f"'{cond.factor}'의 단기 기간({short:g})이 장기 기간({long:g}) 이상입니다 — "
                "단기 < 장기여야 합니다"
            )

    # 보유 기간 vs 리밸런싱 주기
    portfolio = strategy.portfolio
    freq_days = REBALANCE_FREQUENCY_DAYS.get(portfolio.rebalance_frequency or "")
    if freq_days and portfolio.hold_period_days is not None \
            and portfolio.hold_period_days < freq_days:
        warnings.append(
            f"보유 기간({portfolio.hold_period_days}거래일)이 리밸런싱 주기(약 {freq_days}거래일)보다 "
            "짧아 리밸런싱 전에 모든 포지션이 청산됩니다 — 의도한 설정인지 확인하세요"
        )

    # 진입과 청산이 완전히 동일한 방향 조건이면 즉시 청산 루프가 된다
    entry_keys = {
        (c.factor, c.operator, c.value)
        for c in strategy.entry_conditions if c.operator and c.value is not None
    }
    for cond in strategy.exit_conditions:
        if cond.operator and cond.value is not None \
                and (cond.factor, cond.operator, cond.value) in entry_keys:
            warnings.append(
                f"진입과 청산에 동일한 조건({cond.factor} {cond.operator} {cond.value})이 있어 "
                "매수 직후 매도될 수 있습니다"
            )

    return errors, warnings
