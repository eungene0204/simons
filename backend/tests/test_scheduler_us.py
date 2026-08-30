"""scheduler_us.py — 미국 스케줄러의 시각 판정(증분 신선도 / 분기 전량 재수집 기한)."""

import importlib.util
from datetime import date, datetime
from pathlib import Path

import pytz

# scripts/는 backend/scripts/와 네임스페이스 충돌이 있어, 파일 경로로 직접 로드한다.
_PATH = Path(__file__).resolve().parents[2] / "scripts" / "scheduler_us.py"
_spec = importlib.util.spec_from_file_location("simons_scheduler_us", _PATH)
sched = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sched)

KST = pytz.timezone("Asia/Seoul")


def _kst(y, m, d, hour=8, minute=0):
    return KST.localize(datetime(y, m, d, hour, minute))


# ── 시세 증분: 기대 세션은 ET 기준 전날(07:00 KST에 그날 새벽 끝난 세션을 받는다) ──


def test_expected_trading_day_after_sync_is_previous_et_session():
    # 화요일 08:00(07:00 sync 이후) → 그날 새벽 끝난 월요일(ET) 세션
    assert sched._last_expected_trading_day(_kst(2026, 6, 23, 8, 0)).isoformat() == "2026-06-22"


def test_expected_trading_day_before_sync_steps_back_one_more():
    # 화요일 06:00(sync 전) → 월요일 세션은 아직 미적재, 기대치는 금요일
    assert sched._last_expected_trading_day(_kst(2026, 6, 23, 6, 0)).isoformat() == "2026-06-19"


def test_expected_trading_day_monday_morning_is_friday():
    # 월요일 08:00 → 일요일(휴장) 롤백 → 금요일 세션
    assert sched._last_expected_trading_day(_kst(2026, 6, 22, 8, 0)).isoformat() == "2026-06-19"


def test_expected_trading_day_weekend_is_friday():
    # 토·일 08:00 → 금요일 세션(토요일 새벽에 금요일 세션이 끝난다)
    assert sched._last_expected_trading_day(_kst(2026, 6, 20, 8, 0)).isoformat() == "2026-06-19"
    assert sched._last_expected_trading_day(_kst(2026, 6, 21, 8, 0)).isoformat() == "2026-06-19"


def test_data_stale_when_behind(monkeypatch):
    monkeypatch.setattr(sched, "_newest_data_date", lambda: date(2026, 6, 18))
    assert sched._is_data_stale(_kst(2026, 6, 20, 8, 0)) is True


def test_data_not_stale_when_current_so_weekend_is_skipped(monkeypatch):
    # 금요일 세션까지 있으면 일·월 아침 검사가 False → 주말엔 sync가 자연히 건너뛴다
    monkeypatch.setattr(sched, "_newest_data_date", lambda: date(2026, 6, 19))
    assert sched._is_data_stale(_kst(2026, 6, 21, 8, 0)) is False
    assert sched._is_data_stale(_kst(2026, 6, 22, 8, 0)) is False


def test_data_not_stale_when_not_seeded(monkeypatch):
    # 미시딩(파일 없음)이면 증분이 할 일이 없다 — 최초 시딩은 수동
    monkeypatch.setattr(sched, "_newest_data_date", lambda: None)
    assert sched._is_data_stale(_kst(2026, 6, 22, 8, 0)) is False


# ── 전량 재수집(분기 재무): 12주마다 일요일 09:00 KST ──────────────────────────


def test_full_refresh_due_on_sunday_after_12_weeks(monkeypatch):
    monkeypatch.setattr(sched, "_last_full_refresh_date", lambda: date(2026, 3, 1))
    # 2026-06-21은 일요일, 마지막 실행(3/1)에서 112일 경과
    assert sched._is_full_refresh_due(_kst(2026, 6, 21, 9, 0)) is True


def test_full_refresh_not_due_before_start_hour(monkeypatch):
    monkeypatch.setattr(sched, "_last_full_refresh_date", lambda: date(2026, 3, 1))
    assert sched._is_full_refresh_due(_kst(2026, 6, 21, 8, 59)) is False


def test_full_refresh_not_due_on_weekday(monkeypatch):
    monkeypatch.setattr(sched, "_last_full_refresh_date", lambda: date(2026, 3, 1))
    # 2026-06-22는 월요일 — 기한이 지났어도 일요일에만 돈다(9시간 작업, 휴장일 전용)
    assert sched._is_full_refresh_due(_kst(2026, 6, 22, 9, 0)) is False


