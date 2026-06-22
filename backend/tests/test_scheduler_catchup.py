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


def _kst(y, m, d):
    return KST.localize(datetime(y, m, d, 9, 0))


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
