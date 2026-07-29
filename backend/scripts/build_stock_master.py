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
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.sector_mapper import get_sector_from_krx_industry

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


def load_kind_listing_dates() -> dict[str, str]:
    """symbol -> 상장일(YYYY-MM-DD) from FDR "KRX-DESC" (KIND 상장법인목록).

    현행 상장 목록(StockListing("KOSPI"/"KOSDAQ"))에는 상장일 컬럼이 없어 "신규 상장
    종목" 유니버스(FR-STR-073)를 판정할 수 없다. KIND 상장법인목록은 무료·인증 없이
    현행 상장 보통주의 상장일을 사실상 전부 제공한다(실측 2026-07-29: 현행 상장 대비
    99.5%). 상장일이 비어 있는 행(주로 우선주)은 제외한다.
    """
    import FinanceDataReader as fdr
    import pandas as pd

    df = fdr.StockListing("KRX-DESC")
    dates = pd.to_datetime(df["ListingDate"], errors="coerce")
    out: dict[str, str] = {}
    for code, listed in zip(df["Code"].astype(str).str.strip(), dates):
        if code and pd.notna(listed):
            out[code] = str(listed)[:10]
    return out


def _load_active(fdr) -> dict[str, dict]:
    """Current KOSPI/KOSDAQ commons from FDR. Code/Name/Market/Stocks.

    상장일은 현행 상장 목록에 없어 KIND 상장법인목록(KRX-DESC)에서 붙인다.
    """
    listing_dates = load_kind_listing_dates()
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
                "listingDate": listing_dates.get(sym),  # 미커버 시 OHLCV dataStart가 하한
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
        name = str(r.get("Name", "")).strip()
        # KRX 업종명 → 정본 섹터. 섹터 분류 SOT(korea-stocks.json)는 현재 상장 종목만
        # 담으므로, 상폐 종목은 여기서 채워야 섹터 유니버스 백테스트에 포함된다(생존 편향 제거).
        industry = str(r.get("Industry", "")).strip() if pd.notna(r.get("Industry")) else ""
        out[sym] = {
            "symbol": sym,
            "name": name,
            "market": str(r["Market"]).strip(),
            "secuGroup": "주권",
            "listingDate": str(r["ListingDate"])[:10] if pd.notna(r["ListingDate"]) else None,
            "delistingDate": str(r["DelistingDate"])[:10],
            "shares": int(shares) if pd.notna(shares) else None,
            "reason": str(r.get("Reason", "")).strip() or None,
            "toSymbol": str(to_sym).strip() if pd.notna(to_sym) and str(to_sym).strip() else None,
            "industry": industry or None,
            "sector": get_sector_from_krx_industry(sym, industry, name) if industry else None,
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
