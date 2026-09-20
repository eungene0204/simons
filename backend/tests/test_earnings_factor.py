"""실적 서프라이즈 시그널(engine/earnings_factor.py)의 계약 테스트.

지키려는 계약:
  ① 전년 동기는 **날짜**로 찾는다(목록에서 4칸 앞이 아니다)
  ② 표본·표준편차·가격이 모자라면 NaN(중립값 0으로 위장하지 않는다)
  ③ 편입 지연·제외 창이 시그널 자격 그 자체다 — 자격 밖은 NaN
  ④ 새 실적이 발표되면 옛 분기 시그널은 그 날 끊긴다
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import earnings_factor as ef


def _quarters(eps_by_period, announce_lag_days=45):
    """{'2024-03-31': 100.0, ...} → 수집 레코드 목록."""
    records = []
    for period_end, eps in sorted(eps_by_period.items()):
        announced = pd.Timestamp(period_end) + pd.Timedelta(days=announce_lag_days)
        records.append({
            "period_end": period_end,
            "eps": eps,
            "announce_date": announced.strftime("%Y-%m-%d"),
            "fs_div": "CFS",
        })
    return records


def _period_ends(start="2019-03-31", count=16):
    return list(pd.date_range(start=start, periods=count, freq="QE").strftime("%Y-%m-%d"))


def test_year_over_year_uses_date_not_list_position():
    """분기 하나가 비어도 전년 동기는 12개월 전 분기다."""
    periods = _period_ends(count=9)
    eps = {period: 100.0 for period in periods}
    eps[periods[8]] = 150.0           # 2021-03-31
    del eps[periods[5]]               # 중간 분기 결측 → 4칸 앞은 2년 전이 된다

    surprises = ef.year_over_year_surprises(_quarters(eps))

    latest = surprises[-1]
    assert latest["period_end"] == pd.Timestamp(periods[8])
    # 전년 동기(periods[4], 100.0)와의 차이여야 한다.
    assert latest["surprise"] == pytest.approx(50.0)


def test_quarter_without_year_ago_counterpart_is_dropped():
    eps = {period: 100.0 for period in _period_ends(count=3)}

    assert ef.year_over_year_surprises(_quarters(eps)) == []


def test_sue_divides_surprise_by_sample_standard_deviation():
    periods = _period_ends(count=16)
    # YoY 차이가 분기마다 달라지도록(표준편차가 0이 아니도록) 이차식으로 쌓는다.
    eps = {period: 100.0 + float(index * index) for index, period in enumerate(periods)}
    surprises = ef.year_over_year_surprises(_quarters(eps))
    values = [row["surprise"] for row in surprises]

    entries = ef.sue_series(_quarters(eps), sample=8)

    expected = values[-1] / float(np.std(values[-8:], ddof=1))
    assert entries[-1]["sue"] == pytest.approx(expected)


def test_sue_absent_when_sample_incomplete():
    periods = _period_ends(count=9)
    eps = {period: 100.0 + index for index, period in enumerate(periods)}

    # YoY 차이가 5개뿐이라 8개 표본을 채울 수 없다.
    assert ef.sue_series(_quarters(eps), sample=8) == []


def test_sue_absent_when_surprises_are_constant():
    """표준편차 0은 '서프라이즈가 무한대'가 아니라 값 없음이다."""
    periods = _period_ends(count=16)
    eps = {period: 100.0 + 10.0 * (index // 4) for index, period in enumerate(periods)}
    # 위 test와 같은 구성이지만 차이를 일정하게 만들면 표준편차가 0이다.
    eps = {period: 100.0 + 10.0 * index for index, period in enumerate(periods)}

    assert ef.sue_series(_quarters(eps), sample=8) == []


# ─── 발표일 초과수익률 ────────────────────────────────────────────────────────

def _calendar(days=40):
    return pd.DatetimeIndex(pd.bdate_range("2024-01-01", periods=days))


def _returns(length, first_is_nan=True):
    """일간 수익률 배열 — 첫 날은 직전 종가가 없어 NaN이다(실제 재료와 같은 모양)."""
    series = np.zeros(length, dtype=float)
    if first_is_nan:
        series[0] = np.nan
    return series


def test_event_excess_return_subtracts_market_over_same_window():
    calendar = _calendar()
    stock, market = _returns(len(calendar)), _returns(len(calendar))
    event = 10
    stock[event + 2] = 0.10        # 종목 +10%
    market[event + 2] = 0.02       # 시장 +2%

    excess = ef.event_excess_return(calendar, stock, market, calendar[event])

    assert excess == pytest.approx(0.10 - 0.02)


def test_event_window_covers_day_before_through_two_days_after():
    """D-1 종가 → D+2 종가 = r[D]·r[D+1]·r[D+2]의 누적(발표 당일 수익률이 포함된다)."""
    calendar = _calendar()
    stock, market = _returns(len(calendar)), _returns(len(calendar))
    event = 10
    stock[event] = 0.05            # 발표 당일 — 구간 안
    stock[event - 1] = 0.99        # D-1 당일 수익률은 구간 밖(분모가 D-1 종가이므로)

    excess = ef.event_excess_return(calendar, stock, market, calendar[event])

    assert excess == pytest.approx(0.05)


def test_event_excess_return_none_when_window_falls_outside_calendar():
    calendar = _calendar(days=12)
    stock, market = _returns(len(calendar)), _returns(len(calendar))

    # 끝: D+2가 달력 밖. 시작: 첫 거래일은 직전 종가가 없어 수익률이 NaN이다.
    assert ef.event_excess_return(calendar, stock, market, calendar[-1]) is None
    assert ef.event_excess_return(calendar, stock, market, calendar[0]) is None


def test_event_excess_return_none_when_any_day_missing():
    calendar = _calendar()
    stock, market = _returns(len(calendar)), _returns(len(calendar))
    stock[11] = np.nan             # 거래정지 등으로 구간 안에 결측

    assert ef.event_excess_return(calendar, stock, market, calendar[10]) is None


def test_non_trading_announcement_moves_to_next_session():
    calendar = _calendar()
    stock, market = _returns(len(calendar)), _returns(len(calendar))
    saturday = calendar[10] + pd.Timedelta(days=1)   # bdate 달력에 없는 날

    # 직후 거래일을 D로 보므로 계산이 성립한다(값이 None이 아니다).
    assert ef.event_excess_return(calendar, stock, market, saturday) is not None


# ─── 자격 창(편입 지연·제외) ──────────────────────────────────────────────────

def test_signal_is_absent_before_delay_and_after_expiry():
    calendar = _calendar(days=100)
    rows = {"A": [{"announce_position": 10, "sue": 1.0, "excess_return": 0.05}]}

    panels = ef.event_panels(rows, calendar, delay=2, expiry=60)
    series = panels["sue"]["A"].to_numpy()

    assert np.isnan(series[11])          # 발표 다음 날 — 아직 자격 없음
    assert series[12] == pytest.approx(1.0)   # 발표 + 2영업일부터 편입 자격
    assert series[69] == pytest.approx(1.0)   # 발표 + 59영업일까지 보유
    assert np.isnan(series[70])          # 발표 + 60영업일에 제외


def test_new_announcement_ends_previous_signal():
    calendar = _calendar(days=100)
    rows = {"A": [
        {"announce_position": 10, "sue": 1.0, "excess_return": 0.05},
        {"announce_position": 40, "sue": -3.0, "excess_return": -0.02},
    ]}

    series = ef.event_panels(rows, calendar, delay=2, expiry=60)["sue"]["A"].to_numpy()

    assert series[39] == pytest.approx(1.0)    # 새 발표 직전까지는 옛 시그널
    assert np.isnan(series[40])                # 새 실적이 나온 날 옛 시그널은 끊긴다
    assert np.isnan(series[41])                # 새 시그널은 자기 지연이 지나야 선다
    assert series[42] == pytest.approx(-3.0)


def test_pead_signal_is_mean_of_two_cross_sectional_zscores():
    calendar = pd.DatetimeIndex(pd.bdate_range("2024-01-01", periods=1))
    sue = pd.DataFrame([[1.0, 2.0, 3.0]], index=calendar, columns=["A", "B", "C"])
    excess = pd.DataFrame([[3.0, 2.0, 1.0]], index=calendar, columns=["A", "B", "C"])

    signal = ef.pead_signal(sue, excess)

    # 대칭인 두 z-score의 평균이므로 가운데 종목이 0, 양끝이 상쇄된다.
    assert signal.loc[calendar[0], "B"] == pytest.approx(0.0)
    assert signal.loc[calendar[0], "A"] == pytest.approx(0.0)
    assert signal.loc[calendar[0], "C"] == pytest.approx(0.0)


def test_pead_signal_absent_when_one_side_missing():
    calendar = pd.DatetimeIndex(pd.bdate_range("2024-01-01", periods=1))
    sue = pd.DataFrame([[1.0, 2.0, np.nan]], index=calendar, columns=["A", "B", "C"])
    excess = pd.DataFrame([[3.0, 2.0, 1.0]], index=calendar, columns=["A", "B", "C"])

    signal = ef.pead_signal(sue, excess)

    assert np.isnan(signal.loc[calendar[0], "C"])
