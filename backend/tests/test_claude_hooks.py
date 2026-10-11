"""Claude Code 가드 훅(.claude/hooks/guard_bash.py) 회귀.

메모리에 사고로 남은 명령(공유 디렉터리 일괄 스테이징·로컬 parquet 업로드)은 막고,
정상 명령과 명령이 아닌 글자(커밋 메시지 본문)는 통과시킨다.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "guard_bash.py"
_spec = importlib.util.spec_from_file_location("guard_bash", _HOOK)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


@pytest.mark.parametrize("command", [
    "git add -A",
    "git add .",
    "git add --all && git commit -m x",
    "cd /repo && git -C backend add -u",
    "git commit -am 'fix'",
    "git commit --all -m x",
    "git stash",
    "git stash push -m wip",
    "rsync -av data/ohlcv/ root@1.2.3.4:/opt/simons/data/ohlcv/",
    "scp data/index/KS11.parquet box:/opt/simons/data/index/",
    # 계약 검토(2026-10-11)가 실측으로 찾은 미탐
    "git commit -a -m \"$(cat <<'EOF'\nfix: x\n\nbody\nEOF\n)\"",
    "env X=1 git add -A",
    "/usr/bin/git add -A",
    "(git add -A)",
    "bash -c 'git add -A'",
    "git status\ngit add -A",
    "rsync -av data/ box:/opt/simons/data/",
    "rsync -av ./ box:/opt/simons/",
    "rsync -av -e 'ssh -i key' data/ohlcv/ root@h:/opt/simons/data/ohlcv/",
])
def test_blocks_incident_commands(command):
    assert guard.check(command)


@pytest.mark.parametrize("command", [
    "git add backend/scripts/triage_traces.py .claude/hooks/guard_bash.py",
    "git commit -m 'docs: git add -A 금지 훅'",
    "git commit -m \"$(cat <<'EOF'\nfeat: 가드\n\n이제 git add -A 를 막는다\nEOF\n)\"",
    "git status --short",
    "git stash list",
    "git commit --amend --no-edit",
    "echo 'git add -A'",
    "rsync -av root@1.2.3.4:/opt/simons/data/ohlcv/ data/ohlcv/",
    "rsync -av docs/ box:/opt/simons/docs/",
    "uv run python scripts/mirror_data.py",
    # 계약 검토(2026-10-11)가 실측으로 찾은 오탐
    "git commit -m \"$(cat <<'EOF'\nfix\n\ngit add -A 금지\ngit stash\nEOF\n)\"",
    "git commit -m '-a 금지'",
    "git commit -ma",
    "rsync --exclude data/ohlcv ./src/ box:/opt/simons/src/",
])
def test_allows_normal_commands(command):
    assert guard.check(command) is None


def _run(command):
    out = subprocess.run([sys.executable, str(_HOOK)], input=json.dumps({"tool_input": {"command": command}}),
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_hook_protocol_deny_and_pass():
    decision = json.loads(_run("git add -A"))["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "블롭 스테이징" in decision["permissionDecisionReason"]
    assert _run("git status") == ""


def test_broken_input_fails_open():
    out = subprocess.run([sys.executable, str(_HOOK)], input="not json", capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout == ""
