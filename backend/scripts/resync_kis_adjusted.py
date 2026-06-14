"""
Re-sync every OHLCV parquet to KIS 수정주가 (broker-grade adjusted prices).

The FDR-sourced close is only partially adjusted (forward splits yes, reverse splits /
감자 / suspension-resumption no), so the dataset carries impossible jumps. KIS
`inquire-daily-itemchartprice` with FID_ORG_ADJ_PRC=0 returns authoritative adjusted
OHLC for both active and delisted names — this replaces the price columns with the
correct continuous series so the backtest is never fooled by a split.

Fundamentals (annual eps/bps/roe/debt_ratio + sector) are preserved from the existing
parquet; per/pbr are recomputed from the new adjusted close so they stay consistent.

Run (long — paginates ~100 rows/call across full history for ~3200 commons):
    cd backend && python scripts/resync_kis_adjusted.py

Resumable: completed symbols are recorded; re-running skips them. Rate-limited with
backoff. KIS serves only stock-master commons here; special codes are skipped.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import polars as pl
import requests
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_MASTER_PATH = _PROJECT_ROOT / "data" / "stock-master.json"
_PROGRESS_PATH = _OHLCV_DIR / ".kis_resync_done.json"   # under gitignored data/ohlcv

_KIS = "https://openapi.koreainvestment.com:9443"
_CHART = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
_START_FLOOR = "20130101"
_FUND_COLS = ["sector", "eps", "bps", "roe_or_gpa", "debt_ratio"]
_SLEEP = 0.09          # ~11 req/s; KIS personal cap ~20/s
_PAGE_DAYS = 150       # calendar window per call (≈100 trading rows)

import os
load_dotenv(_PROJECT_ROOT / ".env")
_AK = os.getenv("KIS_APP_KEY", "").strip()
_SK = os.getenv("KIS_APP_SECRET", "").strip()

_token = {"v": None, "exp": 0.0}


def _get_token() -> str:
    if _token["v"] and time.time() < _token["exp"]:
        return _token["v"]
    r = requests.post(f"{_KIS}/oauth2/tokenP",
                      json={"grant_type": "client_credentials", "appkey": _AK, "appsecret": _SK},
                      timeout=15)
    tok = r.json().get("access_token")
    if not tok:
        raise RuntimeError(f"KIS token failed: {r.text[:200]}")
    _token["v"] = tok
    _token["exp"] = time.time() + 23 * 3600
    return tok


def _fetch_window(sym: str, d0: str, d1: str) -> list[dict]:
    """Most-recent ≤100 adjusted daily rows within [d0, d1]."""
    for attempt in range(4):
        try:
            r = requests.get(
                f"{_KIS}{_CHART}",
                headers={"authorization": f"Bearer {_get_token()}", "appkey": _AK, "appsecret": _SK,
                         "tr_id": "FHKST03010100", "custtype": "P"},
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": sym,
                        "FID_INPUT_DATE_1": d0, "FID_INPUT_DATE_2": d1,
                        "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"},
                timeout=12,
            )
            j = r.json()
            if j.get("rt_cd") == "0":
                return j.get("output2", []) or []
            # rate limit / transient
            time.sleep(0.5 * (attempt + 1))
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return []


def _fetch_full(sym: str, start: str, end: str) -> pd.DataFrame | None:
    rows: dict[str, dict] = {}
    cur_end = end
    for _ in range(80):  # safety bound (~8000 trading days)
        out = _fetch_window(sym, start, cur_end)
        time.sleep(_SLEEP)
        if not out:
            break
        for o in out:
            d = o.get("stck_bsop_date")
            c = o.get("stck_clpr")
            if d and c and d not in rows:
                rows[d] = o
        oldest = min(o["stck_bsop_date"] for o in out)
        if oldest <= start or len(out) < 100:
            break
        cur_end = (datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    if not rows:
        return None

    recs = []
    for d in sorted(rows):
        o = rows[d]
        try:
            recs.append({
                "date": pd.Timestamp(datetime.strptime(d, "%Y%m%d")),
                "open": float(o["stck_oprc"]), "high": float(o["stck_hgpr"]),
                "low": float(o["stck_lwpr"]), "close": float(o["stck_clpr"]),
                "volume": float(o.get("acml_vol") or 0),
            })
        except (ValueError, TypeError, KeyError):
            continue
    df = pd.DataFrame(recs)
    if df.empty:
        return None
    df["change"] = df["close"].pct_change()
    return df


def _merge_fundamentals(new: pd.DataFrame, sym: str) -> pd.DataFrame:
    """Carry over annual fundamentals from the old parquet; recompute per/pbr on new close."""
    path = _OHLCV_DIR / f"{sym}.parquet"
    if path.exists():
        try:
            old = pl.read_parquet(path).to_pandas()
            keep = [c for c in _FUND_COLS if c in old.columns]
            if keep and "date" in old.columns:
                old["date"] = pd.to_datetime(old["date"])
                new = new.merge(old[["date"] + keep], on="date", how="left")
                for c in keep:
                    if c != "sector":
                        new[c] = new[c].ffill()  # forward-fill annual values across new dates
        except Exception:
            pass
    if "eps" in new.columns:
        eps = new["eps"]
        new["per"] = (new["close"] / eps).where(eps.notna() & (eps != 0))
    if "bps" in new.columns:
        bps = new["bps"]
        new["pbr"] = (new["close"] / bps).where(bps.notna() & (bps != 0))
    return new


def _load_done() -> set[str]:
    if _PROGRESS_PATH.exists():
        try:
            return set(json.loads(_PROGRESS_PATH.read_text()))
        except Exception:
            return set()
    return set()


def _save_done(done: set[str]) -> None:
    _PROGRESS_PATH.write_text(json.dumps(sorted(done)))


def main() -> None:
    master = json.loads(_MASTER_PATH.read_text(encoding="utf-8"))
    targets = [s for s in master["stocks"] if s.get("hasOhlcv")]
    done = _load_done()
    print(f"[resync] {len(targets)} commons, {len(done)} already done")

    ok = fail = skip = 0
    for i, s in enumerate(targets, 1):
        sym = s["symbol"]
        if sym in done:
            continue
        start = max(_START_FLOOR, (s.get("dataStart") or "2013-01-01").replace("-", ""))
        end = (s.get("dataEnd") or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
        try:
            df = _fetch_full(sym, start, end)
            if df is None or len(df) < 5:
                skip += 1
            else:
                df = _merge_fundamentals(df, sym)
                out = pl.from_pandas(df).with_columns(pl.col("date").cast(pl.Datetime("us")))
                out.write_parquet(_OHLCV_DIR / f"{sym}.parquet")
                ok += 1
        except Exception as e:
            fail += 1
            print(f"[resync] {sym} FAIL {repr(e)[:80]}")
        done.add(sym)
        if i % 50 == 0:
            _save_done(done)
            print(f"[resync] {i}/{len(targets)} ok={ok} skip={skip} fail={fail}")
    _save_done(done)
    print(f"[resync] DONE ok={ok} skip={skip} fail={fail}")


if __name__ == "__main__":
    main()
