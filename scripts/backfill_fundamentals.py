"""Backfill annual fundamentals (EPS/BPS/ROE/PER/PBR/부채비율) into OHLCV parquet files.

Motivation: the parquets already carry EPS/BPS/ROE/PER/PBR (originally from pykrx),
but the ``debt_ratio`` column was created and left **entirely null** — pykrx never
served 부채비율. As a result every "부채비율 <= N" filter silently passes (DataResolver
logs "미해결 데이터 … 통과 처리됩니다"), so the constraint was never actually applied.

This script fills that gap for **active/listed** stocks using the already-tested
fetcher in ``engine.fundamental_fetcher``:

    fetch_fundamentals(symbol)  →  KIS financial-ratio API (EPS/BPS/ROE/부채비율,
                                   ~20y history) → Naver Finance scrape (recent ~4y)
                                   → 90-day local JSON cache.

Merge semantics (non-destructive — we *add*, never lose existing coverage):
  - For each fundamental column we prefer the freshly-fetched value and fall back to
    the value already in the parquet (``combine_first``). So debt_ratio gets populated
    where it was null, recent EPS/BPS/ROE get refreshed, and any older pykrx history
    the API lacks is preserved.
  - ROE is derived as EPS/BPS*100 (= 당기순이익/자본총계, exact) wherever ROE is
    missing or reported as 0 by the API but EPS & BPS are present.
  - PER/PBR are recomputed from close ÷ merged EPS/BPS so they stay consistent.

Delisted tickers (KIS/Naver don't serve them) are handled separately by
``backend/scripts/backfill_delisted_fundamentals.py`` (DART). Symbols with no API data
are left untouched.

Idempotent / resumable: a symbol whose ``debt_ratio`` is already populated is skipped
unless ``--force``. ``fetch_fundamentals`` also caches per-symbol JSON, so re-runs are
cheap.

Usage:
  python scripts/backfill_fundamentals.py --dry-run --limit 5
  python scripts/backfill_fundamentals.py --symbol 005930
  python scripts/backfill_fundamentals.py                 # full backfill (writes)
  python scripts/backfill_fundamentals.py --force         # re-fetch even if filled
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# polars/torch deadlock + libomp guards (must precede polars import — see memory).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import json

import polars as pl
import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"
sys.path.insert(0, str(_REPO_ROOT / "backend"))

import engine.fundamental_fetcher as ff  # noqa: E402
from engine.fundamental_fetcher import fetch_fundamentals  # noqa: E402
# Canonical non-destructive merge + market_cap, shared with the daily scheduler sync.
from engine.fundamental_backfill import (  # noqa: E402
    SENTINEL_COL as _SENTINEL_COL,
    merge_fundamentals,
    add_market_cap,
    needs_backfill as _needs_backfill,
)

# KIS access tokens are valid ~24h but issuance is throttled to 1/min (EGW00133).
# A long batch must obtain one token and reuse it; we persist it to disk (shared with
# backfill_dividends.py) so repeated runs don't trip the throttle, then seed the
# fetcher's in-process token so every fetch_fundamentals call rides on KIS (deep
# ~20y history incl. 부채비율) instead of falling back to Naver's recent ~4y.
_KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
_TOKEN_CACHE = Path(os.getenv("TMPDIR", "/tmp")) / "kis_token_cache.json"


def ensure_kis_token() -> bool:
    """Seed ff._KIS_TOKEN from a disk-cached or freshly issued KIS token. False if unavailable."""
    token = None
    expires_at = 0.0
    try:
        if _TOKEN_CACHE.exists():
            cached = json.loads(_TOKEN_CACHE.read_text())
            if cached.get("token") and time.time() < cached.get("expires_at", 0):
                token, expires_at = cached["token"], cached["expires_at"]
    except (OSError, ValueError):
        pass

    if not token:
        app_key = os.getenv("KIS_APP_KEY", "").strip()
        app_secret = os.getenv("KIS_APP_SECRET", "").strip()
        if not app_key or not app_secret:
            return False
        try:
            resp = requests.post(
                f"{_KIS_BASE_URL}/oauth2/tokenP",
                json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"  [KIS] token request failed: {resp.status_code} {resp.text[:120]}")
                return False
            token = resp.json().get("access_token")
            if not token:
                return False
            expires_at = time.time() + 23 * 3600
            _TOKEN_CACHE.write_text(json.dumps({"token": token, "expires_at": expires_at}))
        except Exception as e:  # noqa: BLE001
            print(f"  [KIS] token error: {e}")
            return False

    ff._KIS_TOKEN = token
    ff._KIS_TOKEN_EXPIRES_AT = expires_at
    return True


def process_symbol(path: Path, *, force: bool, dry_run: bool) -> str:
    """Backfill one parquet. Returns a short status code for tallying."""
    symbol = path.stem
    pdf = pl.read_parquet(path).to_pandas()

    if not force and not _needs_backfill(pdf):
        return "skip_filled"

    # Bypass the 90-day per-symbol cache: existing caches predate the new factors, so
    # reading them would perpetuate the gap. fetch_fundamentals still re-writes the cache.
    fundamentals = fetch_fundamentals(symbol, use_cache=False)
    merged = merge_fundamentals(pdf, fundamentals) if fundamentals else pdf
    merged = add_market_cap(merged, symbol)

    annual_filled = bool(fundamentals) and merged[_SENTINEL_COL].notna().any()
    has_market_cap = "market_cap" in merged.columns and merged["market_cap"].notna().any()
    if not annual_filled and not has_market_cap:
        return "no_data"

    if not dry_run:
        pl.from_pandas(merged).write_parquet(path)
    return "enriched" if annual_filled else "market_cap_only"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", help="single 6-digit ticker")
    ap.add_argument("--limit", type=int, help="process at most N parquets")
    ap.add_argument("--force", action="store_true", help="re-fetch even if debt_ratio already filled")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between symbols")
    args = ap.parse_args()

    if args.symbol:
        paths = [_OHLCV_DIR / f"{args.symbol}.parquet"]
    else:
        paths = sorted(_OHLCV_DIR.glob("*.parquet"))
    if args.limit:
        paths = paths[: args.limit]

    kis_ok = ensure_kis_token()
    tally: dict[str, int] = {}
    total = len(paths)
    print(f"[fund] {total} parquet(s); dry_run={args.dry_run} force={args.force} kis={'on' if kis_ok else 'off→naver'}")

    for i, path in enumerate(paths, 1):
        if not path.exists():
            print(f"  [{path.stem}] missing parquet")
            tally["missing"] = tally.get("missing", 0) + 1
            continue
        try:
            status = process_symbol(path, force=args.force, dry_run=args.dry_run)
        except Exception as e:  # noqa: BLE001 — one bad file must not kill the batch
            status = "error"
            print(f"  [{path.stem}] error: {e}")
        tally[status] = tally.get(status, 0) + 1
        if status in ("enriched", "no_data", "error") and (i <= 10 or i % 50 == 0):
            print(f"  [{i}/{total}] {path.stem}: {status}")
        if args.sleep:
            time.sleep(args.sleep)

    print(f"[fund] done: {dict(sorted(tally.items()))}")


if __name__ == "__main__":
    main()
