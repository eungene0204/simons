"""의도 분류 커버리지 리포트 — "무엇을 못 알아듣나"를 추측 대신 데이터로 본다.

관찰 계층이 남긴 Trace(logs/agent_traces/*.jsonl)에서 분류·일반답변 레인 span만 골라
라벨 분포와, 예상 못한 질문이 떨어진 지점의 실제 발화를 뽑는다.

이 스크립트는 **읽기 전용**이다 — Trace를 고치지도, 실행 경로를 건드리지도 않는다.

사용:
    python backend/scripts/report_intent_coverage.py               # 전체 기간
    python backend/scripts/report_intent_coverage.py --days 7      # 최근 7일
    python backend/scripts/report_intent_coverage.py --intent UNKNOWN --limit 50
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

_TRACE_DIR = Path(__file__).resolve().parent.parent / "logs" / "agent_traces"

_CLASSIFY_SPAN = "Classifier · 의도 분류"
_GENERAL_SPAN = "General · 일반 지식 답변"

# 알아들었어도 정형 안내로 끊기는 라벨 — 게이트가 넓으면 정당한 질문도 여기 쌓인다.
_GATED_INTENTS = frozenset({
    "STOCK_ANALYSIS", "STOCK_PICK", "STRATEGY_PICK",
    "PERSONAL_ADVICE", "LIVE_TRADING", "UNSUPPORTED_FEATURE",
})
# 아예 못 알아들은 지점.
_MISS_INTENTS = frozenset({"UNKNOWN", "OFF_TOPIC"})


def _trace_files(days: Optional[int]) -> List[Path]:
    if not _TRACE_DIR.exists():
        return []
    files = sorted(_TRACE_DIR.glob("*.jsonl"))
    if days is None:
        return files
    cutoff = dt.date.today() - dt.timedelta(days=days - 1)
    return [f for f in files if f.stem >= cutoff.isoformat()]


def _walk(node: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from _walk(child)


def _spans(files: List[Path], name: str) -> Iterator[Dict[str, Any]]:
    """이름이 일치하는 span을 Trace 트리 전체에서 훑는다(중첩 포함)."""
    for path in files:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                span = record.get("span")
                if not isinstance(span, dict):
                    continue
                for node in _walk(span):
                    if node.get("name") == name:
                        yield node


def _row(node: Dict[str, Any]) -> Dict[str, Any]:
    inputs = node.get("inputs") or {}
    outputs = node.get("outputs") or {}
    metadata = node.get("metadata") or {}
    return {
        "query": inputs.get("query"),
        "intent": outputs.get("intent"),
        "reason": outputs.get("reason"),
        "deterministic": outputs.get("deterministic"),
        "failed": outputs.get("interpretation_failed"),
        "fact_metric": outputs.get("fact_metric"),
        "list_scope": outputs.get("list_scope"),
        "turns": metadata.get("history_turns"),
        "active_strategy": metadata.get("active_strategy"),
        "ms": node.get("duration_ms"),
    }


def _is_gated(row: Dict[str, Any]) -> bool:
    """정형 안내로 끊겼는가.

    라벨만 보면 안 된다 — 규제 게이트는 라벨과 **직교하는 축**으로 갈린다(2026-08-11).
    같은 STOCK_ANALYSIS라도 값 조회(fact_metric)가, 같은 STOCK_PICK이라도 소속 목록
    (list_scope)이 성립한 턴은 사실로 답한 것이지 끊긴 것이 아니다. 라벨만 세면
    게이트 분리의 효과가 리포트에서 보이지 않는다.
    """
    if row.get("fact_metric") or row.get("list_scope"):
        return False
    return row.get("intent") in _GATED


def _print_table(title: str, counter: Counter, total: int) -> None:
    print(f"\n{title}  (총 {total}건)")
    if not total:
        print("  — 기록 없음")
        return
    width = max((len(str(k)) for k in counter), default=0)
    for key, count in counter.most_common():
        share = count / total * 100
        print(f"  {str(key):<{width}}  {count:>5}  {share:5.1f}%")


def main() -> int:
    parser = argparse.ArgumentParser(description="의도 분류 커버리지 리포트")
    parser.add_argument("--days", type=int, default=None, help="최근 N일만 (기본: 전체)")
    parser.add_argument("--intent", default=None, help="이 라벨의 발화만 나열")
    parser.add_argument("--limit", type=int, default=30, help="발화 나열 개수")
    args = parser.parse_args()

    files = _trace_files(args.days)
    if not files:
        print(f"Trace 파일이 없습니다: {_TRACE_DIR}")
        print("AGENT_TRACE_LOCAL=0으로 꺼져 있거나, 아직 분류 요청이 없었습니다.")
        return 1

    rows = [_row(node) for node in _spans(files, _CLASSIFY_SPAN)]
    print(f"대상 파일 {len(files)}개: {files[0].stem} ~ {files[-1].stem}")

    if not rows:
        print(f"\n'{_CLASSIFY_SPAN}' span이 없습니다 — 계측 이후의 요청이 아직 없습니다.")
        return 1

    _print_table("라벨 분포", Counter(r["intent"] for r in rows), len(rows))

    # 못 알아들음도 축을 본다(_is_gated와 같은 이유) — UNKNOWN 라벨이어도 값 조회·소속
    # 목록으로 답한 턴은 실패가 아니다.
    miss = [
        r for r in rows
        if r["intent"] in _MISS_INTENTS and not (r.get("fact_metric") or r.get("list_scope"))
    ]
    gated = [r for r in rows if _is_gated(r)]
    facts = [r for r in rows if r.get("fact_metric") or r.get("list_scope")]
    failed = [r for r in rows if r["failed"]]
    print(f"\n못 알아들음(UNKNOWN·OFF_TOPIC): {len(miss)}건 ({len(miss)/len(rows)*100:.1f}%)")
    print(f"정형 안내로 끊김(규제 게이트): {len(gated)}건 ({len(gated)/len(rows)*100:.1f}%)")
    print(f"값 조회로 답함(게이트 통과): {len(facts)}건 ({len(facts)/len(rows)*100:.1f}%)")
    print(f"해석 실패(LLM 미가용·출력 파손): {len(failed)}건")

    listing = (
        [r for r in rows if r["intent"] == args.intent] if args.intent
        else miss + gated
    )
    if facts and not args.intent:
        print(f"\n── 값 조회로 답한 문항 (라벨은 게이트지만 축이 열어준 것) ──")
        for row in facts[-args.limit:]:
            print(f"  [{row['fact_metric'] or row['list_scope']}] {row['query']!r}")
    header = f"'{args.intent}' 발화" if args.intent else "못 알아들었거나 끊긴 발화"
    print(f"\n{header} — 최근 {min(args.limit, len(listing))}건")
    for row in listing[-args.limit:]:
        flag = "!" if row["failed"] else " "
        print(f" {flag} [{row['intent']}] {row['query']!r}")
        print(f"     turns={row['turns']} 전략진행={row['active_strategy']} "
              f"결정론={row['deterministic']} 근거={row['reason']!r}")

    general = [_row(node) for node in _spans(files, _GENERAL_SPAN)]
    if general:
        sources = Counter(
            (node.get("outputs") or {}).get("source")
            for node in _spans(files, _GENERAL_SPAN)
        )
        _print_table("일반 지식 답변 경로", sources, len(general))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
