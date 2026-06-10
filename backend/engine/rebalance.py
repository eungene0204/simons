"""달력 기준 리밸런싱 유틸 (vectorbt 비의존 — 단위 테스트 가능)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_rebalance_dates(index, period: str) -> np.ndarray:
    """리밸런싱 실행일을 boolean 배열로 반환한다.

    각 주기의 '첫 거래일'에 True. 'none'이면 전부 False, 'daily'면 전부 True.
    weekly/monthly/bimonthly/quarterly/yearly는 직전 행과 주/달/2달/분기/연이 바뀌는 첫 행에서 True.
    """
    n = len(index)
    if n == 0 or period in (None, "none"):
        return np.zeros(n, dtype=bool)
    if period == "daily":
        return np.ones(n, dtype=bool)

    idx = pd.DatetimeIndex(index)
    if period == "weekly":
        # ISO 주차 기준(연말·연초 경계에서도 안전). 연도×100 + 주차로 고유 키 생성.
        iso = idx.isocalendar()
        keys = np.asarray(iso["year"]) * 100 + np.asarray(iso["week"])
    elif period == "monthly":
        keys = np.asarray(idx.year) * 12 + np.asarray(idx.month)
    elif period == "bimonthly":
        # 2달씩 묶는다(1·2월, 3·4월 …). 각 블록의 첫 거래일에 True.
        keys = (np.asarray(idx.year) * 12 + (np.asarray(idx.month) - 1)) // 2
    elif period == "quarterly":
        keys = np.asarray(idx.year) * 4 + np.asarray(idx.quarter)
    elif period == "yearly":
        keys = np.asarray(idx.year)
    else:
        return np.zeros(n, dtype=bool)

    mask = np.zeros(n, dtype=bool)
    mask[0] = True
    mask[1:] = keys[1:] != keys[:-1]
    return mask
