#!/usr/bin/env python3
"""mini-planner 승격 판정 배치 하니스 — planner vs 고정 체인 A/B 리플레이.

Planner→Tool→Responder Phase 3 후속(승격 판정)의 오프라인 트랙: 미해석 테마/업종
표현 코퍼스를 mini-planner(plan_universe_resolution)와 고정 체인
(primary._resolve_sector_terms_term_in)에 각각 태워 해석률·되묻기·지연을 비교한다.

공정 비교 계약:
- 레인마다 새 서브프로세스 — 어휘집(_load_lexicon_cached)·지식그래프 인프로세스
  캐시가 레인 간에 새는 것을 차단한다.
- 레인 실행 전후 data/term_lexicon.json 스냅샷/복원 — ground_term은 성공/실패
  모두 어휘집에 영속 저장하므로, 복원 없이는 먼저 돈 레인의 학습을 뒤에 도는
  레인이 공짜로 읽는 순서 오염이 생긴다. 복원으로 QA 실행 흔적도 남기지 않는다
  (searched_at 원장 오염 방지).
- precheck에서 이미 결정적으로 해석되는 표현은 스킵 — planner 소관 케이스가 아니다.

전제: `ollama serve` 실행 중(9B 인터프리터 슬롯), .env에 NAVER_CLIENT_ID/SECRET
(없으면 ground_term이 침묵해 양쪽 다 KG-only로 비교됨 — 결과에 search_available 기록).
주의: pytest 스위트와 동시 실행 금지 — 어휘집 스냅샷/복원이 어휘집을 읽는 테스트와
경합해 일시 실패를 만든다(2026-07-26 실측 1건).

사용:
  python scripts/qa_planner_promotion.py                # 전체 코퍼스
  python scripts/qa_planner_promotion.py --limit 3      # 앞 3건만(스모크)
  python scripts/qa_planner_promotion.py --only "CXL 관련주"
결과: scripts/qa_planner_promotion_results.json + 표준출력 요약표.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
LEXICON = REPO / "data" / "term_lexicon.json"
TERMS_FILE = REPO / "scripts" / "qa_planner_promotion_terms.json"
RESULTS_FILE = REPO / "scripts" / "qa_planner_promotion_results.json"
MARKER = "@@QA_RESULT@@"
CHILD_TIMEOUT_S = 420

# 백엔드 import 안전 가드(AI 모듈 전이 import 대비 — 프로젝트 표준)
_CHILD_ENV_GUARDS = {
    "KMP_DUPLICATE_LIB_OK": "TRUE",
    "OMP_NUM_THREADS": "1",
    "POLARS_MAX_THREADS": "1",
}


# ─── child: 격리 프로세스에서 레인 하나 실행 ────────────────────────────────────


def _slim_observation(obs: Optional[dict]) -> Optional[dict]:
    """관찰값 로그 슬리밍 — companies 전체 나열 대신 수+앞 3개 이름만."""
    if not obs:
        return obs
    slim = dict(obs)
    companies = slim.get("companies")
    if isinstance(companies, list) and companies:
        slim["companies"] = {
            "count": len(companies),
            "head": [c.get("name") or c.get("symbol") for c in companies[:3]
                     if isinstance(c, dict)],
        }
    return slim


def _run_child(lane: str, term: str) -> dict:
    sys.path.insert(0, str(REPO / "backend"))
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    out: dict = {"term": term, "lane": lane}

    if lane == "precheck":
        from engine.term_grounding import search_available
        from strategy_conversation.registry.universe_resolver import resolve_sectors

        value, unresolved = resolve_sectors([term])
        out.update({"resolved_value": value, "unresolved": unresolved,
                    "search_available": search_available()})

    elif lane == "planner":
        from strategy_conversation.planner.mini_planner import plan_universe_resolution
        from strategy_conversation.planner.shadow import _default_chat

        base_chat = _default_chat()
        raw_outputs: list = []

        def _chat(system_prompt: str, user_message: str, **kw) -> str:
            reply = base_chat(system_prompt, user_message, **kw)
            raw_outputs.append(reply)
            return reply

        start = time.monotonic()
        result = plan_universe_resolution(term, _chat)
        if result is None:
            # 폴백 원인 진단용 — 마지막 LLM 원시 출력(계약 위반 지점)
            out.update({"outcome": "none",
                        "latency_ms": int((time.monotonic() - start) * 1000),
                        "raw_tail": raw_outputs[-1][:400] if raw_outputs else None})
        else:
            out.update({
                "outcome": result.outcome,
                "sector": result.sector,
                "companies_count": len(result.companies),
                "question": result.question,
                "steps": [{"tool": s.tool, "args": s.args,
                           "observation": _slim_observation(s.observation)}
                          for s in result.steps],
                "latency_ms": result.latency_ms,
            })

    elif lane == "fixed":
        from engine.nl_parser import ParsedStrategy
        from strategy_conversation.primary import _resolve_sector_terms_term_in

        parsed = ParsedStrategy(description="qa-planner-promotion")
        notices: list = []
        start = time.monotonic()
        question, suggestions = _resolve_sector_terms_term_in(parsed, [term], notices)
        latency_ms = int((time.monotonic() - start) * 1000)
        resolved = bool(parsed.sector or parsed.target_symbols)
        out.update({
            "outcome": "clarify" if question else ("resolved" if resolved else "none"),
            "sector": parsed.sector,
            "companies_count": len(parsed.target_symbols or []),
            "question": question,
            "suggestions": suggestions,
            "notices": notices,
            "latency_ms": latency_ms,
        })

    else:
        raise SystemExit(f"unknown lane: {lane}")

    print(MARKER + json.dumps(out, ensure_ascii=False, default=str))


# ─── parent: 코퍼스 순회 + 어휘집 격리 + 집계 ───────────────────────────────────


def _spawn(lane: str, term: str) -> dict:
    env = {**os.environ, **_CHILD_ENV_GUARDS}
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child", "--lane", lane,
         "--term", term],
        capture_output=True, text=True, timeout=CHILD_TIMEOUT_S, env=env,
        cwd=str(REPO),
    )
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith(MARKER):
            return json.loads(line[len(MARKER):])
    return {"term": term, "lane": lane, "outcome": "error",
            "error": (proc.stderr or proc.stdout or "no output")[-500:]}


def _snapshot_lexicon() -> Optional[bytes]:
    return LEXICON.read_bytes() if LEXICON.exists() else None


def _restore_lexicon(snapshot: Optional[bytes]) -> None:
    if snapshot is None:
        LEXICON.unlink(missing_ok=True)
    else:
        LEXICON.write_bytes(snapshot)


def _pct(values: list, q: float) -> Optional[int]:
    if not values:
        return None
    ordered = sorted(values)
    return int(ordered[min(len(ordered) - 1, int(q * len(ordered)))])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--lane", help=argparse.SUPPRESS)
    parser.add_argument("--term", help=argparse.SUPPRESS)
    parser.add_argument("--terms-file", default=str(TERMS_FILE))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only", default=None, help="해당 term 하나만 실행")
    args = parser.parse_args()

    if args.child:
        _run_child(args.lane, args.term)
        return

    corpus = json.loads(Path(args.terms_file).read_text(encoding="utf-8"))
    if args.only:
        corpus = [c for c in corpus if c["term"] == args.only]
    if args.limit:
        corpus = corpus[: args.limit]

    rows: list = []
    for i, case in enumerate(corpus, 1):
        term = case["term"]
        print(f"[{i}/{len(corpus)}] {term}", flush=True)
        row: dict = {"term": term, **{k: v for k, v in case.items() if k != "term"}}

        pre = _spawn("precheck", term)
        row["search_available"] = pre.get("search_available")
        if pre.get("outcome") == "error":
            row["status"] = "precheck_error"
            row["error"] = pre.get("error")
            rows.append(row)
            print("    precheck 실패 — 스킵", flush=True)
            continue
        if not pre.get("unresolved"):
            row["status"] = "skipped_already_resolved"
            row["resolved_value"] = pre.get("resolved_value")
            rows.append(row)
            print(f"    결정적 해석됨({pre.get('resolved_value')}) — planner 소관 아님, 스킵",
                  flush=True)
            continue

        snapshot = _snapshot_lexicon()
        try:
            row["planner"] = _spawn("planner", term)
            _restore_lexicon(snapshot)
            row["fixed"] = _spawn("fixed", term)
        finally:
            _restore_lexicon(snapshot)
        row["status"] = "compared"
        rows.append(row)
        p, f = row["planner"], row["fixed"]
        print(f"    planner={p.get('outcome')}({p.get('sector')}, {p.get('latency_ms')}ms) "
              f"fixed={f.get('outcome')}({f.get('sector')}, {f.get('latency_ms')}ms)",
              flush=True)

    RESULTS_FILE.write_text(
        json.dumps({"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "cases": rows},
                   ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    _print_summary(rows)
    print(f"\n결과 저장: {RESULTS_FILE}")


def _print_summary(rows: list) -> None:
    compared = [r for r in rows if r.get("status") == "compared"]
    skipped = [r for r in rows if r.get("status") == "skipped_already_resolved"]
    errors = [r for r in rows if r.get("status") == "precheck_error"]
    print("\n" + "=" * 72)
    print(f"총 {len(rows)}건 — 비교 {len(compared)} / 결정적 스킵 {len(skipped)} / 에러 {len(errors)}")

    def _lane_stats(lane: str) -> str:
        outcomes = [r[lane].get("outcome") for r in compared if lane in r]
        lat = [r[lane]["latency_ms"] for r in compared
               if lane in r and isinstance(r[lane].get("latency_ms"), int)]
        counts = {o: outcomes.count(o) for o in ("resolved", "clarify", "none", "error")}
        stats = f"p50={_pct(lat, 0.5)}ms p95={_pct(lat, 0.95)}ms" if lat else "-"
        return f"resolved={counts['resolved']} clarify={counts['clarify']} " \
               f"none/폴백={counts['none']} error={counts['error']} | {stats}"

    if compared:
        print(f"planner : {_lane_stats('planner')}")
        print(f"fixed   : {_lane_stats('fixed')}")
        print("-" * 72)
        for r in compared:
            p, f = r.get("planner", {}), r.get("fixed", {})
            mark = "  " if p.get("outcome") == f.get("outcome") and \
                p.get("sector") == f.get("sector") else "≠ "
            expected = r.get("expected_sector") or r.get("expected_outcome") or "-"
            print(f"{mark}{r['term']}: planner={p.get('outcome')}/{p.get('sector')}"
                  f"/{p.get('companies_count')}곳 fixed={f.get('outcome')}/{f.get('sector')}"
                  f"/{f.get('companies_count')}곳 (기대: {expected})")
    print("=" * 72)


if __name__ == "__main__":
    main()
