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


def test_weekly_marks_first_trading_day_of_each_iso_week():
    # 평일(B) 30거래일 ≈ 6주 → 매주 첫 거래일(월요일)에 True
    idx = _dates("2024-01-01", 30, freq="B")
    mask = compute_rebalance_dates(idx, "weekly")
    flagged = [str(idx[i].date()) for i in np.where(mask)[0]]
    assert flagged == [
        "2024-01-01",
        "2024-01-08",
        "2024-01-15",
        "2024-01-22",
        "2024-01-29",
        "2024-02-05",
    ]


def test_weekly_handles_year_boundary_iso_week():
    # 연말~연초 경계에서 ISO 주차로 끊겨 같은 주가 중복 플래그되지 않는다.
    idx = _dates("2023-12-25", 10, freq="B")  # 2023 W52 ~ 2024 W01
    mask = compute_rebalance_dates(idx, "weekly")
    flagged = [str(idx[i].date()) for i in np.where(mask)[0]]
    assert flagged[0] == "2023-12-25"   # 첫 거래일(W52 월요일)
    assert "2024-01-01" in flagged      # W01 첫 거래일
    # 12/25 주 안에서는 한 번만
    assert flagged.count("2023-12-26") == 0


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


def test_bimonthly_marks_every_two_month_block():
    # 1·2월, 3·4월, 5·6월 … 각 2달 블록의 첫 거래일에만 True.
    idx = _dates("2024-01-01", 200)  # Jan ~ Jul 일부
    mask = compute_rebalance_dates(idx, "bimonthly")
    flagged = [str(idx[i].date()) for i in np.where(mask)[0]]
    assert "2024-01-01" in flagged   # 1·2월 블록 시작
    assert "2024-03-01" in flagged   # 3·4월 블록 시작
    assert "2024-05-01" in flagged   # 5·6월 블록 시작
    assert "2024-07-01" in flagged   # 7·8월 블록 시작
    # 같은 블록 안의 둘째 달 1일에는 새 플래그가 생기지 않는다.
    assert "2024-02-01" not in flagged
    assert "2024-04-01" not in flagged
    assert "2024-06-01" not in flagged


def test_semiannual_marks_half_year_boundaries():
    # 반기(1~6월 / 7~12월) 첫 거래일에만 True — 리밸런싱 기간별 비교(FR-BT-064)용 신설 주기.
    idx = _dates("2023-03-15", 500)  # 2023 상반기 중간 ~ 2024 하반기 초입
    mask = compute_rebalance_dates(idx, "semiannual")
    flagged = [str(idx[i].date()) for i in np.where(mask)[0]]
    assert flagged == ["2023-03-15", "2023-07-01", "2024-01-01", "2024-07-01"]


def test_empty_index():
    assert len(compute_rebalance_dates(pd.DatetimeIndex([]), "monthly")) == 0
