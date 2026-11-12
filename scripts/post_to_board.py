"""널스탁 자유게시판(https://www.nullstock.im/board)에 업데이트 소식 글을 올린다.

초안 파일(JSON) 하나 = 글 하나. 초안은 저장소 밖 `~/.config/nullstock-board/`에 둔다 — 수정·삭제
비밀번호가 들어 있어서다. 스킬: `.claude/skills/board-release-note/SKILL.md`.

    uv run python scripts/post_to_board.py new <slug>              # 초안 틀 생성(비밀번호 무작위)
    uv run python scripts/post_to_board.py check <draft.json>      # 게시 전 검사만(전송 안 함)
    uv run python scripts/post_to_board.py post <draft.json>       # 게시 → post_id·게시 시각 기록
    uv run python scripts/post_to_board.py list                    # 대기·게시 초안 목록
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://www.nullstock.im"
DRAFT_DIR = Path.home() / ".config" / "nullstock-board"
CATEGORIES = ("공지", "정보", "질문", "건의", "자유")

# 게시판 서버 검열(lib/board/rules.ts::moderate)과 CLAUDE.md 규제 안전 표현. 서버가 거절하기 전에
# 여기서 먼저 막는다 — 글은 LLM 출력이 아니라 우리가 쓴 고지문이라 표현 검사가 정당하다.
_BANNED = [
    (r"추천", "추천 표현(규제 안전 원칙)"),
    (r"유망|유리합니다|기대됩니다|권장", "전망·권유 표현(규제 안전 원칙)"),
    (r"수익[\s\S]{0,20}보장|보장[\s\S]{0,20}수익", "수익 보장 표현(규제·게시판 검열)"),
    (r"(?:무료|수익|대출|카지노|도박|성인)[\s\S]{0,20}(?:가입|홍보|문의|입장|보장)", "게시판 상업 검열 패턴"),
    (r"<\/?[a-z][^>]*>", "HTML(게시판이 거절)"),
    (r"\bSimons\b|시몬스", "브랜드명 — 사용자 노출은 '널스탁'"),
    (r"[a-z]+_[a-z_]+|\.py\b|\.tsx?\b|v\d+\.\d+", "내부 식별자·파일명·버전 번호"),
]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, draft: dict) -> None:
    path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def problems(draft: dict) -> list[str]:
    out = []
    title, body = draft.get("title") or "", draft.get("body") or ""
    if not 1 <= len(title.strip()) <= 120:
        out.append("제목은 1~120자")
    if not 1 <= len(body.strip()) <= 10000:
        out.append("본문은 1~10000자")
    if draft.get("category") not in CATEGORIES:
        out.append(f"분류는 {CATEGORIES} 중 하나")
    pw = draft.get("password") or ""
    if not 4 <= len(pw) <= 64:
        out.append("비밀번호는 4~64자")
    if len(re.findall(r"https?://|www\.", body)) > 3:
        out.append("링크 3개 초과(게시판이 거절)")
    for pattern, why in _BANNED:
        hit = re.search(pattern, title + "\n" + body)
        if hit:
            out.append(f"{why}: '{hit.group(0)}'")
    if not draft.get("deploy"):
        out.append("deploy(배포 확인 근거: 커밋·CI 실행 URL)가 비어 있다 — 배포 전엔 게시하지 않는다")
    return out


def cmd_new(slug: str) -> None:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    DRAFT_DIR.chmod(0o700)
    path = DRAFT_DIR / f"{dt.date.today().isoformat()}-{slug}.json"
    if path.exists():
        sys.exit(f"이미 있다: {path}")
    _save(path, {
        "status": "draft", "kind": "bugfix | feature", "commits": [], "deploy": None,
        "category": "공지", "nickname": "널스탁", "title": "", "body": "",
        "password": secrets.token_urlsafe(18), "post_id": None, "posted_at": None,
    })
    print(path)


def cmd_check(path: Path) -> int:
    found = problems(_load(path))
    for p in found:
        print("✗", p)
    print("✓ 게시 가능" if not found else f"{len(found)}건 — 고친 뒤 다시 검사")
    return 1 if found else 0


def cmd_post(path: Path) -> int:
    draft = _load(path)
    if draft.get("post_id"):
        sys.exit(f"이미 게시됨: {BASE}/board?id={draft['post_id']}")
    if cmd_check(path):
        return 1
    payload = {"action": "create", "kind": "post", "category": draft["category"],
               "title": draft["title"], "body": draft["body"],
               "nickname": draft["nickname"], "password": draft["password"]}
    req = urllib.request.Request(
        f"{BASE}/api/board", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Origin": BASE,
                 "User-Agent": "nullstock-board-release-note/1"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            result = json.loads(res.read())
    except urllib.error.HTTPError as e:
        print(f"게시 실패 {e.code}: {e.read().decode('utf-8', 'replace')}")
        return 1
    draft.update(status="posted", post_id=result["id"],
                 posted_at=dt.datetime.now().astimezone().isoformat(timespec="seconds"))
    _save(path, draft)
    print(f"게시됨: {BASE}/board?id={result['id']}")
    return 0


def cmd_list() -> None:
    for path in sorted(DRAFT_DIR.glob("*.json")):
        d = _load(path)
        print(f"{d.get('status', '?'):8} {path.name}  {d.get('title', '')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("new").add_argument("slug")
    sub.add_parser("check").add_argument("draft", type=Path)
    sub.add_parser("post").add_argument("draft", type=Path)
    sub.add_parser("list")
    args = ap.parse_args()
    if args.cmd == "new":
        cmd_new(args.slug)
    elif args.cmd == "check":
        return cmd_check(args.draft)
    elif args.cmd == "post":
        return cmd_post(args.draft)
    else:
        cmd_list()
    return 0


if __name__ == "__main__":
    sys.exit(main())
