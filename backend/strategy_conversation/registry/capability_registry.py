"""CapabilityRegistry — 지표 외 시스템 기능의 지원 계약.

포트폴리오 구성·리밸런싱·유니버스 등 엔진이 실제로 지원하는 값의 화이트리스트.
compiler와 validator가 공유하는 단일 진실 소스다(엔진 스키마와 1:1 유지).
"""

from __future__ import annotations

from typing import Optional

# 엔진 ParsedStrategy.rebalancing_period Literal과 1:1
SUPPORTED_REBALANCE_FREQUENCIES = (
    "none", "daily", "weekly", "monthly", "bimonthly", "quarterly", "semiannual", "yearly",
)

# 엔진 ParsedStrategy.rebalance_method Literal과 1:1 (FR-BT-067)
# reconstitute = 리밸런싱일마다 목표 종목 재선정, weights_only = 종목 교체 없이 비중만 균등 리셋
SUPPORTED_REBALANCE_METHODS = ("reconstitute", "weights_only")

# 엔진 ParsedStrategy.allocation_type Literal과 1:1 — 동일 비중 / 변동성 역비중(v16.14)
SUPPORTED_WEIGHTINGS = ("equal", "inverse_volatility", "market_cap", "min_variance", "risk_parity",
                        "max_sharpe", "min_cvar", "fixed")
# 수익률 공분산·평균으로 비중을 푸는 방식(v16.28) — 산정 기간(weighting_lookback_days)을 받는다.
OPTIMIZER_WEIGHTINGS = ("min_variance", "risk_parity", "max_sharpe", "min_cvar")
SUPPORTED_EXECUTION_TIMINGS = ("next_open", "current_close", "next_avg")

# 리스크 패리티 계열 표기 — v16.28부터 엔진이 공분산 기반 위험 기여 균등(ERC)을 직접 푼다
# (종전 09-19 결정의 역변동성 근사는 폐지). 표기 변형만 정본 값으로 맞춘다.
RISK_PARITY_WEIGHTING_ALIASES = frozenset({
    "risk_parity", "riskparity", "risk-parity", "리스크패리티", "리스크_패리티", "erc",
    "equal_risk_contribution",
})
_WEIGHTING_ALIASES = {
    "market_cap": "market_cap", "marketcap": "market_cap", "market-cap": "market_cap", "cap_weighted": "market_cap",
    "시가총액": "market_cap", "시총가중": "market_cap", "시가총액가중": "market_cap", "시총비중": "market_cap",
    "가치가중": "market_cap", "value_weighted": "market_cap",
    "min_variance": "min_variance", "minimum_variance": "min_variance", "최소분산": "min_variance",
    "min_vol": "min_variance", "minimum_volatility": "min_variance", "변동성최저": "min_variance",
    "최소변동성": "min_variance", "gmv": "min_variance",
    "max_sharpe": "max_sharpe", "maximum_sharpe": "max_sharpe", "최대샤프": "max_sharpe", "mvo": "max_sharpe",
    "mean_variance": "max_sharpe", "평균분산": "max_sharpe", "평균분산최적화": "max_sharpe", "tangency": "max_sharpe",
    "min_cvar": "min_cvar", "minimum_cvar": "min_cvar", "cvar": "min_cvar", "최소cvar": "min_cvar",
    "fixed": "fixed", "고정비중": "fixed", "고정": "fixed", "target_weights": "fixed", "static": "fixed",
}

SUPPORTED_MARKETS = ("KOSPI", "KOSDAQ", "KOSPI200", "KOSDAQ150",
                     "SP500", "NASDAQ100", "NASDAQ", "DOW30", "US")

# 미국 시장 토큰 — 한국 시장과 혼합 금지·업종/신규상장/AI 미지원 검증에 쓴다
US_MARKETS = ("SP500", "NASDAQ100", "NASDAQ", "DOW30", "US", "US_ETF")

SUPPORTED_BACKTEST_PERIODS = ("1y", "3y", "5y", "full")

MAX_POSITIONS_RANGE = (1, 100)

# 리밸런싱 주기 → 대략적 거래일 수(보유기간 충돌 검사용)
REBALANCE_FREQUENCY_DAYS = {
    "daily": 1, "weekly": 5, "monthly": 21, "bimonthly": 42,
    "quarterly": 63, "semiannual": 126, "yearly": 252,
}

_FREQUENCY_ALIASES = {
    "매일": "daily", "일간": "daily", "daily": "daily",
    "매주": "weekly", "주간": "weekly", "weekly": "weekly",
    "매월": "monthly", "월간": "monthly", "monthly": "monthly", "한달": "monthly",
    "격월": "bimonthly", "bimonthly": "bimonthly",
    "분기": "quarterly", "분기별": "quarterly", "quarterly": "quarterly",
    # 반기(v16.25) — 엔진 rebalance.py는 이미 알았지만 대화 레인 허용 목록에 빠져 요청할 수 없었다.
    "반기": "semiannual", "반기별": "semiannual", "반기마다": "semiannual", "6개월": "semiannual",
    "6개월마다": "semiannual", "semiannual": "semiannual", "semi-annual": "semiannual",
    "half-yearly": "semiannual", "halfyearly": "semiannual",
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


# 다중 타임프레임(v16.29) — 조건 파라미터 timeframe의 표기 변형. 일봉은 값 없음.
STRING_CONDITION_PARAMS = ("timeframe", "pattern")
_TIMEFRAME_ALIASES = {
    "weekly": "weekly", "week": "weekly", "w": "weekly", "주봉": "weekly", "주간": "weekly", "1w": "weekly",
    "monthly": "monthly", "month": "monthly", "m": "monthly", "월봉": "monthly", "월간": "monthly", "1m": "monthly",
}
TAA_MODELS = ("vaa", "daa", "paa")


def normalize_timeframe(value) -> Optional[str]:
    if value is None:
        return None
    key = str(value).strip().lower().replace(" ", "")
    if key in ("daily", "day", "d", "일봉", "1d", ""):
        return "daily"
    return _TIMEFRAME_ALIASES.get(key)


def normalize_weighting(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    key = value.strip().lower().replace(" ", "_")
    if key in ("equal", "동일비중", "균등", "equal_weight", "동일"):
        return "equal"
    if key in ("inverse_volatility", "inverse_vol", "inverse-volatility", "변동성역비중",
               "변동성_역비중", "역변동성", "volatility_weighted", "inverse_volatility_weighting"):
        return "inverse_volatility"
    if key in RISK_PARITY_WEIGHTING_ALIASES:
        return "risk_parity"
    return _WEIGHTING_ALIASES.get(key)
