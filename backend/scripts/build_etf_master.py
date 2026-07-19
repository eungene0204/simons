"""
Build data/etf-master.json — the ETF universe master.

Merges three sources:
  1. FDR ETF/KR listing: current ETF symbols and names.
  2. Local OHLCV parquet date coverage (dataStart/dataEnd) — the ground truth of
     what we can actually price/trade.
  3. data/etf-delisted.json (scripts/backfill_delisted_etf.py 산출물, 있으면):
     상폐 ETF 멤버십 — 생존 편향 제거. 코드가 현재 목록에 재사용된 경우 현재분 우선.

The universe resolver (engine/universe_pit.py) reads this file to answer
universe_id="etf" — the ETF universe is disjoint from the stock universes
(KOSPI/KOSDAQ/KOSPI200) and is never mixed with them.

etf-delisted.json이 없으면 현재 상장분만 담기며(생존 편향), 엔진이 ETF 백테스트마다
경고를 남긴다. backfill_delisted_etf.py는 KRX 접근 승인(Open API 또는 로그인)이 필요하다.

Run:
    cd backend && python scripts/build_etf_master.py

Idempotent. Network-bound (FDR).
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import polars as pl

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_OUT_PATH = _PROJECT_ROOT / "data" / "etf-master.json"
_DELISTED_PATH = _PROJECT_ROOT / "data" / "etf-delisted.json"
_KST = timezone(timedelta(hours=9))


def _scan_local_ohlcv_coverage(symbols: set[str]) -> dict[str, tuple[str, str]]:
    """symbol -> (dataStart, dataEnd) from local parquet date columns."""
    coverage: dict[str, tuple[str, str]] = {}
    for f in glob.glob(str(_OHLCV_DIR / "*.parquet")):
        sym = os.path.basename(f)[:-8]
        if sym not in symbols:
            continue
        try:
            d = pl.read_parquet(f, columns=["date"])["date"]
            if len(d) == 0:
                continue
            coverage[sym] = (str(d.min())[:10], str(d.max())[:10])
        except Exception:
            continue
    return coverage


def main() -> None:
    import FinanceDataReader as fdr

    listing = fdr.StockListing("ETF/KR")
    symbols = {str(row.Symbol).zfill(6) for row in listing.itertuples()}
    coverage = _scan_local_ohlcv_coverage(symbols)

    etfs = []
    for row in listing.itertuples():
        sym = str(row.Symbol).zfill(6)
        ds, de = coverage.get(sym, (None, None))
        etfs.append({
            "symbol": sym,
            "name": str(row.Name),
            "dataStart": ds,
            "dataEnd": de,
            "hasOhlcv": sym in coverage,
            "delistingDate": None,
        })

    # 상폐 ETF 병합(backfill_delisted_etf.py 산출물) — 코드 재사용 시 현재 상장분 우선.
    delisted_count = 0
    if _DELISTED_PATH.exists():
        current_syms = {e["symbol"] for e in etfs}
        delisted_entries = json.loads(_DELISTED_PATH.read_text(encoding="utf-8")).get("etfs", [])
        delisted_coverage = _scan_local_ohlcv_coverage(
            {e["symbol"] for e in delisted_entries} - current_syms
        )
        for e in delisted_entries:
            sym = e["symbol"]
            if sym in current_syms:
                continue
            ds, de = delisted_coverage.get(sym, (e.get("dataStart"), e.get("dataEnd")))
            etfs.append({
                "symbol": sym, "name": e.get("name", ""),
                "dataStart": ds, "dataEnd": de,
                "hasOhlcv": sym in delisted_coverage,
                "delistingDate": e.get("delistingDate"),
            })
            delisted_count += 1
    etfs.sort(key=lambda e: e["symbol"])

    with_data = sum(1 for e in etfs if e["hasOhlcv"])
    payload = {
        "generatedAt": datetime.now(_KST).isoformat(),
        "counts": {"total": len(etfs), "withOhlcv": with_data, "delisted": delisted_count},
        "etfs": etfs,
    }
    _OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"etf-master.json: {len(etfs)} ETFs ({with_data} with OHLCV) -> {_OUT_PATH}")


if __name__ == "__main__":
    main()
