"""Backfill a per-share cash ``dividends`` column into the OHLCV parquet files.

This is the data half of the dividend total-return feature (engine/dividends.py).
Once each parquet carries a ``dividends`` column (per-share cash on the ex-date,
0 elsewhere), backtests run with ``options.total_return=True`` reflect reinvested
dividends instead of price-return only.

Data source: pykrx ``get_market_fundamental_by_date`` exposes annual DPS (주당
배당금). Korean Dec-settlement firms go ex-dividend at year-end, so we attribute
each year's DPS to the **last trading day of that calendar year** present in the
symbol's price index (배당기준일 convention). This is an approximation suitable
for a research total-return series, not corporate-action-exact accounting.

Design:
  - ``build_dividend_series`` is pure (no network/IO) → unit-testable offline.
  - ``annual_dps_from_pykrx`` is the default provider; injectable for tests.
  - ``--dry-run`` reports changes without writing; ``--symbol`` / ``--limit``
    scope the run for safe incremental backfills.

Usage:
  python scripts/backfill_dividends.py --dry-run --limit 5
  python scripts/backfill_dividends.py --symbol 005930
  python scripts/backfill_dividends.py            # full backfill (writes parquet)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = _REPO_ROOT / "data" / "ohlcv"
sys.path.insert(0, str(_REPO_ROOT / "backend"))

# KIS_APP_KEY / KIS_APP_SECRET live in the repo-root .env (loaded by the backend
# app); a standalone script must load it explicitly or the KIS provider gets no creds.
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

# A provider maps a symbol + date bounds -> {calendar_year: dividend_per_share}.
DpsProvider = Callable[[str, str, str], Dict[int, float]]


def build_dividend_series(dates: pd.DatetimeIndex, annual_dps: Dict[int, float]) -> pd.Series:
    """Place each year's DPS on the last trading day of that year; 0 elsewhere.

    Args:
        dates: the symbol's price DatetimeIndex (ascending).
        annual_dps: {year: dividend_per_share}. Non-positive/zero amounts and
            years absent from ``dates`` are skipped.

    Returns:
        float Series aligned to ``dates`` (per-share cash dividend on the ex-date).
    """
    div = pd.Series(0.0, index=dates)
    if len(dates) == 0 or not annual_dps:
        return div
    years = pd.DatetimeIndex(dates).year
    for year, dps in annual_dps.items():
        try:
            dps = float(dps)
        except (TypeError, ValueError):
            continue
        if dps <= 0:
            continue
        in_year = dates[years == int(year)]
        if len(in_year) == 0:
            continue
        ex_date = in_year.max()  # last trading day of that calendar year
        div.loc[ex_date] = dps
    return div


def annual_dps_from_pykrx(symbol: str, start: str, end: str) -> Dict[int, float]:
    """Annual DPS per year from pykrx. Returns {} on any failure (offline/no data).

    pykrx reports a trailing annual DPS that updates after the AGM (≈ March). We
    take, for each calendar year, the max DPS observed in that year as the payout
    attributable to it (a robust read of the announced annual dividend).
    """
    try:
        from pykrx import stock
        df = stock.get_market_fundamental_by_date(start, end, symbol)
    except Exception as e:  # noqa: BLE001
        print(f"  [{symbol}] pykrx fetch failed: {e}")
        return {}
    if df is None or "DPS" not in getattr(df, "columns", []) or df.empty:
        return {}
    dps = df["DPS"].astype(float)
    by_year = dps.groupby(dps.index.year).max()
    return {int(y): float(v) for y, v in by_year.items() if v and v > 0}


def _to_float(raw) -> float:
    try:
        return float(str(raw).replace(",", "") or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_kis_dividends(records: List[dict]) -> Dict[int, float]:
    """Pure: KIS 예탁원 배당 레코드 리스트 → {연도: 주당 현금배당 합(분할조정)}.

    KIS ``ksdinfo/dividend`` output1 fields used:
      - ``record_date`` (기준일, YYYYMMDD) — 배당 귀속 연도 판정.
      - ``per_sto_divi_amt`` (주당 현금배당금, 원, 당시 액면 기준).
      - ``face_val`` (액면가) — 액면분할/병합 추적용.

    **분할조정:** parquet 가격은 (정방향)액면분할 조정 상태이므로 배당도 같은 기준으로
    맞춰야 한다. 액면가가 분할과 함께 바뀌므로(삼성 5000→100, 50:1) 각 배당을
    ``DPS × (최신 액면가 / 당시 액면가)`` 로 역조정한다. 예: 분할 전 17700원(액면 5000)
    × (100/5000) = 354원 → 분할 후 354원과 일치. 액면가 없으면 무조정(factor=1).
    중간/기말 배당은 같은 해로 합산, 현금배당만(주식배당 제외).
    """
    recs = [r for r in (records or [])
            if str(r.get("record_date") or "").strip()[:4].isdigit()]
    if not recs:
        return {}

    # 최신 기준일의 액면가 = 현재(=조정가격) 주식 기준.
    latest = max(recs, key=lambda r: str(r["record_date"]))
    latest_face = _to_float(latest.get("face_val"))

    by_year: Dict[int, float] = {}
    for rec in recs:
        rd = str(rec["record_date"]).strip()
        dps = _to_float(rec.get("per_sto_divi_amt"))
        if dps <= 0:
            continue
        rec_face = _to_float(rec.get("face_val"))
        if latest_face > 0 and rec_face > 0:
            dps *= latest_face / rec_face   # split back-adjustment
        by_year[int(rd[:4])] = by_year.get(int(rd[:4]), 0.0) + dps
    return by_year


_KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"
_TOKEN_CACHE = Path(os.getenv("TMPDIR", "/tmp")) / "kis_token_cache.json"


def _get_cached_kis_token() -> str | None:
    """디스크 캐시 기반 KIS 토큰 — 대량 작업 시 1분당 1회 발급 제한 회피.

    KIS 접근토큰은 24h 유효하지만 발급은 1분당 1회로 제한된다. 프로세스마다
    재발급하면 EGW00133에 막히므로 토큰을 디스크에 캐시해 모든 실행이 재사용한다.
    미설정/실패 시 None.
    """
    import json
    import time
    import requests

    try:
        if _TOKEN_CACHE.exists():
            cached = json.loads(_TOKEN_CACHE.read_text())
            if cached.get("token") and time.time() < cached.get("expires_at", 0):
                return cached["token"]
    except (OSError, ValueError):
        pass

    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        return None
    try:
        resp = requests.post(
            f"{_KIS_BASE_URL}/oauth2/tokenP",
            json={"grant_type": "client_credentials",
                  "appkey": app_key, "appsecret": app_secret},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  [KIS] token request failed: {resp.status_code} {resp.text[:120]}")
            return None
        token = resp.json().get("access_token")
        if token:
            # 24h 유효, 5분 여유 두고 만료 처리
            _TOKEN_CACHE.write_text(json.dumps(
                {"token": token, "expires_at": time.time() + 23 * 3600}))
        return token
    except Exception as e:  # noqa: BLE001
        print(f"  [KIS] token error: {e}")
        return None


def _kis_dividend_records(symbol: str, start: str, end: str) -> List[dict]:
    """KIS 예탁원 배당일정 API(HHKDB669102C0) 호출 → output1 레코드 리스트.

    토큰은 디스크 캐시(_get_cached_kis_token)로 재사용해 발급 제한을 피한다.
    크레덴셜(KIS_APP_KEY/KIS_APP_SECRET) 미설정/실패 시 빈 리스트(크래시 없음).
    """
    import requests

    token = _get_cached_kis_token()
    if not token:
        return []
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("KIS_APP_KEY", "").strip(),
        "appsecret": os.getenv("KIS_APP_SECRET", "").strip(),
        "tr_id": "HHKDB669102C0",
        "custtype": "P",
    }
    params = {
        "CTS": "", "GB1": "0", "F_DT": start, "T_DT": end,
        "SHT_CD": symbol, "HIGH_GB": "",
    }
    try:
        resp = requests.get(
            f"{_KIS_BASE_URL}/uapi/domestic-stock/v1/ksdinfo/dividend",
            headers=headers, params=params, timeout=15,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("output1", []) or []
    except Exception as e:  # noqa: BLE001
        print(f"  [{symbol}] KIS dividend fetch failed: {e}")
        return []


def annual_dps_from_kis(symbol: str, start: str, end: str) -> Dict[int, float]:
    """KIS 예탁원 배당 API 기반 연간 주당 현금배당. 실패 시 {}."""
    return _parse_kis_dividends(_kis_dividend_records(symbol, start, end))


PROVIDERS: Dict[str, DpsProvider] = {
    "kis": annual_dps_from_kis,
    "pykrx": annual_dps_from_pykrx,
}


def backfill_file(path: Path, provider: DpsProvider, dry_run: bool = False,
                  start: str = "19900101", end: str = "20251231") -> dict:
    """Backfill the ``dividends`` column for one parquet. Returns a stats dict."""
    df = pd.read_parquet(path)
    symbol = path.stem
    if "date" not in df.columns:
        return {"symbol": symbol, "status": "skip", "reason": "no date column", "events": 0}

    dates = pd.DatetimeIndex(pd.to_datetime(df["date"]))
    annual_dps = provider(symbol, start, end)
    series = build_dividend_series(dates, annual_dps)
    df["dividends"] = series.to_numpy()

    # 배당 메트릭 동시 산출: 배당수익률(TTM DPS/종가), 배당성향(TTM DPS/EPS).
    # dividends 컬럼이 전부 0(무배당)이어도 컬럼을 만들어 '데이터 있음(=0)'을 명시한다
    # — 커버리지 로그가 '무배당'과 '데이터 없음'을 구분하게 하기 위함.
    from engine.dividends import (
        trailing_dividend_yield, dividend_payout_ratio, dividend_growth_yoy,
    )
    close = df["close"].astype(float)
    close.index = dates
    div_ser = pd.Series(series.to_numpy(), index=dates)
    df["dividend_yield"] = trailing_dividend_yield(close, div_ser).to_numpy()
    df["dividend_growth"] = dividend_growth_yoy(div_ser).to_numpy()
    if "eps" in df.columns:
        eps = pd.Series(df["eps"].to_numpy(), index=dates)
        df["payout_rate"] = dividend_payout_ratio(div_ser, eps).to_numpy()

    events = int((series > 0).sum())
    total = float(series.sum())
    if not dry_run:
        df.to_parquet(path)
    return {
        "symbol": symbol,
        "status": "written" if not dry_run else "dry-run",
        "events": events,
        "total_dps": round(total, 2),
        "rows": len(df),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill per-share dividends into OHLCV parquet.")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--symbol", help="backfill a single symbol only")
    ap.add_argument("--limit", type=int, help="process at most N files")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--source", choices=sorted(PROVIDERS), default="kis",
                    help="dividend data source (default: kis)")
    ap.add_argument("--sleep", type=float, default=0.06,
                    help="seconds between API calls (KIS rate-limit guard)")
    ap.add_argument("--start", default="19900101")
    ap.add_argument("--end", default="20251231")
    args = ap.parse_args()
    provider = PROVIDERS[args.source]

    data_dir: Path = args.data_dir
    if args.symbol:
        files = [data_dir / f"{args.symbol}.parquet"]
    else:
        files = sorted(data_dir.glob("*.parquet"))
    if args.limit:
        files = files[: args.limit]

    import time
    print(f"Backfilling dividends for {len(files)} file(s) "
          f"[source={args.source}] ({'DRY-RUN' if args.dry_run else 'WRITE'})...")
    with_div = processed = 0
    for path in files:
        if not path.exists():
            print(f"  [{path.stem}] not found — skip")
            continue
        stats = backfill_file(path, provider, args.dry_run, args.start, args.end)
        processed += 1
        if stats.get("events", 0) > 0:
            with_div += 1
            print(f"  [{stats['symbol']}] {stats['events']} ex-dates, "
                  f"total DPS {stats['total_dps']} ({stats['status']})", flush=True)
        if processed % 200 == 0:
            print(f"  ...progress {processed}/{len(files)} ({with_div} with dividends)", flush=True)
        if args.sleep:
            time.sleep(args.sleep)
    print(f"Done. {with_div}/{processed} symbols had dividend events.")


if __name__ == "__main__":
    main()
