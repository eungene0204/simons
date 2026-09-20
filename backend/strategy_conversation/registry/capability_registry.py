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

# 엔진 ParsedStrategy.rebalance_method Literal과 1:1 (FR-BT-067)
# reconstitute = 리밸런싱일마다 목표 종목 재선정, weights_only = 종목 교체 없이 비중만 균등 리셋
SUPPORTED_REBALANCE_METHODS = ("reconstitute", "weights_only")

# 엔진 ParsedStrategy.allocation_type Literal과 1:1 — 동일 비중 / 변동성 역비중(v16.14)
SUPPORTED_WEIGHTINGS = ("equal", "inverse_volatility")

# 리스크 패리티 계열 표기 — 엔진은 공분산을 쓰지 않는 역변동성 가중(1/σ)으로 반영하므로
# '가깝게 반영'했다고 알린다(2026-09-19 사용자 결정: 완전 위험기여 균등(ERC) 대신 역변동성).
RISK_PARITY_WEIGHTING_ALIASES = frozenset({
    "risk_parity", "riskparity", "risk-parity", "리스크패리티", "리스크_패리티", "erc",
    "equal_risk_contribution",
})

SUPPORTED_MARKETS = ("KOSPI", "KOSDAQ", "KOSPI200", "KOSDAQ150",
                     "SP500", "NASDAQ100", "NASDAQ", "DOW30", "US")

# 미국 시장 토큰 — 한국 시장과 혼합 금지·업종/신규상장/AI 미지원 검증에 쓴다
US_MARKETS = ("SP500", "NASDAQ100", "NASDAQ", "DOW30", "US", "US_ETF")

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
    key = value.strip().lower().replace(" ", "_")
    if key in ("equal", "동일비중", "균등", "equal_weight", "동일"):
        return "equal"
    if key in ("inverse_volatility", "inverse_vol", "inverse-volatility", "변동성역비중",
               "변동성_역비중", "역변동성", "volatility_weighted", "inverse_volatility_weighting") \
            or key in RISK_PARITY_WEIGHTING_ALIASES:
        return "inverse_volatility"
    return None