def test_full_refresh_not_due_within_12_weeks(monkeypatch):
    # 2026-05-31 실행 → 6/21(일)은 21일 경과라 아직 아님
    monkeypatch.setattr(sched, "_last_full_refresh_date", lambda: date(2026, 5, 31))
    assert sched._is_full_refresh_due(_kst(2026, 6, 21, 9, 0)) is False


def test_full_refresh_not_due_without_marker(monkeypatch):
    # 마커 없음 = 미시딩이거나 기준일 초기화 전 — 돌리지 않는다
    monkeypatch.setattr(sched, "_last_full_refresh_date", lambda: None)
    assert sched._is_full_refresh_due(_kst(2026, 6, 21, 9, 0)) is False


def test_marker_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(sched, "_FULL_MARKER", tmp_path / ".last_full_refresh")
    assert sched._last_full_refresh_date() is None
    sched._mark_full_refresh(date(2026, 8, 24))
    assert sched._last_full_refresh_date() == date(2026, 8, 24)


# ── 마커 초기화: 시딩이 스케줄러 기동 뒤에 끝나도 기준일이 생겨야 한다 ──────────


def test_ensure_marker_initializes_after_seeding(tmp_path, monkeypatch):
    """시딩 완료 + 마커 없음 → 오늘로 초기화. 없으면 전량 재수집이 영영 안 돈다."""
    monkeypatch.setattr(sched, "_FULL_MARKER", tmp_path / ".last_full_refresh")
    monkeypatch.setattr(sched, "_newest_data_date", lambda: date(2026, 8, 21))
    sched._ensure_marker(date(2026, 8, 24))
    assert sched._last_full_refresh_date() == date(2026, 8, 24)


def test_ensure_marker_does_not_overwrite_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(sched, "_FULL_MARKER", tmp_path / ".last_full_refresh")
    monkeypatch.setattr(sched, "_newest_data_date", lambda: date(2026, 8, 21))
    sched._mark_full_refresh(date(2026, 3, 1))
    sched._ensure_marker(date(2026, 8, 24))
    assert sched._last_full_refresh_date() == date(2026, 3, 1)   # 기한 계산 기준일 보존


def test_ensure_marker_skips_when_not_seeded(tmp_path, monkeypatch):
    marker = tmp_path / ".last_full_refresh"
    monkeypatch.setattr(sched, "_FULL_MARKER", marker)
    monkeypatch.setattr(sched, "_newest_data_date", lambda: None)
    sched._ensure_marker(date(2026, 8, 24))
    assert not marker.exists()


# ── 미러 모드(로컬): DATA_MIRROR_REMOTE가 있으면 수집 대신 프로덕션 pull ──────────


def test_is_mirror_follows_env(monkeypatch):
    monkeypatch.delenv("DATA_MIRROR_REMOTE", raising=False)
    assert sched._is_mirror() is False
    monkeypatch.setenv("DATA_MIRROR_REMOTE", "root@example.com:/opt/simons")
    assert sched._is_mirror() is True
    monkeypatch.setenv("DATA_MIRROR_REMOTE", "   ")   # 공백만 = 미설정
    assert sched._is_mirror() is False


def test_run_update_mirror_pulls_us_dataset(monkeypatch):
    """미러 모드의 run_update는 수집 스크립트가 아니라 mirror_data.py --us를 부른다."""
    monkeypatch.setenv("DATA_MIRROR_REMOTE", "root@example.com:/opt/simons")
    calls = []
    monkeypatch.setattr(sched, "_run", lambda label, cmd, **kw: calls.append(cmd) or 0)
    assert sched.run_update() == 0
    assert len(calls) == 1
    assert calls[0][-2:] == ["scripts/mirror_data.py", "--us"]


def test_run_update_source_mode_collects(monkeypatch):
    """정본 모드(DATA_MIRROR_REMOTE 없음)는 기존대로 개별주 → ETF 증분을 돈다."""
    monkeypatch.delenv("DATA_MIRROR_REMOTE", raising=False)
    calls = []
    monkeypatch.setattr(sched, "_run", lambda label, cmd, **kw: calls.append(cmd) or 0)
    assert sched.run_update() == 0
    assert [c[-2:] for c in calls] == [
        ["scripts/backfill_us_stocks.py", "--update"],
        ["scripts/backfill_us_etf.py", "--update"],
    ]
