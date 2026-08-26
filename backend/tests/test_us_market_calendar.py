"""미국 장 운영 달력(engine/us_market_calendar) — 휴장·조기 종료·장애 폴백 회귀.

자동매매의 미국 장 시간 판정 정본이다. 종전 고정 규칙("평일 09:30~16:00 ET")은
공휴일과 조기 종료일(추수감사절 다음날 13:00 ET)을 몰랐다. 네트워크 없이
`_fetch`를 스텁해 판정 계약만 검증한다.
"""

from __future__ import annotations

from datetime import datetime, time as _time
from zoneinfo import ZoneInfo

import pytest

from engine import us_market_calendar as cal
from engine.virtual_trader import _is_us_market_hours

_ET = ZoneInfo("America/New_York")


_KST = ZoneInfo("Asia/Seoul")


def _day(date_str: str, start: str | None, end: str | None) -> dict:
    """UsMarketDay 형태 — start/end(ET 현지 시각)가 None이면 휴장(regularMarket: null).

    실제 API는 모든 시각을 KST(+09:00)로 준다(스펙) — 같은 표기로 만들어
    파서의 시간대 변환까지 함께 검증한다. 서머타임(EDT/EST)은 ZoneInfo가 처리한다.
    """
    if start is None:
        return {"date": date_str, "regularMarket": None}

    def _kst_iso(hhmm: str) -> str:
        h, m = (int(x) for x in hhmm.split(":"))
        d = datetime.fromisoformat(date_str).date()
        return datetime.combine(d, _time(h, m), tzinfo=_ET).astimezone(_KST).isoformat()

    return {
        "date": date_str,
        "regularMarket": {"startTime": _kst_iso(start), "endTime": _kst_iso(end)},
    }


@pytest.fixture(autouse=True)
def _clean_cache():
    cal.reset_cache()
    yield
    cal.reset_cache()


def _stub(monkeypatch, payload, calls=None):
    def _fake_fetch(date_str):
        if calls is not None:
            calls.append(date_str)
        return payload
    monkeypatch.setattr(cal, "_fetch", _fake_fetch)


# ── 정규장·휴장·조기 종료 ────────────────────────────────────────────────────

def test_regular_day_uses_api_session(monkeypatch):
    _stub(monkeypatch, {"today": _day("2026-08-25", "09:30", "16:00")})
    at = lambda h, m: datetime(2026, 8, 25, h, m, tzinfo=_ET)
    assert cal.is_open(at(9, 29)) is False
    assert cal.is_open(at(9, 30)) is True
    assert cal.is_open(at(16, 0)) is True
    assert cal.is_open(at(16, 1)) is False


def test_holiday_closes_the_market(monkeypatch):
    """공휴일은 regularMarket이 null — 고정 규칙(평일 장중)이라도 닫힘이다."""
    _stub(monkeypatch, {"today": _day("2026-11-26", None, None)})  # 추수감사절(목)
    noon = datetime(2026, 11, 26, 12, 0, tzinfo=_ET)
    assert cal.regular_session(noon) is None
    assert cal.calendar_available(noon) is True
    assert cal.is_open(noon) is False
    assert _is_us_market_hours(noon) is False  # 게이트도 닫힌다


def test_early_close_day_is_respected(monkeypatch):
    """조기 종료일(추수감사절 다음날 13:00 ET) — 오후는 장중이 아니다."""
    _stub(monkeypatch, {"today": _day("2026-11-27", "09:30", "13:00")})
    at = lambda h, m: datetime(2026, 11, 27, h, m, tzinfo=_ET)
    assert cal.is_open(at(12, 59)) is True
    assert cal.is_open(at(13, 0)) is True
    assert cal.is_open(at(13, 1)) is False
    assert _is_us_market_hours(at(15, 0)) is False  # 고정 규칙이면 열렸다고 봤을 시각


def test_payload_date_mismatch_treated_as_closed(monkeypatch):
    """휴장일 조회에서 today가 다음 영업일로 밀려 와도 요청일 기준으로 판정한다."""
    _stub(monkeypatch, {
        "today": _day("2026-11-27", "09:30", "13:00"),      # 다음 영업일
        "previousBusinessDay": _day("2026-11-25", "09:30", "16:00"),
    })
    noon = datetime(2026, 11, 26, 12, 0, tzinfo=_ET)        # 요청일=추수감사절
    assert cal.is_open(noon) is False


# ── 캐시·장애 폴백 ───────────────────────────────────────────────────────────

def test_session_is_cached_per_day(monkeypatch):
    calls: list[str] = []
    _stub(monkeypatch, {"today": _day("2026-08-25", "09:30", "16:00")}, calls)
    at = lambda h: datetime(2026, 8, 25, h, 0, tzinfo=_ET)
    cal.is_open(at(10))
    cal.is_open(at(11))
    cal.is_open(at(12))
    assert calls == ["2026-08-25"]  # 30초 루프가 매번 API를 두드리지 않는다


def test_fetch_failure_falls_back_to_fixed_rule(monkeypatch):
    """달력 장애면 '모름'(None)이라 게이트가 종전 고정 규칙으로 진행한다(fail-open)."""
    def _boom(_date_str):
        raise RuntimeError("network down")
    monkeypatch.setattr(cal, "_fetch", _boom)

    weekday_noon = datetime(2026, 8, 25, 12, 0, tzinfo=_ET)
    saturday_noon = datetime(2026, 8, 29, 12, 0, tzinfo=_ET)
    assert cal.is_open(weekday_noon) is None          # 모름
    assert cal.calendar_available(weekday_noon) is False
    assert _is_us_market_hours(weekday_noon) is True   # 고정 규칙: 평일 장중
    cal.reset_cache()
    assert _is_us_market_hours(saturday_noon) is False  # 고정 규칙: 주말


def test_failure_is_not_retried_every_call(monkeypatch):
    """실패 직후에는 재조회하지 않는다 — 죽은 API를 30초마다 두드리지 않는다."""
    calls: list[str] = []

    def _boom(date_str):
        calls.append(date_str)
        raise RuntimeError("network down")
    monkeypatch.setattr(cal, "_fetch", _boom)

    base = datetime(2026, 8, 25, 12, 0, tzinfo=_ET)
    cal.is_open(base)
    cal.is_open(base.replace(minute=1))
    cal.is_open(base.replace(minute=2))
    assert len(calls) == 1
