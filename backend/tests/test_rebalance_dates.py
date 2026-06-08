import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.rebalance import compute_rebalance_dates


def _dates(start, n, freq="D"):
    return pd.date_range(start, periods=n, freq=freq)


def test_none_is_all_false():
    idx = _dates("2024-01-01", 30)
    assert (~compute_rebalance_dates(idx, "none")).all()
    assert (~compute_rebalance_dates(idx, None)).all()


def test_daily_is_all_true():
    idx = _dates("2024-01-01", 30)
    assert compute_rebalance_dates(idx, "daily").all()


def test_monthly_marks_first_trading_day_of_each_month():
    # 1/15 시작 → 첫 행 + 매월 첫 거래일에 True
    idx = _dates("2024-01-15", 80)  # ~ Jan15 ~ Apr초
    mask = compute_rebalance_dates(idx, "monthly")
    flagged = [str(idx[i].date()) for i in np.where(mask)[0]]
    assert flagged[0] == "2024-01-15"          # 첫 거래일
    assert "2024-02-01" in flagged
    assert "2024-03-01" in flagged
    # 같은 달 안에서는 한 번만
    feb = [d for d in flagged if d.startswith("2024-02")]
    assert feb == ["2024-02-01"]


def test_yearly_marks_year_boundary():
    idx = _dates("2023-06-01", 400)
    mask = compute_rebalance_dates(idx, "yearly")
    flagged = [str(idx[i].date()) for i in np.where(mask)[0]]
    assert flagged == ["2023-06-01", "2024-01-01"]


def test_quarterly_marks_quarter_boundaries():
    idx = _dates("2024-01-01", 200)  # Q1~Q3 일부
    mask = compute_rebalance_dates(idx, "quarterly")
    flagged = [str(idx[i].date()) for i in np.where(mask)[0]]
    assert "2024-01-01" in flagged
    assert "2024-04-01" in flagged  # Q2 시작
    assert "2024-07-01" in flagged  # Q3 시작


def test_empty_index():
    assert len(compute_rebalance_dates(pd.DatetimeIndex([]), "monthly")) == 0
