"""mirror_data.py — rsync 명령 구성(정본=프로덕션, 단방향 미러)."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "mirror_data.py"
_spec = importlib.util.spec_from_file_location("simons_mirror_data", _PATH)
mirror_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mirror_data)

REMOTE = "root@example.com:/opt/simons"


def test_pull_orders_remote_then_local():
    cmd = mirror_data.build_rsync_cmd(remote=REMOTE, ssh_key=None, push=False, dry_run=False)
    # 마지막 두 인자가 source, dest. pull은 remote → local 순서.
    src, dst = cmd[-2], cmd[-1]
    assert src.endswith("data/ohlcv/") and src.startswith(REMOTE)
    assert dst.endswith("data/ohlcv/") and not dst.startswith(REMOTE)


def test_push_orders_local_then_remote():
    cmd = mirror_data.build_rsync_cmd(remote=REMOTE, ssh_key=None, push=True, dry_run=False)
    src, dst = cmd[-2], cmd[-1]
    assert not src.startswith(REMOTE)
    assert dst.startswith(REMOTE)


def test_ssh_key_included():
    cmd = mirror_data.build_rsync_cmd(remote=REMOTE, ssh_key="~/.ssh/k", push=False, dry_run=False)
    i = cmd.index("-e")
    assert "ssh -i" in cmd[i + 1] and "/.ssh/k" in cmd[i + 1]


def test_dry_run_adds_flag():
    cmd = mirror_data.build_rsync_cmd(remote=REMOTE, ssh_key=None, push=False, dry_run=True)
    assert "--dry-run" in cmd


def test_empty_remote_raises():
    with pytest.raises(ValueError):
        mirror_data.build_rsync_cmd(remote="", ssh_key=None, push=False, dry_run=False)


def test_stall_timeouts_always_present():
    """SSH 행 시 무기한 스톨 방지(2026-08-04 스케줄러 pull 30시간 좀비 회귀).

    rsync --timeout(무전송 중단)과 SSH keepalive(죽은 연결 감지)는 키 유무와
    무관하게 항상 포함돼야 한다.
    """
    for ssh_key in (None, "~/.ssh/k"):
        cmd = mirror_data.build_rsync_cmd(remote=REMOTE, ssh_key=ssh_key, push=False, dry_run=False)
        assert f"--timeout={mirror_data._RSYNC_STALL_TIMEOUT_S}" in cmd
        assert mirror_data._RSYNC_STALL_TIMEOUT_S >= 300  # 큰 델타 정상 전송이 120초에 끊기던 실측
        ssh_arg = cmd[cmd.index("-e") + 1]
        assert "ServerAliveInterval" in ssh_arg
        assert "ServerAliveCountMax" in ssh_arg


def test_run_with_retries_resumes_after_stall_exit_codes(monkeypatch):
    """스톨(exit 10)로 끊겨도 이어서 재시도하고, 성공하면 0을 돌려준다(2026-08-17 실측 4회 stall)."""
    calls = {"n": 0}

    class _R:
        def __init__(self, rc):
            self.returncode = rc

    def fake_run(cmd):
        calls["n"] += 1
        return _R(10 if calls["n"] < 3 else 0)

    monkeypatch.setattr(mirror_data.subprocess, "run", fake_run)
    assert mirror_data.run_with_retries(["rsync"], max_attempts=5, delay_s=0) == 0
    assert calls["n"] == 3


def test_run_with_retries_does_not_retry_non_network_errors(monkeypatch):
    calls = {"n": 0}

    class _R:
        returncode = 23  # 부분 전송 오류(권한 등) — 재시도해도 같다

    def fake_run(cmd):
        calls["n"] += 1
        return _R()

    monkeypatch.setattr(mirror_data.subprocess, "run", fake_run)
    assert mirror_data.run_with_retries(["rsync"], max_attempts=5, delay_s=0) == 23
    assert calls["n"] == 1
