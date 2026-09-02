"""증권거래세 시행일 스케줄 — 매도 봉의 날짜에 맞는 법정 세율을 돌려준다."""
import pandas as pd
import pytest

from engine.transaction_tax import kr_sell_tax_rates, CURRENT_KR_SELL_TAX_RATE


@pytest.mark.parametrize("date,rate", [
    ("2015-03-02", 0.0030),
    ("2019-05-29", 0.0030),
    ("2019-05-30", 0.0025),   # 시행일 당일 포함
    ("2020-12-30", 0.0025),
    ("2021-01-04", 0.0023),
    ("2022-12-29", 0.0023),
    ("2023-01-02", 0.0020),
    ("2024-01-02", 0.0018),
    ("2025-01-02", 0.0015),
    ("2026-08-28", 0.0015),
])
def test_rate_by_effective_date(date, rate):
    assert kr_sell_tax_rates(pd.DatetimeIndex([date]))[0] == pytest.approx(rate)


def test_vector_shape_follows_index():
    idx = pd.bdate_range("2018-12-24", "2019-06-05")
    rates = kr_sell_tax_rates(idx)
    assert rates.shape == (len(idx),)
    assert rates[0] == pytest.approx(0.0030) and rates[-1] == pytest.approx(0.0025)


def test_current_rate_is_last_schedule_entry():
    assert CURRENT_KR_SELL_TAX_RATE == pytest.approx(0.0015)
