"""Trace 실패 분류(triage) — "어제 무엇이 실패했나"를 구조 신호로 묶는다.

관찰 계층이 남긴 Trace(logs/agent_traces/*.jsonl)를 훑어, 실패 후보를 **신호 종류 ×
판별 키**로 묶고 묶음마다 대표 사례(trace_id·발화)를 붙인다. 분류 로직은
observability/triage.py(운영 콘솔 실패 분류 탭과 공용)이고, 이 파일은 CLI·리포트다.
고치는 일은 이 리포트를 입력으로 받는 `trace-triage` 스킬 → `strategy-interpretation-fix`
스킬이 한다.

판정 계약(CLAUDE.md 대원칙 1):
- 판정은 **시스템이 남긴 구조 필드만** 본다 — span 오류, 검증기 보고(errors·
  unsupported_features), 컴파일러 dropped·pending_conditions, Responder의
  clarification_priority, 우리가 낸 질문 문장의 동일성.
- 사용자 원문(user_input)은 **표본으로 옮겨 적기만** 한다. 원문을 읽어 실패 여부·종류를
  판정하지 않는다(정규식·어휘 목록 금지).
- 오류 문자열에서 예외 클래스명을 떼는 것은 시스템 출력의 표기 정규화다.

보관: 리포트에는 발화 원문이 들어가므로 Trace와 같은 정책(원문 3일, retention.RETENTION_DAYS)을
따른다 — 리포트 이름은 담은 Trace 중 가장 오래된 날짜이고, 기한 지난 리포트는 어떤 모드로
실행하든(--summary 포함) 먼저 지운다.

이 스크립트는 **읽기 전용**이다 — Trace를 고치지도, 실행 경로를 건드리지도 않는다.

사용:
    python backend/scripts/triage_traces.py                 # 보관 중인 전체(최대 3일)
    python backend/scripts/triage_traces.py --days 1        # 오늘만
    python backend/scripts/triage_traces.py --summary       # 한 줄 요약(SessionStart 훅용)

Trace 하나의 상세(레이어별 칸·오류·LLM 원출력)는 strategy-interpretation-fix 스킬의
`trace_turn.py --trace-id <id>`로 본다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from observability.retention import RETENTION_DAYS  # noqa: E402
from observability.triage import TIERS, load  # noqa: E402

_REPORT_DIR = _BACKEND / "logs" / "triage"


def render_markdown(result: Dict[str, Any]) -> str:
    groups, total = result["groups"], result["total"]
    span_text = " ~ ".join(result["range"]) if result["range"] else "없음"
    lines = [
        f"# Trace triage — {span_text}",
        "",
        f"Trace {total}건 · 실패 후보 그룹 {len(groups)}개. 판정은 구조 신호만(원문은 표본으로 옮겨 적기만).",
        "원문이 들어 있으므로 Trace와 같은 3일 보관 정책을 따른다.",
    ]
    for tier in TIERS:
        tier_groups = [g for g in groups if g["tier"] == tier]
        if not tier_groups:
            continue
        lines += ["", f"## {tier} ({sum(g['count'] for g in tier_groups)}건 / {len(tier_groups)}그룹)"]
        for g in tier_groups:
            lines += ["", f"### [{g['signal']}] {g['key']} — {g['count']}건 · 세션 {g['sessions']} · {', '.join(g['environments'])}",
                      f"_{g['label']}_"]
            for s in g["samples"]:
                lines.append(f"- `{s['trace_id']}` {s['ts'][:16] if s['ts'] else ''} {s['turn_kind'] or ''} · {s['model'] or ''}")
                if s["user_input"]:
                    lines.append(f"  - 입력: {s['user_input']}")
                if s["detail"]:
                    lines.append(f"  - 근거: {s['detail']}")
    return "\n".join(lines) + "\n"


def render_summary(groups: List[Dict[str, Any]]) -> str:
    counts = {tier: sum(g["count"] for g in groups if g["tier"] == tier) for tier in TIERS}
    defect_groups = sum(1 for g in groups if g["tier"] == "결함 후보")
    if not any(counts.values()):
        return "[trace-triage] 보관 중인 Trace에 실패 후보 없음"
    parts = " · ".join(f"{tier} {n}" for tier, n in counts.items() if n)
    return (f"[trace-triage] 최근 Trace 실패 후보 — {parts} (결함 후보 {defect_groups}그룹). "
            "/trace-triage 로 묶음별 확인·수정")


def sweep_reports(report_dir: Path, today: dt.date) -> None:
    """리포트에도 원문이 있으므로 Trace와 같은 기한으로 지운다.

    리포트 이름은 담은 Trace 중 가장 오래된 날짜다 — 그 Trace와 같은 날 지워진다.
    """
    if not report_dir.exists():
        return
    cutoff = today - dt.timedelta(days=RETENTION_DAYS - 1)
    for path in report_dir.iterdir():
        try:
            file_date = dt.date.fromisoformat(path.stem)
        except ValueError:
            continue
        if file_date < cutoff:
            path.unlink(missing_ok=True)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Trace 실패 분류(triage) 리포트")
    parser.add_argument("--dir", type=Path, default=None, help="Trace 디렉터리(기본: 관찰 계층 저장 위치)")
    parser.add_argument("--days", type=int, default=None, help="최근 N일만(기본: 보관 중 전체)")
    parser.add_argument("--summary", action="store_true", help="한 줄 요약만 출력")
    parser.add_argument("--json", action="store_true", help="그룹 목록을 JSON으로 출력")
    parser.add_argument("--report-dir", type=Path, default=_REPORT_DIR, help="리포트 디렉터리")
    parser.add_argument("--no-write", action="store_true", help="리포트 파일을 쓰지 않음")
    args = parser.parse_args(argv)

    # 원문 보관 기한은 어떤 출력 모드든 먼저 지킨다(--summary는 매 세션 돈다).
    sweep_reports(args.report_dir, dt.date.today())
    result = load(args.dir, args.days)
    if result["range"] is None:
        if not args.summary:
            print(f"Trace 파일이 없습니다: {args.dir or '관찰 계층 저장 위치(AGENT_TRACE_DIR)'}")
        return 0
    groups = result["groups"]
    if args.summary:
        print(render_summary(groups))
        return 0
    if args.json:
        print(json.dumps(groups, ensure_ascii=False, indent=1))
        return 0
    markdown = render_markdown(result)
    print(markdown)
    if not args.no_write:
        args.report_dir.mkdir(parents=True, exist_ok=True)
        # 이름 = 담은 원문 중 가장 오래된 Trace 날짜 — 그 Trace가 지워지는 날 리포트도 지워진다.
        out = args.report_dir / f"{result['range'][0]}.md"
        out.write_text(markdown, encoding="utf-8")
        print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
