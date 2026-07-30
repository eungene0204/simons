"""KSIC 산업분류 단위 섹터 재귀속(멱등).

'이 KSIC 코드는 이 섹터여야 한다'가 명확한데 기존 데이터가 다른 섹터에 넣어둔 경우를
바로잡는다. 개별 종목 오등록(OVERRIDDEN_SYMBOLS)과 달리 **분류 코드 단위 규칙**이라
신규 상장 종목도 자동으로 맞게 들어온다 — 여기 적은 규칙은 sector_mapper.MAPPING_RULES에
같은 내용으로 반영돼 있어야 하며, 이 스크립트는 이미 쌓인 데이터를 따라오게 만든다.

    python backend/scripts/reassign_by_industry.py [--apply]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from engine.universe_pit import CANONICAL_SECTORS  # noqa: E402

KOREA_STOCKS = REPO / "data" / "korea-stocks.json"

# KSIC 산업분류 → 정본 섹터.
REASSIGN: dict[str, str] = {
    # [2026-07-30] 관광·숙박·카지노가 미디어/엔터에 섞여 있었다 — MAPPING_RULES의
    # '관광·여행·숙박·유원지·오락·카지노' 어휘가 미디어/엔터 버킷에 들어 있던 탓.
    # 하나투어·강원랜드·아난티가 "미디어 업종" 백테스트에 잡히던 문제.
    "여행사 및 기타 여행보조 서비스업": "여행",
    "일반 및 생활 숙박시설 운영업": "레저",
    "유원지 및 기타 오락관련 서비스업": "레저",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    unknown = {v for v in REASSIGN.values() if v not in CANONICAL_SECTORS}
    if unknown:
        print(f"❌ 정본 목록에 없는 섹터: {sorted(unknown)}")
        return 1

    payload = json.loads(KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload["stocks"]

    tally: collections.Counter = collections.Counter()
    moved: list[str] = []
    for row in rows:
        target = REASSIGN.get(row.get("industry") or "")
        if target and row.get("sector") != target:
            moved.append(f"   {row.get('name'):<14} {row.get('sector')} → {target}")
            tally[f"{row.get('sector')} → {target}"] += 1
            row["sector"] = target

    if not moved:
        print("변경 없음 — 이미 규칙과 일치한다")
        return 0

    print(f"{len(moved)}종목 재귀속:")
    print("\n".join(moved))
    print()
    for key, count in sorted(tally.items()):
        print(f"   {count:3d}  {key}")

    if not args.apply:
        print("\n[dry-run] 실제 반영은 --apply")
        return 0

    KOREA_STOCKS.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n✅ {len(moved)}종목 반영 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
