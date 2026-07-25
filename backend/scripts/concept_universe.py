"""Concept Universe Builder CLI — 개념 중심 백테스트 유니버스 리포트(FR-STR-072).

용법(백엔드 루트에서):
  python3 scripts/concept_universe.py "BTS"
  python3 scripts/concept_universe.py "HBM" --json

관련도는 KG 근거(시드 원장 점수·학습 출처 수·관계 거리)에서 결정론 산출 — 동일
Concept엔 항상 동일 결과. 객관적 관계 데이터 표시이며 추천·전망이 아니다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description="Concept Universe Builder")
    ap.add_argument("concept", help="개념/테마/기술 (예: BTS, HBM, ESS)")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args()

    from engine.concept_universe import build_concept_universe

    result = build_concept_universe(args.concept)
    if result is None:
        print(f"'{args.concept}' — 지식그래프가 모르는 개념입니다. "
              "(전략 대화에서 언급하면 검색 그라운딩이 학습을 시도합니다)")
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    print(f"Concept\n{result['concept']}\n")
    print(f"Universe Size\n{result['size']}\n")
    if result["relaxed"]:
        print(f"(참고: 최소 크기 확보를 위해 임계를 {result['threshold_used']:.2f}까지 완화)\n")
    print("Universe\n")
    for i, s in enumerate(result["stocks"], 1):
        print(f"{i}.\n종목명\n{s['name']}\n\n종목코드\n{s['symbol']}\n")
        print(f"관련도\n{s['score']:.2f}\n\n이유\n{s['reason']}\n")
        print("-" * 25 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
