"""sector_mapper.OVERRIDDEN_SYMBOLS를 korea-stocks.json에 반영한다(멱등).

OVERRIDDEN_SYMBOLS는 '산업분류 문자열로는 옳게 분류할 수 없는 종목'의 정본 귀속이다
(KSIC에 해당 업종 코드가 없거나, 코드가 실제 사업과 어긋나는 경우). 종전에는 이 표가
재생성 경로(build_stock_master·enrich)에만 쓰여 현재 상장 SOT(korea-stocks.json)와
어긋날 수 있었다 — 이 스크립트가 둘을 맞추고 드리프트를 드러낸다.

    python backend/scripts/apply_sector_overrides.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from engine.sector_mapper import OVERRIDDEN_SYMBOLS  # noqa: E402
from engine.universe_pit import CANONICAL_SECTORS  # noqa: E402

KOREA_STOCKS = REPO / "data" / "korea-stocks.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    unknown = {s for s in OVERRIDDEN_SYMBOLS.values() if s not in CANONICAL_SECTORS}
    if unknown:
        print(f"❌ 정본 목록에 없는 섹터가 오버라이드에 있다: {sorted(unknown)}")
        return 1

    payload = json.loads(KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload["stocks"]

    changes = []
    for row in rows:
        target = OVERRIDDEN_SYMBOLS.get(row.get("symbol"))
        if target and row.get("sector") != target:
            changes.append((row["symbol"], row.get("name"), row.get("sector"), target))
            row["sector"] = target

    if not changes:
        print("변경 없음 — korea-stocks.json이 오버라이드 표와 일치한다")
        return 0

    print(f"{len(changes)}종목 재귀속:")
    for symbol, name, old, new in changes:
        print(f"   {symbol}  {name:<16} {old} → {new}")

    if not args.apply:
        print("\n[dry-run] 실제 반영은 --apply")
        return 0

    KOREA_STOCKS.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n✅ {len(changes)}종목 반영 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
