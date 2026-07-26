#!/usr/bin/env python3
"""planner shadow 로그(JSONL) 요약 — 승격 판정(Phase 3 후속 ③)용 리포트.

backend/logs/strategy_planner_shadow.jsonl(또는 --log 경로)을 읽어 outcome 분포,
지연 백분위, planner vs baseline_sector(고정 체인 결정적 재조회) 일치/불일치 목록을
출력한다. 로그는 dev 백엔드가 STRATEGY_PLANNER_MODE=shadow일 때 자동 누적된다.

사용: python scripts/qa_planner_shadow_report.py [--log <path>] [--tail N]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_LOG = REPO / "backend" / "logs" / "strategy_planner_shadow.jsonl"


def _pct(values: list, q: float):
    if not values:
        return None
    ordered = sorted(values)
    return int(ordered[min(len(ordered) - 1, int(q * len(ordered)))])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--tail", type=int, default=None, help="최근 N건만 집계")
    args = parser.parse_args()

    path = Path(args.log)
    if not path.exists():
        print(f"로그 없음: {path}\n"
              "dev 백엔드가 STRATEGY_PLANNER_MODE=shadow로 실행 중이어야 누적됩니다.")
        return

    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if args.tail:
        records = records[-args.tail:]
    if not records:
        print(f"기록 0건: {path}")
        return

    outcomes = Counter(r.get("outcome") for r in records)
    errors = [r for r in records if r.get("error")]
    latencies = [r["latency_ms"] for r in records
                 if isinstance(r.get("latency_ms"), int)]

    print(f"shadow 로그: {path} — 총 {len(records)}건 "
          f"({records[0].get('ts')} ~ {records[-1].get('ts')})")
    print(f"outcome: {dict(outcomes)} | error {len(errors)}건")
    print(f"지연: p50={_pct(latencies, 0.5)}ms p95={_pct(latencies, 0.95)}ms")
    print("-" * 72)

    for r in records:
        term = r.get("term")
        outcome = r.get("outcome")
        sector = r.get("sector")
        baseline = r.get("baseline_sector")
        # baseline은 '고정 체인이 같은 턴에 학습한 뒤'의 결정적 재조회 — 다르면 관심 케이스
        planner_view = sector or (f"상장사 {r.get('companies_count')}곳"
                                  if r.get("companies_count") else None)
        agree = "  " if (planner_view or None) == (baseline or None) else "≠ "
        detail = f"planner={outcome}/{planner_view} baseline={baseline}"
        if r.get("error"):
            detail += f" error={r['error'][:80]}"
        print(f"{agree}{term}: {detail}")


if __name__ == "__main__":
    main()
