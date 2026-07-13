"""
Backfill sector classification for delisted stocks in data/stock-master.json.

섹터 분류 SOT(korea-stocks.json)는 현재 상장 종목만 담아, 섹터 유니버스 백테스트에서
기간 중 상장폐지된 종목이 통째로 빠지는 생존 편향이 있었다. FDR KRX-DELISTING이
제공하는 KRX 업종명(Industry)을 현재 상장 종목과 동일한 매퍼
(engine.sector_mapper.get_sector_from_industry)로 정본 섹터에 매핑해
stock-master.json의 상폐 엔트리에 industry/sector 필드를 채운다.

전체 재빌드(build_stock_master.py) 없이 기존 파일을 제자리 패치한다. 멱등.
신규 재빌드는 build_stock_master.py가 같은 로직으로 sector를 직접 생성한다.

Run:
    cd backend && python scripts/backfill_delisted_sectors.py

data/stock-master.json은 git 추적 파일이고 프로덕션 compose가 ./data를 마운트하므로,
백필 결과를 커밋하면 배포(git pull)로 프로덕션에 자동 반영된다(별도 실행 불필요).
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.sector_mapper import get_sector_from_krx_industry

_MASTER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock-master.json"


def _load_delisted_industries() -> dict[str, str]:
    """symbol -> KRX 업종명. 재상장으로 상폐 이력이 여러 번이면 최신 상폐 행을 쓴다."""
    import FinanceDataReader as fdr

    d = fdr.StockListing("KRX-DELISTING")
    d["Symbol"] = d["Symbol"].astype(str).str.strip()
    d["DelistingDate"] = pd.to_datetime(d["DelistingDate"], errors="coerce")
    d = d.sort_values("DelistingDate").drop_duplicates("Symbol", keep="last")
    out: dict[str, str] = {}
    for _, r in d.iterrows():
        industry = str(r.get("Industry", "")).strip() if pd.notna(r.get("Industry")) else ""
        if industry:
            out[r["Symbol"]] = industry
    return out


def main() -> None:
    if not _MASTER_PATH.exists():
        raise SystemExit(f"{_MASTER_PATH} 없음 — 먼저 build_stock_master.py를 실행하세요.")
    payload = json.loads(_MASTER_PATH.read_text(encoding="utf-8"))
    stocks = payload.get("stocks", [])
    delisted = [s for s in stocks if s.get("delistingDate")]

    print("[delisted-sectors] loading FDR KRX-DELISTING...")
    industries = _load_delisted_industries()

    filled, unmapped, dist = 0, [], Counter()
    for s in delisted:
        industry = industries.get(s["symbol"])
        if not industry:
            unmapped.append((s["symbol"], s["name"]))
            continue
        sector = get_sector_from_krx_industry(s["symbol"], industry, s.get("name", ""))
        s["industry"] = industry
        s["sector"] = sector
        dist[sector] += 1
        filled += 1

    _MASTER_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[delisted-sectors] 상폐 {len(delisted)}개 중 sector 백필 {filled}개, 업종 미상 {len(unmapped)}개")
    for sector, n in dist.most_common():
        print(f"[delisted-sectors]   {sector}: {n}")
    if unmapped:
        print(f"[delisted-sectors] 업종 미상(sector 없음 유지): {unmapped[:20]}")


if __name__ == "__main__":
    main()
