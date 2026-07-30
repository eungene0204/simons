"""섹터 소속 정본(KG 오버레이)을 만든다 — data/kg-sector-membership.json.

[2026-07-30 정본 전환] 종전 섹터 소속의 정본은 korea-stocks.json의 `sector` 필드였고
KG는 그것을 몰랐다(`related_universe('원자력')` → {}). 인터프리터가 지식을 찾는 곳은
KG인데 섹터 소속이 KG 밖에 있어, 개념 해석은 되지만 "그 섹터에 어떤 종목이 있나"는
그래프로 답할 수 없었다.

이 파일이 새 정본이며 KG 빌드 시 `company:<symbol> -belongs_to→ sector:<정본명>`
엣지로 편입된다(theme_catalog·learned와 같은 오버레이 관례 — 손으로 큐레이션하는
시드 파일 knowledge-graph.json은 깨끗하게 남는다).

korea-stocks.json의 `sector` 필드는 이 정본에서 파생되는 **캐시**로 강등됐다
(참조부 71곳 호환 유지). 불일치는 test_sector_membership_sot가 잡는다.

    python backend/scripts/build_sector_membership.py [--apply]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KOREA_STOCKS = REPO / "data" / "korea-stocks.json"
STOCK_MASTER = REPO / "data" / "stock-master.json"
OUT_PATH = REPO / "data" / "kg-sector-membership.json"


def collect() -> tuple[dict[str, str], dict[str, str]]:
    """symbol → sector, symbol → name.

    병합 규칙(마스터 → korea-stocks 덮어쓰기 → 우선주 상속)은 universe_pit이 정본
    구현을 갖는다 — 여기서 다시 적으면 두 곳이 어긋난다."""
    sys.path.insert(0, str(REPO / "backend"))
    from engine.universe_pit import sector_map_from_files

    membership = sector_map_from_files()
    names: dict[str, str] = {}
    for row in json.loads(STOCK_MASTER.read_text(encoding="utf-8"))["stocks"]:
        if row.get("symbol"):
            names[row["symbol"]] = row.get("name") or row["symbol"]
    payload = json.loads(KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload["stocks"]
    for row in rows:
        if row.get("symbol"):
            names[row["symbol"]] = row.get("name") or row["symbol"]
    return membership, names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    membership, names = collect()
    tally = collections.Counter(membership.values())

    payload = {
        "version": 1,
        "description": (
            "섹터 소속 정본(SOT). KG 빌드 시 company -belongs_to→ sector 엣지로 편입된다. "
            "korea-stocks.json의 sector 필드는 이 파일에서 파생되는 캐시다. "
            "생성: backend/scripts/build_sector_membership.py"
        ),
        "counts": {"symbols": len(membership), "sectors": len(tally)},
        "membership": dict(sorted(membership.items())),
    }

    print(f"종목 {len(membership)} / 섹터 {len(tally)}")
    for sector, count in tally.most_common(8):
        print(f"   {count:5d}  {sector}")
    print("   …")

    if not args.apply:
        print(f"\n[dry-run] 실제 저장은 --apply → {OUT_PATH.name}")
        return 0

    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n✅ {OUT_PATH.name} 저장 ({len(membership)}종목)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
