"""KG 재연결 감사 — 학습 어휘집 × 현재 그래프 재스캔(+선택적 TTL 재그라운딩).

두 가지 공백을 메운다(FR-STR-069 ⑦·FR-STR-070b ⑥ — 'bts 관련주' 사고 후속):
  ① 역스캔(기본, 네트워크·LLM 불필요): 학습 항목의 저장 정의·출처 제목에 등장하는
     미연결 개념(학습 이후 편입된 시드 포함)을 pending related_to로 제안한다.
     제안은 전부 콘솔(Knowledge 탭) 승인 대상 — 자동 verified 없음.
  ② --reground-stale: searched_at이 TTL(TERM_REGROUND_TTL_DAYS, 기본 90일)보다 오래된
     항목을 재검색·재그라운딩한다(네이버 자격증명+로컬 LLM 필요). 병합 계약이라
     기존 엣지의 검토 상태(verified/rejected)는 보존되고 새 제안만 추가된다.

용법(백엔드 루트에서):
  python3 scripts/kg_relink_audit.py                     # 역스캔만
  python3 scripts/kg_relink_audit.py --reground-stale    # 역스캔 + TTL 재그라운딩
  python3 scripts/kg_relink_audit.py --ttl-days 30       # TTL 오버라이드

시드 편입 절차의 가드 5(docs/kg_concept_builder.md)이자 주기 감사 진입점이다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description="KG 재연결 감사")
    ap.add_argument("--reground-stale", action="store_true",
                    help="TTL 경과 항목 재검색·병합(네이버 자격증명+LLM 필요)")
    ap.add_argument("--ttl-days", type=float, default=None,
                    help="TERM_REGROUND_TTL_DAYS 오버라이드")
    args = ap.parse_args()

    if args.ttl_days is not None:
        os.environ["TERM_REGROUND_TTL_DAYS"] = str(args.ttl_days)

    from engine.term_grounding import (
        _LEXICON_PATH, _default_search, _entry_is_stale, _ground_and_learn,
        _load_lexicon, relink_lexicon, search_available,
    )

    report = relink_lexicon()
    print(f"[역스캔] 항목 {report['terms_scanned']}개 중 {report['terms_updated']}개에 후보 추가")
    for key, targets in report["added"].items():
        print(f"  - {key}: {', '.join(targets)} (pending — 콘솔 승인 대상)")

    if args.reground_stale:
        lexicon = _load_lexicon(_LEXICON_PATH)
        stale = {k: e for k, e in lexicon.items()
                 if isinstance(e, dict) and _entry_is_stale(e)}
        print(f"[재그라운딩] TTL 경과 항목 {len(stale)}개")
        if stale:
            if not search_available():
                print("  ! 네이버 검색 자격증명 없음 — 재그라운딩 건너뜀")
                return 1
            from engine.nl_parser import NLStrategyParser

            chat = NLStrategyParser().chat
            for key, entry in stale.items():
                term = entry.get("term") or key
                updated = _ground_and_learn(term, chat, _default_search,
                                            _LEXICON_PATH, previous=entry)
                if updated is None:
                    print(f"  - {term}: 검색 실패 — 기존 항목 유지")
                    continue
                print(f"  - {term}: sector={updated.get('sector')}, "
                      f"edges={len(updated.get('edges') or [])} (검토 상태 보존 병합)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
