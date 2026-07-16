"""CapabilityRegistry — 지표 외 시스템 기능의 지원 계약.

포트폴리오 구성·리밸런싱·유니버스 등 엔진이 실제로 지원하는 값의 화이트리스트.
compiler와 validator가 공유하는 단일 진실 소스다(엔진 스키마와 1:1 유지).
"""

from __future__ import annotations

from typing import Optional

# 엔진 ParsedStrategy.rebalancing_period Literal과 1:1
SUPPORTED_REBALANCE_FREQUENCIES = (
    "none", "daily", "weekly", "monthly", "bimonthly", "quarterly", "yearly",
)

# 엔진은 동일비중만 지원한다(별도 가중 방식 없음)
SUPPORTED_WEIGHTINGS = ("equal",)

SUPPORTED_MARKETS = ("KOSPI", "KOSDAQ", "KOSPI200")

SUPPORTED_BACKTEST_PERIODS = ("1y", "3y", "5y", "full")

MAX_POSITIONS_RANGE = (1, 100)

# 리밸런싱 주기 → 대략적 거래일 수(보유기간 충돌 검사용)
REBALANCE_FREQUENCY_DAYS = {
    "daily": 1, "weekly": 5, "monthly": 21, "bimonthly": 42,
    "quarterly": 63, "yearly": 252,
}

_FREQUENCY_ALIASES = {
    "매일": "daily", "일간": "daily", "daily": "daily",
    "매주": "weekly", "주간": "weekly", "weekly": "weekly",
    "매월": "monthly", "월간": "monthly", "monthly": "monthly", "한달": "monthly",
    "격월": "bimonthly", "bimonthly": "bimonthly",
    "분기": "quarterly", "분기별": "quarterly", "quarterly": "quarterly",
    "매년": "yearly", "연간": "yearly", "yearly": "yearly", "annual": "yearly",
    "없음": "none", "none": "none",
}


def normalize_rebalance_frequency(value: Optional[str]) -> Optional[str]:
    """리밸런싱 주기 표기를 엔진 enum으로 정규화한다. 해석 불가면 None."""
    if not value:
        return None
    key = value.strip().replace(" ", "").lower()
    if key in SUPPORTED_REBALANCE_FREQUENCIES:
        return key
    return _FREQUENCY_ALIASES.get(key)


def normalize_weighting(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = value.strip().lower()
    if key in ("equal", "동일비중", "균등", "equal_weight", "동일"):
        return "equal"
    return None
