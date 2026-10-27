from datetime import date, datetime, timezone

import pytest

from public_simulation.window import (
    WindowError, actual_period, compute_window, previous_weekday, seoul_today, three_years_before,
)

KST_NOON = lambda y, m, d: datetime(y, m, d, 3, 0, tzinfo=timezone.utc)  # 12:00 KST


def test_three_years_before_leap_day_uses_feb_28():
    assert three_years_before(date(2028, 2, 29)) == date(2025, 2, 28)
    assert three_years_before(date(2026, 2, 28)) == date(2023, 2, 28)
    assert three_years_before(date(2027, 3, 1)) == date(2024, 3, 1)
    # 3년 전이 윤년의 2월 29일이어도 같은 월·일이 존재하면 그대로다.
    assert three_years_before(date(2027, 2, 28)) == date(2024, 2, 28)


def test_today_is_seoul_date_not_utc():
    # 2026-10-26 16:00 UTC = 2026-10-27 01:00 KST
    assert seoul_today(datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)) == date(2026, 10, 27)
    with pytest.raises(ValueError):
        seoul_today(datetime(2026, 10, 27, 1, 0))


def test_previous_weekday_skips_weekend():
    assert previous_weekday(date(2026, 10, 26)) == date(2026, 10, 23)  # 월 → 금
    assert previous_weekday(date(2026, 10, 25)) == date(2026, 10, 23)  # 일 → 금
    assert previous_weekday(date(2026, 10, 28)) == date(2026, 10, 27)


def test_intraday_uses_previous_close_and_is_not_stale():
    # 수요일 장중: 확정 데이터는 화요일까지
    w = compute_window(KST_NOON(2026, 10, 28), date(2026, 10, 27))
    assert (w.today, w.requested_start, w.end_date, w.data_as_of) == (
        "2026-10-28", "2023-10-28", "2026-10-27", "2026-10-27")
    assert w.stale is False


def test_after_close_today_data_included():
    w = compute_window(KST_NOON(2026, 10, 28), date(2026, 10, 28))
    assert w.end_date == "2026-10-28" and w.stale is False


def test_weekend_and_monday_are_not_stale_with_friday_data():
    assert compute_window(KST_NOON(2026, 10, 25), date(2026, 10, 23)).stale is False  # 일요일
    assert compute_window(KST_NOON(2026, 10, 26), date(2026, 10, 23)).stale is False  # 월요일 장중


def test_delayed_data_is_stale_and_end_date_follows_data():
    w = compute_window(KST_NOON(2026, 10, 28), date(2026, 10, 26))
    assert w.stale is True and w.end_date == "2026-10-26"


def test_future_data_never_extends_window_past_today():
    w = compute_window(KST_NOON(2026, 10, 28), date(2026, 10, 30))
    assert w.end_date == "2026-10-28"


def test_no_data_in_window_raises():
    with pytest.raises(WindowError) as exc:
        compute_window(KST_NOON(2026, 10, 28), date(2023, 10, 1))
    assert exc.value.code == "NO_DATA_IN_WINDOW"


def test_actual_period_full_and_limited():
    w = compute_window(KST_NOON(2026, 10, 28), date(2026, 10, 27))
    full = actual_period(w, "2023-10-30", "2026-10-27")  # 주말 때문에 이틀 늦음
    assert full["limited"] is False and "limitReason" not in full
    short = actual_period(w, "2024-06-03", "2026-10-27")
    assert short["limited"] is True and short["limitReason"] == "DATA_STARTS_LATER"
    assert short["requestedStart"] == "2023-10-28" and short["actualStart"] == "2024-06-03"


def test_actual_period_outside_window_is_rejected():
    w = compute_window(KST_NOON(2026, 10, 28), date(2026, 10, 27))
    for start, end in (("2023-10-01", "2026-10-27"), ("2023-11-01", "2026-10-28")):
        with pytest.raises(WindowError) as exc:
            actual_period(w, start, end)
        assert exc.value.code == "WINDOW_VIOLATION"
