"""
Backfill OHLCV for delisted commons that we lack locally.

The local price history is itself survivorship-biased: ~89% of recently delisted
KOSPI/KOSDAQ commons have no local parquet. Without their prices we cannot include
them in a backtest even after fixing universe membership. FDR serves full price
history for delisted symbols (up to their final 정리매매 day), so we download the
missing names into data/ohlcv/ in the same schema the loader expects.

Run (after build_stock_master.py):
    cd backend && python scripts/backfill_delisted_ohlcv.py

Idempotent: skips symbols that already have a parquet. Re-run build_stock_master.py
afterwards to refresh dataStart/dataEnd/hasOhlcv coverage.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_MASTER_PATH = _PROJECT_ROOT / "data" / "stock-master.json"

_DOWNLOAD_FROM = "2013-01-01"   # match the depth of existing local history
_SLEEP_SECONDS = 0.1            # be polite to the data source


def _to_parquet(df, sym: str) -> int:
    """Write FDR pandas OHLCV to our parquet schema. Returns row count."""
    df = df.reset_index().rename(columns={
        "Date": "date", "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume", "Change": "change",
    })
    keep = ["date", "open", "high", "low", "close", "volume", "change"]
    df = df[[c for c in keep if c in df.columns]]
    pdf = df.dropna(subset=["close"])
    pdf = pdf[pdf["close"] > 0]
    if len(pdf) == 0:
        return 0
    out = pl.from_pandas(pdf).with_columns([
        pl.col("date").cast(pl.Datetime("us")),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Float64),
        pl.col("change").cast(pl.Float64),
    ])
    out.write_parquet(_OHLCV_DIR / f"{sym}.parquet")
    return len(out)


def main() -> None:
    import FinanceDataReader as fdr

    master = json.loads(_MASTER_PATH.read_text(encoding="utf-8"))
    targets = [
        s for s in master["stocks"]
        if s["delistingDate"] is not None and not s["hasOhlcv"]
    ]
    print(f"[backfill] {len(targets)} delisted commons missing OHLCV")

    ok = skipped = failed = 0
    for i, s in enumerate(targets, 1):
        sym = s["symbol"]
        path = _OHLCV_DIR / f"{sym}.parquet"
        if path.exists():
            skipped += 1
            continue
        try:
            df = fdr.DataReader(sym, _DOWNLOAD_FROM, s["delistingDate"])
            n = _to_parquet(df, sym) if df is not None and len(df) else 0
            if n > 0:
                ok += 1
                if i % 25 == 0 or n == 0:
                    print(f"[backfill] {i}/{len(targets)} {sym} {s['name']} <- {n} rows")
            else:
                failed += 1
                print(f"[backfill] {i}/{len(targets)} {sym} {s['name']} -> empty")
        except Exception as e:
            failed += 1
            print(f"[backfill] {i}/{len(targets)} {sym} {s['name']} -> FAIL {repr(e)[:80]}")
        time.sleep(_SLEEP_SECONDS)

    print(f"[backfill] done: ok={ok} skipped={skipped} failed={failed}")
    print("[backfill] now re-run: python scripts/build_stock_master.py")


if __name__ == "__main__":
    main()
