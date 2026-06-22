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
