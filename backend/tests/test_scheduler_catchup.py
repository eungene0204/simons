"""scheduler.py 캐치업 로직 — 직전 거래일 판정 / 데이터 신선도 검사."""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytz

# scripts/는 backend/scripts/와 네임스페이스 충돌이 있어, 파일 경로로 직접 로드한다.
_SCHEDULER_PATH = Path(__file__).resolve().parents[2] / "scripts" / "scheduler.py"
_spec = importlib.util.spec_from_file_location("simons_scheduler", _SCHEDULER_PATH)
scheduler = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scheduler)

KST = pytz.timezone("Asia/Seoul")


def _kst(y, m, d, hour=9, minute=0):
    return KST.localize(datetime(y, m, d, hour, minute))


def test_last_expected_trading_day_monday_is_previous_friday():
    # 2026-06-22는 월요일 → 직전 거래일은 2026-06-19(금)
    assert scheduler._last_expected_trading_day(_kst(2026, 6, 22)).isoformat() == "2026-06-19"


def test_last_expected_trading_day_tuesday_is_monday():
    # 2026-06-23(화) → 2026-06-22(월)
    assert scheduler._last_expected_trading_day(_kst(2026, 6, 23)).isoformat() == "2026-06-22"


def test_last_expected_trading_day_weekend_falls_back_to_friday():
    # 2026-06-20(토)·2026-06-21(일) → 둘 다 2026-06-19(금)
    assert scheduler._last_expected_trading_day(_kst(2026, 6, 20)).isoformat() == "2026-06-19"
    assert scheduler._last_expected_trading_day(_kst(2026, 6, 21)).isoformat() == "2026-06-19"


def test_is_data_stale_true_when_data_behind(monkeypatch):
    from datetime import date
    # 데이터가 06-12까지인데 오늘이 06-22(월) → 직전 거래일 06-19보다 밀림 → stale
    monkeypatch.setattr(scheduler, "_newest_data_date", lambda: date(2026, 6, 12))
    assert scheduler._is_data_stale(_kst(2026, 6, 22)) is True


def test_is_data_stale_false_when_up_to_date(monkeypatch):
    from datetime import date
    # 데이터가 직전 거래일(06-19)까지면 최신 → not stale
    monkeypatch.setattr(scheduler, "_newest_data_date", lambda: date(2026, 6, 19))
    assert scheduler._is_data_stale(_kst(2026, 6, 22)) is False


def test_is_data_stale_true_when_no_data(monkeypatch):
    monkeypatch.setattr(scheduler, "_newest_data_date", lambda: None)
    assert scheduler._is_data_stale(_kst(2026, 6, 22)) is True


# ── 시각 인지 sync 시점(21:00 KST 당일 종가, 2026-07-25 00:00→21:00 전환) ──────────


def test_last_expected_trading_day_before_sync_time_still_expects_previous_day():
    # 화요일 09:00(21:00 sync 전) → 당일분은 아직 안 왔을 시간대이므로 기대치는 월요일
    assert scheduler._last_expected_trading_day(_kst(2026, 6, 23, 9, 0)).isoformat() == "2026-06-22"


def test_last_expected_trading_day_at_sync_time_expects_today():
    # 화요일 21:00 정각(sync 시각 도달) → 당일 종가가 기대치
    assert scheduler._last_expected_trading_day(_kst(2026, 6, 23, 21, 0)).isoformat() == "2026-06-23"


def test_last_expected_trading_day_after_sync_time_expects_today():
    # 화요일 23:00(sync 완료 이후) → 여전히 당일 종가가 기대치
    assert scheduler._last_expected_trading_day(_kst(2026, 6, 23, 23, 0)).isoformat() == "2026-06-23"


def test_last_expected_trading_day_friday_evening_expects_friday():
    # 금요일 22:00 → 당일(금) 종가 기대. 주말로 넘어가지 않는다.
    assert scheduler._last_expected_trading_day(_kst(2026, 6, 19, 22, 0)).isoformat() == "2026-06-19"


def test_is_data_stale_false_right_after_sync_time_with_todays_data(monkeypatch):
    from datetime import date
    # 21:05에 당일(06-23) 데이터가 이미 있으면(방금 sync 완료) not stale
    monkeypatch.setattr(scheduler, "_newest_data_date", lambda: date(2026, 6, 23))
    assert scheduler._is_data_stale(_kst(2026, 6, 23, 21, 5)) is False


def test_is_data_stale_true_when_past_sync_time_without_todays_data(monkeypatch):
    from datetime import date
    # 22:00인데 아직 어제(06-22) 데이터뿐이면 오늘 sync가 안 된 것 — stale(캐치업 필요)
    monkeypatch.setattr(scheduler, "_newest_data_date", lambda: date(2026, 6, 22))
    assert scheduler._is_data_stale(_kst(2026, 6, 23, 22, 0)) is True


# ── 미러/정본 분기 ────────────────────────────────────────────────

def test_is_mirror_follows_env(monkeypatch):
    monkeypatch.delenv("DATA_MIRROR_REMOTE", raising=False)
    assert scheduler._is_mirror() is False
    monkeypatch.setenv("DATA_MIRROR_REMOTE", "root@host:/opt/simons")
    assert scheduler._is_mirror() is True


def test_run_update_pulls_in_mirror_mode(monkeypatch):
    monkeypatch.setenv("DATA_MIRROR_REMOTE", "root@host:/opt/simons")
    calls = {}
    monkeypatch.setattr(scheduler, "_run", lambda label, cmd: calls.setdefault("cmd", cmd))
    scheduler.run_update()
    assert calls["cmd"][-1].endswith("scripts/mirror_data.py")


def test_run_update_syncs_in_source_mode(monkeypatch):
    monkeypatch.delenv("DATA_MIRROR_REMOTE", raising=False)
    calls = {}
    monkeypatch.setattr(scheduler, "_run", lambda label, cmd: calls.setdefault("cmd", cmd))
    scheduler.run_update()
    assert calls["cmd"][-1].endswith("scripts/sync_data.py")
