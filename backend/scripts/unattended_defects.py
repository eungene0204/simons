"""무인 실행 결함 대기열 — 뉴스 12시·속설 13시 무인 실행이 찾은 결함을 수리로 넘기는 장부.

2026-11-26 사용자 지시: 매일 새 전략을 만드는 목적은 엔진이 새 문장을 정확히 해석하는지
시험하는 것이다. 그런데 무인 실행이 찾은 결함은 보고서·제외 목록에만 쌓이고 수리로 이어지지
않아, 같은 결함(테마 위에 업종 칸이 낌)이 5번 반복됐다. 이 장부가 그 연결이다.

- 무인 실행은 **기록만** 한다(고치지 않는다 — 스킬 규칙 그대로). `add`로 한 줄씩 붙인다.
- 세션 시작 요약(`triage_traces.py --summary`)이 열린 건수를 함께 띄우고, `trace-triage`
  스킬이 목록을 읽어 수리 스킬로 넘긴다. 고친 뒤 `close`로 닫는다.
- 판정은 사람이 적은 증상 그대로다 — 이 파일은 문장을 읽어 아무것도 판정하지 않는다.

사용:
    python3 backend/scripts/unattended_defects.py add --source news --kind interpretation \\
        --slug 2026-11-25/04-pcb-rsi --prompt "<전략 문장>" --symptom "<증상 한 줄>" [--trace <id>]
    python3 backend/scripts/unattended_defects.py list [--all]
    python3 backend/scripts/unattended_defects.py close <id> --by "<커밋·사유>" [--status fixed|wontfix|duplicate]

kind: interpretation(해석) · data(데이터) · engine(엔진·백테스트) · other
표준 라이브러리만 쓴다(SessionStart 훅이 시스템 python3로 부른다).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

QUEUE = Path(__file__).resolve().parent.parent / "logs" / "triage" / "unattended_defects.jsonl"
KINDS = ("interpretation", "data", "engine", "other")
KIND_LABEL = {"interpretation": "해석", "data": "데이터", "engine": "엔진", "other": "기타"}
CLOSED = ("fixed", "wontfix", "duplicate")


def load(path: Path = QUEUE) -> List[Dict[str, Any]]:
    """한 줄 = 한 사건(추가 또는 닫기). 같은 id의 마지막 상태가 이긴다."""
    items: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("op") == "close" and rec.get("id") in items:
            items[rec["id"]].update(status=rec["status"], closed_by=rec.get("by"), closed_at=rec.get("at"))
        elif rec.get("op") == "add":
            items[rec["id"]] = {**rec, "status": "open"}
    return list(items.values())


def open_items(path: Path = QUEUE) -> List[Dict[str, Any]]:
    return [i for i in load(path) if i["status"] == "open"]


def summary(path: Path = QUEUE) -> Optional[str]:
    items = open_items(path)
    if not items:
        return None
    counts = {k: sum(1 for i in items if i.get("kind") == k) for k in KINDS}
    parts = "·".join(f"{KIND_LABEL[k]} {n}" for k, n in counts.items() if n)
    return f"[무인 실행 결함] 수리 대기 {len(items)}건({parts}) — /trace-triage 로 확인"


def _append(rec: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def add(source: str, kind: str, slug: str, prompt: str, symptom: str,
        trace: Optional[str] = None, path: Path = QUEUE) -> str:
    ident = hashlib.sha1(f"{source}|{slug}|{symptom}".encode()).hexdigest()[:8]
    if any(i["id"] == ident for i in load(path)):
        return ident  # 같은 건을 두 번 적지 않는다(무인 실행 재시도)
    _append({"op": "add", "id": ident, "at": dt.datetime.now().isoformat(timespec="seconds"),
             "source": source, "kind": kind, "slug": slug, "prompt": prompt,
             "symptom": symptom, "trace": trace}, path)
    return ident


def close(ident: str, by: str, status: str = "fixed", path: Path = QUEUE) -> bool:
    if not any(i["id"] == ident for i in load(path)):
        return False
    _append({"op": "close", "id": ident, "status": status, "by": by,
             "at": dt.datetime.now().isoformat(timespec="seconds")}, path)
    return True


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="무인 실행 결함 대기열")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--source", required=True, choices=("news", "myth", "other"))
    a.add_argument("--kind", required=True, choices=KINDS)
    a.add_argument("--slug", required=True, help="날짜/폴더 이름 등 사례 식별자")
    a.add_argument("--prompt", required=True, help="전략 문장(그대로)")
    a.add_argument("--symptom", required=True, help="증상 한 줄(무엇이 문장과 달랐나)")
    a.add_argument("--trace", default=None, help="trace_id(있으면)")
    ls = sub.add_parser("list")
    ls.add_argument("--all", action="store_true", help="닫힌 건도 표시")
    c = sub.add_parser("close")
    c.add_argument("id")
    c.add_argument("--by", required=True, help="고친 커밋 또는 닫는 사유")
    c.add_argument("--status", default="fixed", choices=CLOSED)
    p.add_argument("--queue", type=Path, default=QUEUE, help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    if args.cmd == "add":
        print(add(args.source, args.kind, args.slug, args.prompt, args.symptom, args.trace, args.queue))
    elif args.cmd == "close":
        if not close(args.id, args.by, args.status, args.queue):
            print(f"없는 id: {args.id}", file=sys.stderr)
            return 1
    else:
        items = load(args.queue) if args.all else open_items(args.queue)
        for i in items:
            tail = f" · trace {i['trace']}" if i.get("trace") else ""
            closed = f" → {i['status']} ({i.get('closed_by')})" if i["status"] != "open" else ""
            print(f"[{i['id']}] {i['at'][:10]} {i['source']}/{KIND_LABEL.get(i['kind'], i['kind'])} "
                  f"{i['slug']}{tail}{closed}\n  문장: {i['prompt']}\n  증상: {i['symptom']}")
        if not items:
            print("열린 결함 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
