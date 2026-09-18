"""메모리 가드 — 컨테이너 한계에 닿기 전에 백테스트를 끊는다.

2026-09-18: 한계를 넘으면 커널이 무엇을 죽일지 고른다. Phase1 워커가 걸리면 사용자 문구로
바뀌지만 본체가 걸리면 백엔드 컨테이너가 통째로 죽어 사용자는 문구 없이 연결 끊김만 본다.
"""

import time

import pytest

from engine import memory_guard
from engine.phase1_pool import RESOURCE_EXHAUSTED_MESSAGE, BacktestResourceError


def _fake_cgroup(monkeypatch, *, limit: str, anon: int):
    files = {
        memory_guard._CGROUP_V2_MAX: limit,
        memory_guard._CGROUP_V2_STAT: f"anon {anon}\nfile 12345\n",
    }
    monkeypatch.setattr(memory_guard, "_read", lambda path: files.get(path))


def test_limit_and_usage_read_from_cgroup_v2(monkeypatch):
    _fake_cgroup(monkeypatch, limit="2000\n", anon=1500)
    assert memory_guard.limit_bytes() == 2000
    assert memory_guard.anon_bytes() == 1500


def test_unlimited_container_has_no_trip_point(monkeypatch):
    """한계가 없으면(로컬 dev) 가드는 아무 일도 하지 않는다."""
    _fake_cgroup(monkeypatch, limit="max\n", anon=1500)
    assert memory_guard.limit_bytes() is None
    assert memory_guard.trip_bytes() is None
    assert memory_guard.guarded(lambda: "실행됨") == "실행됨"


def test_v1_unlimited_sentinel_is_not_a_limit(monkeypatch):
    """cgroup v1은 '무제한'을 거대한 수로 적는다 — 그걸 한계로 읽으면 가드가 영영 안 걸린다."""
    monkeypatch.setattr(memory_guard, "_read", lambda path: {
        memory_guard._CGROUP_V1_MAX: str((1 << 62) + 4096),
    }.get(path))
    assert memory_guard.limit_bytes() is None


def test_threshold_env_override(monkeypatch):
    _fake_cgroup(monkeypatch, limit="1000", anon=0)
    monkeypatch.setenv("BACKTEST_MEMORY_GUARD_PCT", "0.5")
    assert memory_guard.trip_bytes() == 500
    monkeypatch.setenv("BACKTEST_MEMORY_GUARD_PCT", "이상한값")
    assert memory_guard.trip_bytes() == 900          # 기본 0.9로 되돌아온다


def test_guard_stops_run_before_limit_with_user_message(monkeypatch, capsys):
    """중단선을 넘으면 실행 중인 작업에 사용자 문구 예외가 꽂힌다."""
    _fake_cgroup(monkeypatch, limit="1000", anon=950)   # 중단선 900 초과
    monkeypatch.setattr(memory_guard.threading, "get_ident", memory_guard.threading.get_ident)

    def long_running():
        for _ in range(400):                            # 파이썬 루프 = 예외가 꽂힐 수 있는 지점
            time.sleep(0.01)
        return "끝까지 돌았다"

    with pytest.raises(BacktestResourceError) as exc:
        memory_guard.guarded(long_running, interval_s=0.05)
    assert str(exc.value) == RESOURCE_EXHAUSTED_MESSAGE
    out = capsys.readouterr().out
    assert "[BT-MEM]" in out and "중단" in out


def test_guard_does_not_disturb_runs_below_the_line(monkeypatch):
    _fake_cgroup(monkeypatch, limit="1000", anon=100)
    assert memory_guard.guarded(lambda: time.sleep(0.15) or "정상", interval_s=0.05) == "정상"


def test_pending_exception_is_cleared_when_run_finishes_first(monkeypatch):
    """짧은 작업이 먼저 끝났으면 심어 둔 예외를 거둔다 — 다음 코드가 엉뚱하게 죽지 않도록."""
    _fake_cgroup(monkeypatch, limit="1000", anon=950)
    with pytest.raises(BacktestResourceError):
        memory_guard.guarded(lambda: time.sleep(0.2) or "ok", interval_s=0.05)
    # 가드 밖에서는 예외가 남아 있지 않다.
    total = 0
    for i in range(10000):
        total += i
    assert total == 49995000
