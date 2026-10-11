#!/usr/bin/env python3
"""PreToolUse(Bash) 가드 — 메모리에 사고로 남은 명령을 실행 전에 막는다.

막는 것(각각 실제 사고 근거가 있다):
1. 공유 디렉터리 일괄 스테이징 — `git add -A/--all/./-u/:/`, `git commit -a`, `git stash`.
   2026-09-21 병렬 세션의 미커밋 작업 8파일을 쓸어 담아 푸시·배포 직전까지 갔다
   (memory: feedback_no_git_add_all_shared_dir).
2. 로컬 parquet을 원격으로 올리기 — rsync/scp의 목적지가 원격(host:)이고 parquet 데이터
   경로를 실어 보낼 때. 방향은 프로덕션 → 로컬 하나뿐이다(CLAUDE.md, 2026-09-21 사고).

입력은 Claude가 실행하려는 셸 명령이다(사용자 자연어가 아니다). 판정 실패는 통과로 둔다
(fail-open) — 가드가 작업을 막는 쪽으로 고장 나면 안 된다.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from typing import Iterator, List, Optional

_SEPARATORS = {"&&", "||", ";", "|", "&", "\n", "(", ")", ";;", "|&"}
_LINE_SPLIT = re.compile(r"&&|\|\||;|\||\n")
_PREFIX_WORDS = {"env", "sudo", "command", "exec", "nohup", "time"}
_SHELLS = {"bash", "sh", "zsh"}
_GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree"}
_BULK_ADD = {"-A", "--all", ".", "-u", "--update", ":/", "*", "./"}
# commit에서 값을 받는 옵션 — 그 값(메시지 등)은 플래그로 읽지 않는다.
_COMMIT_WITH_VALUE = {"-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date",
                      "--template", "--reuse-message", "--reedit-message", "--fixup", "--squash",
                      "--cleanup", "--trailer"}
_COMMIT_SHORT_VALUE = set("mFCct")
_RSYNC_WITH_VALUE = {"-e", "--rsh", "--exclude", "--include", "--exclude-from", "--include-from",
                     "--files-from", "--filter", "-f", "--rsync-path", "-i", "-P", "-o", "-F", "-J"}


def _segments(command: str) -> Iterator[List[str]]:
    """명령을 따옴표를 지키며 단순 명령 단위로 끊는다.

    따옴표 안의 줄바꿈(히어독 커밋 메시지 `"$(cat <<'EOF' …)"`)은 한 낱말로 남는다.
    전체 해석이 실패하면(짝 안 맞는 따옴표) 줄 단위로 물러나 가능한 만큼 본다.
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
        lex.whitespace = " \t\r"
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        for part in _LINE_SPLIT.split(command):
            try:
                yield shlex.split(part)
            except ValueError:
                continue
        return
    segment: List[str] = []
    for token in tokens:
        if token in _SEPARATORS or set(token) <= set("();|&\n"):
            if segment:
                yield segment
            segment = []
        else:
            segment.append(token)
    if segment:
        yield segment


def _strip_prefix(tokens: List[str]) -> List[str]:
    """`env X=1 git …`·`/usr/bin/git …` → ['git', …]."""
    i = 0
    while i < len(tokens) and (tokens[i] in _PREFIX_WORDS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i])):
        i += 1
    rest = tokens[i:]
    if rest:
        rest = [os.path.basename(rest[0])] + rest[1:]
    return rest


def _git_subcommand(tokens: List[str]) -> Optional[tuple]:
    """['git', '-C', 'x', 'add', '-A'] → ('add', ['-A'])."""
    # 단순 명령의 첫 낱말이 git인 것만 본다 — 메시지·echo 본문 속 "git add -A" 글자는 명령이 아니다.
    if not tokens or tokens[0] != "git":
        return None
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        i += 2 if tokens[i] in _GIT_GLOBAL_WITH_VALUE else 1
    if i >= len(tokens):
        return None
    return tokens[i], tokens[i + 1:]


def _commit_all(args: List[str]) -> bool:
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == "--":
            return False
        if arg in ("-a", "--all"):
            return True
        if arg in _COMMIT_WITH_VALUE:
            skip = True
            continue
        if arg.startswith("-") and not arg.startswith("--"):
            for pos, ch in enumerate(arg[1:]):
                if ch == "a":
                    return True
                if ch in _COMMIT_SHORT_VALUE:
                    skip = pos == len(arg) - 2  # 값이 다음 낱말이면 건너뛴다
                    break
    return False


def _bulk_git(tokens: List[str]) -> Optional[str]:
    parsed = _git_subcommand(tokens)
    if not parsed:
        return None
    sub, args = parsed
    if sub == "add" and any(a in _BULK_ADD for a in args):
        return "git add 일괄 스테이징"
    if sub == "commit" and _commit_all(args):
        return "git commit -a(추적 파일 일괄 스테이징)"
    if sub == "stash" and not (args and args[0] in ("list", "show")):
        return "git stash(병렬 세션의 미커밋 작업까지 치운다)"
    return None


def _uploads_data(source: str) -> bool:
    """로컬 원천이 parquet 데이터(또는 그것을 품은 상위 경로)인가."""
    path = os.path.normpath(source)
    return (path in (".", "data") or path.startswith("data/") or path.startswith("./data")
            or ".parquet" in path or "ohlcv" in path)


def _parquet_upload(tokens: List[str]) -> Optional[str]:
    if not tokens or tokens[0] not in ("rsync", "scp"):
        return None
    operands: List[str] = []
    skip = False
    for token in tokens[1:]:
        if skip:
            skip = False
        elif token in _RSYNC_WITH_VALUE:
            skip = True
        elif not token.startswith("-"):
            operands.append(token)
    if len(operands) < 2:
        return None
    *sources, dest = operands
    if ":" not in dest or dest.startswith("/"):
        return None
    if any(":" not in s and _uploads_data(s) for s in sources):
        return f"로컬 parquet 데이터를 원격({dest})으로 전송"
    return None


def check(command: str, _depth: int = 0) -> Optional[str]:
    for raw in _segments(command or ""):
        tokens = _strip_prefix(raw)
        if tokens and tokens[0] in _SHELLS and "-c" in tokens and _depth < 2:
            idx = tokens.index("-c")
            if idx + 1 < len(tokens):
                reason = check(tokens[idx + 1], _depth + 1)
                if reason:
                    return reason
        reason = _bulk_git(tokens) or _parquet_upload(tokens)
        if reason:
            return reason
    return None


_ADVICE = {
    "git": ("공유 워킹트리라 병렬 세션의 미커밋 작업이 섞인다. `git status --short`로 확인한 뒤 내가 만진 경로만 "
            "명시해 add하고, 섞인 파일은 블롭 스테이징으로 내 변경만 담는다(memory: feedback_no_git_add_all_shared_dir)."),
    "rsync": ("parquet 방향은 프로덕션 → 로컬 하나뿐이다. 백필·수리는 프로덕션에서 실행하고 로컬은 "
              "`scripts/mirror_data.py`로 pull 한다(CLAUDE.md 필수 규칙)."),
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = (payload.get("tool_input") or {}).get("command") or ""
        reason = check(command)
    except Exception:  # noqa: BLE001 — 가드 고장이 작업을 막지 않는다
        return 0
    if not reason:
        return 0
    advice = _ADVICE["rsync" if "parquet" in reason else "git"]
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": f"[guard] {reason} 차단 — {advice}",
    }}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
