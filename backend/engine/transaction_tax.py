"""한국 증권거래세 매도세율 — 시행일 기준 법정 스케줄(농어촌특별세 포함).

백테스트는 과거 어느 해의 매도든 같은 세율을 물리면 안 된다 — 2019년 이전 매도에
2025년 세율(0.15%)을 적용하면 매도 1회당 최대 0.15%p를 덜 물려 장기 결과가 실제보다
유리해진다. 코스피(거래세+농특세)와 코스닥(거래세) 합산 세율은 모든 구간에서 같다.
ETF·미국 주식은 증권거래세가 없다(엔진이 sell_tax_rate=0을 명시한다).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# (시행일, 코스피·코스닥 합산 매도세율). 시행일 이후 다음 시행일 전까지 적용.
KR_SELL_TAX_SCHEDULE: tuple[tuple[str, float], ...] = (
    ("1900-01-01", 0.0030),   # 거래세 0.15% + 농특세 0.15% (코스닥 0.30%)
    ("2019-05-30", 0.0025),   # 2019-05-30 인하
    ("2021-01-01", 0.0023),
    ("2023-01-01", 0.0020),
    ("2024-01-01", 0.0018),
    ("2025-01-01", 0.0015),   # 코스피 거래세 0% + 농특세 0.15%
)

CURRENT_KR_SELL_TAX_RATE = KR_SELL_TAX_SCHEDULE[-1][1]


def kr_sell_tax_rates(index: pd.Index) -> np.ndarray:
    """봉 날짜별 매도세율 벡터(len(index),). 시행일 경계는 당일 포함."""
    dates = pd.DatetimeIndex(pd.to_datetime(index)).normalize()
    starts = pd.DatetimeIndex([pd.Timestamp(d) for d, _ in KR_SELL_TAX_SCHEDULE])
    rates = np.array([r for _, r in KR_SELL_TAX_SCHEDULE], dtype=float)
    pos = starts.searchsorted(dates, side="right") - 1
    return rates[np.clip(pos, 0, len(rates) - 1)]
