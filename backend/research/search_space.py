"""
Per-template Optuna search-space whitelist.

에이전트는 여기 정의된 DSL 블록 파라미터 범위만 Optuna에 전달한다.
DSL 블록 ID와 파라미터 키가 실제 SignalEngine에 존재하는지 코드 리뷰 시 검증한다.
"""

from __future__ import annotations

from typing import Any, Dict

# 공통: 포지션 크기 / 손절익절 범위 — 모든 템플릿이 공유
_RISK_RANGES: Dict[str, Any] = {
    "risk.stop_loss_pct": {"type": "number", "min": 5, "max": 20, "step": 1},
    "risk.take_profit_pct": {"type": "number", "min": 10, "max": 50, "step": 5},
}

# 템플릿별 진입 조건 파라미터 범위
# path prefix는 strategy_converter._tech_signal_to_condition 이 생성하는 구조를 따른다:
#   entry.conditions.<idx>.params.<key>
TEMPLATE_SEARCH_SPACES: Dict[str, Dict[str, Any]] = {
    "momentum": {
        "entry.conditions.0.params.shortMA": {"type": "number", "min": 3, "max": 20, "step": 1},
        "entry.conditions.0.params.longMA": {"type": "number", "min": 20, "max": 120, "step": 5},
        **_RISK_RANGES,
    },
    "mean_reversion": {
        "entry.conditions.0.params.period": {"type": "number", "min": 10, "max": 21, "step": 1},
        "entry.conditions.0.params.value": {"type": "number", "min": 20, "max": 35, "step": 1},
        **_RISK_RANGES,
    },
    "value": {
        # fundamental filter의 value는 전략 본질이므로 좁게만 튜닝
        "entry.conditions.0.params.value": {"type": "number", "min": 0.5, "max": 1.5, "step": 0.1},
        **_RISK_RANGES,
    },
    "volume_breakout": {
        "entry.conditions.0.params.lookbackPeriod": {"type": "number", "min": 20, "max": 120, "step": 5},
        "entry.conditions.1.params.period": {"type": "number", "min": 10, "max": 30, "step": 1},
        **_RISK_RANGES,
    },
    "ai_signal": {
        "entry.conditions.0.params.threshold": {"type": "number", "min": 55, "max": 85, "step": 5},
        **_RISK_RANGES,
    },
}


def get_search_space(template: str) -> Dict[str, Any]:
    """Return Optuna-compatible ranges dict for a given template.

    Unknown templates return an empty dict (optimizer will no-op).
    """
    return dict(TEMPLATE_SEARCH_SPACES.get(template, {}))


def space_cardinality(ranges: Dict[str, Any]) -> int:
    """Rough cardinality estimate (product of number-of-steps per param).

    Used to cap Optuna n_trials below sqrt(cardinality) to prevent overfitting
    to noise in the search space.
    """
    card = 1
    for spec in ranges.values():
        if isinstance(spec, dict) and spec.get("type") == "number":
            lo = spec["min"]
            hi = spec["max"]
            step = spec.get("step", 1)
            if step <= 0:
                continue
            card *= max(1, int((hi - lo) / step) + 1)
        elif isinstance(spec, list):
            card *= max(1, len(spec))
    return card
