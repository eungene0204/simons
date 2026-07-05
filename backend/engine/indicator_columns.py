"""지표 파라미터 → stockstats 컬럼명 결정 (indicators.py·signals.py 공유).

MACD/스토캐스틱/볼린저는 원래 stockstats 기본값(12/26/9, KDJ 9, BOLL 20±2σ) 고정이었다.
파라미터가 명시되면 stockstats의 파라미터화 컬럼 문법(macd_f,s,g / kdjk_n / boll_n)을 쓰고,
기본값이면 기존 컬럼을 그대로 써서 과거 백테스트 결과와의 동일성을 보존한다.
"""

from typing import Any, Dict, Tuple

MACD_DEFAULTS = (12, 26, 9)
STOCHASTIC_DEFAULT_PERIOD = 9
BOLLINGER_DEFAULT_PERIOD = 20
BOLLINGER_DEFAULT_STD = 2.0


def macd_params(p: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        int(p.get("fastPeriod", MACD_DEFAULTS[0])),
        int(p.get("slowPeriod", MACD_DEFAULTS[1])),
        int(p.get("signalPeriod", MACD_DEFAULTS[2])),
    )


def macd_columns(p: Dict[str, Any]) -> Tuple[str, str]:
    """(macd 라인, 시그널 라인) 컬럼명."""
    fast, slow, signal = macd_params(p)
    if (fast, slow, signal) == MACD_DEFAULTS:
        return "macd", "macds"
    suffix = f"{fast},{slow},{signal}"
    return f"macd_{suffix}", f"macds_{suffix}"


def stochastic_period(p: Dict[str, Any]) -> int:
    return int(p.get("period", STOCHASTIC_DEFAULT_PERIOD))


def stochastic_columns(p: Dict[str, Any]) -> Tuple[str, str]:
    """(K, D) 컬럼명."""
    period = stochastic_period(p)
    if period == STOCHASTIC_DEFAULT_PERIOD:
        return "kdjk", "kdjd"
    return f"kdjk_{period}", f"kdjd_{period}"


def bollinger_params(p: Dict[str, Any]) -> Tuple[int, float]:
    return (
        int(p.get("period", BOLLINGER_DEFAULT_PERIOD)),
        float(p.get("stdDev", BOLLINGER_DEFAULT_STD)),
    )


def bollinger_columns(p: Dict[str, Any]) -> Tuple[str, str]:
    """(상단 밴드, 하단 밴드) 컬럼명.

    - (20, 2.0): stockstats 기본 boll_ub / boll_lb
    - (n, 2.0): stockstats 파라미터화 boll_ub_n / boll_lb_n
    - (n, k):   커스텀 계산 컬럼 boll_ub_n_kp5 형태 (indicators.py가 직접 산출)
    """
    period, std = bollinger_params(p)
    if (period, std) == (BOLLINGER_DEFAULT_PERIOD, BOLLINGER_DEFAULT_STD):
        return "boll_ub", "boll_lb"
    if std == BOLLINGER_DEFAULT_STD:
        return f"boll_ub_{period}", f"boll_lb_{period}"
    std_tag = f"{std:g}".replace(".", "p")
    return f"boll_ub_{period}_{std_tag}", f"boll_lb_{period}_{std_tag}"
