"""
Build data/stock-master.json — the survivorship-bias-free stock master.

Merges three sources into a single point-in-time membership table:
  1. FDR active listings (KOSPI/KOSDAQ): current symbols, market, shares.
  2. FDR KRX-DELISTING: delisted symbols with market, listing/delisting dates,
     reason, listed shares, and merger target (ToSymbol).
  3. Local OHLCV parquet date coverage (dataStart/dataEnd) — the ground truth of
     what we can actually price/trade.

The as-of universe resolver (engine/universe_pit.py) reads this file to decide,
for any backtest window, which symbols were *alive and priceable* during it —
including names that have since delisted. That is what removes survivorship bias.

Run:
    cd backend && python scripts/build_stock_master.py

Idempotent. Network-bound (FDR). Common stocks only (SecuGroup == 주권).
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import polars as pl

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_OUT_PATH = _PROJECT_ROOT / "data" / "stock-master.json"

# Delisted names older than this are dropped — we have no OHLCV depth for them and
# they only bloat the file. Our local price history starts ~2013-2016.
_DELISTING_FLOOR = "2015-01-01"
_KST = timezone(timedelta(hours=9))


def _scan_local_ohlcv_coverage() -> dict[str, tuple[str, str]]:
    """symbol -> (dataStart, dataEnd) from local parquet date columns."""
    coverage: dict[str, tuple[str, str]] = {}
    for f in glob.glob(str(_OHLCV_DIR / "*.parquet")):
        sym = os.path.basename(f)[:-8]
        try:
            d = pl.read_parquet(f, columns=["date"])["date"]
            if len(d) == 0:
                continue
            coverage[sym] = (str(d.min())[:10], str(d.max())[:10])
        except Exception:
            continue
    return coverage


def _load_active(fdr) -> dict[str, dict]:
    """Current KOSPI/KOSDAQ commons from FDR. Code/Name/Market/Stocks."""
    out: dict[str, dict] = {}
    for market in ("KOSPI", "KOSDAQ"):
        df = fdr.StockListing(market)
        code_col = "Code" if "Code" in df.columns else "Symbol"
        for _, r in df.iterrows():
            sym = str(r[code_col]).strip()
            if not sym or len(sym) > 6 and not sym.isalnum():
                continue
            shares = r.get("Stocks")
            out[sym] = {
                "symbol": sym,
                "name": str(r.get("Name", "")).strip(),
                "market": market,
                "secuGroup": "주권",
                "listingDate": None,   # active: lower bound derived from OHLCV dataStart
                "delistingDate": None,
                "shares": int(shares) if pd.notna(shares) else None,
                "reason": None,
                "toSymbol": None,
            }
    return out


def _load_delisted(fdr) -> dict[str, dict]:
    """Delisted KOSPI/KOSDAQ commons (>= floor) from FDR KRX-DELISTING."""
    d = fdr.StockListing("KRX-DELISTING")
    d["DelistingDate"] = pd.to_datetime(d["DelistingDate"], errors="coerce")
    d["ListingDate"] = pd.to_datetime(d["ListingDate"], errors="coerce")
    mask = (
        (d["SecuGroup"] == "주권")
        & (d["Market"].isin(["KOSPI", "KOSDAQ"]))
        & (d["DelistingDate"] >= _DELISTING_FLOOR)
    )
    out: dict[str, dict] = {}
    for _, r in d[mask].iterrows():
        sym = str(r["Symbol"]).strip()
        shares = r.get("ListingShares")
        to_sym = r.get("ToSymbol")
        out[sym] = {
            "symbol": sym,
            "name": str(r.get("Name", "")).strip(),
            "market": str(r["Market"]).strip(),
            "secuGroup": "주권",
            "listingDate": str(r["ListingDate"])[:10] if pd.notna(r["ListingDate"]) else None,
            "delistingDate": str(r["DelistingDate"])[:10],
            "shares": int(shares) if pd.notna(shares) else None,
            "reason": str(r.get("Reason", "")).strip() or None,
            "toSymbol": str(to_sym).strip() if pd.notna(to_sym) and str(to_sym).strip() else None,
        }
    return out


def build() -> dict:
    import FinanceDataReader as fdr

    print("[stock-master] scanning local OHLCV coverage...")
    coverage = _scan_local_ohlcv_coverage()
    print(f"[stock-master]   {len(coverage)} local parquet files")

    print("[stock-master] loading FDR active listings (KOSPI/KOSDAQ)...")
    active = _load_active(fdr)
    print(f"[stock-master]   {len(active)} active commons")

    print("[stock-master] loading FDR KRX-DELISTING...")
    delisted = _load_delisted(fdr)
    print(f"[stock-master]   {len(delisted)} delisted commons (>= {_DELISTING_FLOOR})")

    # Active wins over delisted on symbol collision (re-listed / re-used codes).
    merged: dict[str, dict] = {**delisted, **active}

    # Attach local OHLCV coverage (ground truth of priceability).
    for sym, entry in merged.items():
        cov = coverage.get(sym)
        entry["dataStart"] = cov[0] if cov else None
        entry["dataEnd"] = cov[1] if cov else None
        entry["hasOhlcv"] = cov is not None

    stocks = sorted(merged.values(), key=lambda s: s["symbol"])
    payload = {
        "generatedAt": datetime.now(_KST).isoformat(),
        "delistingFloor": _DELISTING_FLOOR,
        "counts": {
            "total": len(stocks),
            "active": sum(1 for s in stocks if s["delistingDate"] is None),
            "delisted": sum(1 for s in stocks if s["delistingDate"] is not None),
            "withOhlcv": sum(1 for s in stocks if s["hasOhlcv"]),
            "delistedWithOhlcv": sum(1 for s in stocks if s["delistingDate"] and s["hasOhlcv"]),
            "delistedMissingOhlcv": sum(1 for s in stocks if s["delistingDate"] and not s["hasOhlcv"]),
        },
        "stocks": stocks,
    }
    return payload


def main() -> None:
    payload = build()
    _OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    c = payload["counts"]
    print(f"[stock-master] wrote {_OUT_PATH}")
    print(f"[stock-master]   total={c['total']} active={c['active']} delisted={c['delisted']}")
    print(f"[stock-master]   delisted_with_ohlcv={c['delistedWithOhlcv']} "
          f"delisted_missing_ohlcv={c['delistedMissingOhlcv']}")


if __name__ == "__main__":
    main()
