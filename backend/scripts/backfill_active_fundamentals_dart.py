"""Backfill BPS/EPS/ROE/부채비율 for ACTIVE (listed) stocks from DART, years-only gaps.

Motivation: KIS's financial-ratio API and Naver Finance only serve recent history — in
practice back to ~2005-2006 (e.g. 005930's bps series starts 2005-03-30). Local OHLCV
goes back to 1996 for most names, so every active stock has a fixed multi-year gap in
bps/eps/pbr/per before that floor, plus ~550 tickers where KIS/Naver return nothing at
all (see scripts/backfill_fundamentals.py run — 'no_data'). DART (전자공시) has annual
reports for a stock's whole listed history, same source already used for delisted names
in backfill_delisted_fundamentals.py.

For each active stock-master symbol we find the fiscal years where ``bps`` is entirely
missing across the parquet, pull DART 자본총계/부채총계/당기순이익 for exactly those years,
derive BPS = 자본총계 / 현재상장주식수 (same current-shares approximation the delisted
script and market_cap fallback already use), and merge non-destructively via
engine.fundamental_backfill.merge_fundamentals (combine_first — existing KIS/Naver years
are never touched).

Idempotent/resumable: re-running only refetches years still missing in the parquet, so a
DART daily-quota cutoff (status "020") just needs a re-run another day.

Usage:
  cd backend && python scripts/backfill_active_fundamentals_dart.py --dry-run --limit 5
  cd backend && python scripts/backfill_active_fundamentals_dart.py
  cd backend && python scripts/backfill_active_fundamentals_dart.py --symbol 000020
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import polars as pl
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.fundamental_backfill import merge_fundamentals  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_MASTER_PATH = _PROJECT_ROOT / "data" / "stock-master.json"
_CORPCODE_CACHE = _PROJECT_ROOT / "data" / "dart_corpcode.json"

_DART = "https://opendart.fss.or.kr/api"
_ANNUAL = "11011"  # 사업보고서
_SLEEP = 0.05
# DART's structured financial-statement API (fnlttSinglAcnt) only covers filings from
# fiscal year 2015 onward (pre-XBRL-standardization years return status "013" — no
# data — for every symbol, confirmed empirically). Gap years before this floor cannot
# be filled by DART at all, so we skip them to avoid wasted calls.
_DART_YEAR_FLOOR = 2015

load_dotenv(_PROJECT_ROOT / ".env")
_KEY = os.getenv("DART_API_KEY", "").strip()


class QuotaExceeded(Exception):
    pass


def _load_corpcode() -> dict[str, str]:
    return json.loads(_CORPCODE_CACHE.read_text(encoding="utf-8"))


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _fetch_year(corp_code: str, year: int) -> dict | None:
    """Annual 자본총계/부채총계/당기순이익 for a fiscal year (consolidated preferred)."""
    r = requests.get(
        f"{_DART}/fnlttSinglAcnt.json",
        params={"crtfc_key": _KEY, "corp_code": corp_code,
                "bsns_year": str(year), "reprt_code": _ANNUAL},
        timeout=15,
    ).json()
    status = r.get("status")
    if status == "020":
        raise QuotaExceeded(r.get("message", "quota exceeded"))
    if status != "000":
        return None
    by_div: dict[str, dict[str, str]] = {}
    for it in r.get("list", []):
        by_div.setdefault(it.get("fs_div", "OFS"), {})[it.get("account_nm", "")] = it.get("thstrm_amount")
    accounts = by_div.get("CFS") or by_div.get("OFS") or {}

    def pick(target: str) -> float | None:
        if target in accounts:
            return _num(accounts[target])
        for nm, v in accounts.items():
            if target in nm:
                return _num(v)
        return None

    equity = pick("자본총계")
    debt = pick("부채총계")
    income = pick("당기순이익")
    if equity is None:
        return None
    return {"equity": equity, "debt": debt, "income": income}


def _gap_years(pdf: pd.DataFrame) -> list[int]:
    """Fiscal years (up to last completed year) where bps is entirely missing.

    A parquet with no ``bps`` column at all (never enriched, e.g. REITs whose Naver
    page has no EPS/BPS table) is the worst case, not "no gap" — every year is missing.
    """
    if pdf.empty:
        return []
    years = pd.to_datetime(pdf["date"]).dt.year
    current_year = pd.Timestamp.now().year
    start = max(_DART_YEAR_FLOOR, int(years.min()))
    if "bps" not in pdf.columns:
        return [y for y in range(start, current_year) if (years == y).any()]
    return [
        y for y in range(start, current_year)
        if (years == y).any() and pdf.loc[years == y, "bps"].isna().all()
    ]


def process_symbol(symbol: str, shares, corp_code: str, *, dry_run: bool) -> str:
    path = _OHLCV_DIR / f"{symbol}.parquet"
    if not path.exists():
        return "missing_parquet"
    pdf = pl.read_parquet(path).to_pandas()
    gap_years = _gap_years(pdf)
    if not gap_years:
        return "skip_no_gap"
    if not shares:
        return "no_shares"

    fundamentals = []
    for year in gap_years:
        fin = _fetch_year(corp_code, year)
        time.sleep(_SLEEP)
        if not fin:
            continue
        equity, debt, income = fin["equity"], fin["debt"], fin["income"]
        entry = {"year_end": f"{year}-12-31", "bps": equity / shares}
        if income is not None:
            entry["eps"] = income / shares
            if equity:
                entry["roe_or_gpa"] = income / equity * 100.0
        if debt is not None and equity:
            entry["debt_ratio"] = debt / equity * 100.0
        fundamentals.append(entry)

    if not fundamentals:
        return "no_dart_data"

    merged = merge_fundamentals(pdf, fundamentals)
    if not dry_run:
        pl.from_pandas(merged).write_parquet(path)
    return "enriched"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", help="single 6-digit ticker")
    ap.add_argument("--limit", type=int, help="process at most N stocks")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not _KEY:
        print("[dart-gap] DART_API_KEY not set")
        return

    master = json.loads(_MASTER_PATH.read_text(encoding="utf-8"))
    sym2corp = _load_corpcode()
    targets = [s for s in master["stocks"] if not s.get("delistingDate") and s.get("hasOhlcv")]
    if args.symbol:
        targets = [s for s in targets if s["symbol"] == args.symbol]
    if args.limit:
        targets = targets[: args.limit]

    print(f"[dart-gap] {len(targets)} active stocks; corpCode map={len(sym2corp)}")
    tally: dict[str, int] = {}
    for i, s in enumerate(targets, 1):
        sym = s["symbol"]
        corp = sym2corp.get(sym)
        if not corp:
            status = "no_corp"
        else:
            try:
                status = process_symbol(sym, s.get("shares"), corp, dry_run=args.dry_run)
            except QuotaExceeded as e:
                print(f"[dart-gap] DART quota exceeded at {i}/{len(targets)} ({sym}): {e}")
                break
            except Exception as e:  # noqa: BLE001 — one bad symbol must not kill the batch
                status = "error"
                print(f"  [{sym}] error: {e}")
        tally[status] = tally.get(status, 0) + 1
        if status == "enriched" and (i <= 10 or i % 50 == 0):
            print(f"  [{i}/{len(targets)}] {sym}: {status}")
        elif i % 200 == 0:
            print(f"  [{i}/{len(targets)}] progress {dict(sorted(tally.items()))}")

    print(f"[dart-gap] done: {dict(sorted(tally.items()))}")


if __name__ == "__main__":
    main()
