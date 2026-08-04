"""Backfill a per-share cash ``dividends`` column into the OHLCV parquet files.

This is the data half of the dividend total-return feature (engine/dividends.py).
Once each parquet carries a ``dividends`` column (per-share cash on the ex-date,
0 elsewhere), backtests run with ``options.total_return=True`` reflect reinvested
dividends instead of price-return only.

Data source: KIS 예탁원 배당일정 API가 배당 **건별 기준일(record_date)**과 주당 현금배당을
준다. 각 배당은 그 기준일 **이하의 마지막 거래일**에 찍는다(배당기준일 convention).
연말 결산 배당은 이 규칙이 곧 '그 해 마지막 거래일'이라 기존 배치와 같지만, 분기·중간
배당은 실제 지급 시점에 흩어진다 — TTM(최근 252거래일) 합이 말 그대로 '최근 12개월 실제
지급액'이 된다. 기업행사 단위로 정확한 회계가 아니라 리서치용 총수익 근사다.

.. note:: 2026-08-04 이전에는 배당을 **연도 단위로 합산해 그 해 마지막 거래일 한 점**에
   몰아 찍었다. 진행 중인 해의 부분 배당이 직전 연말 배치와 7개월 간격으로 들어가 TTM 창
   안에서 겹쳐 세지는 문제가 있었다(삼성전자 실측: TTM 1,668원 → 2,414원, 45% 과대).
   기준일 배치는 이 왜곡 없이 당해 연도 배당을 반영한다.

Design:
  - ``build_dividend_series`` is pure (no network/IO) → unit-testable offline.
  - ``dps_by_record_date_from_kis`` is the default provider; injectable for tests.
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
from datetime import datetime
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

# A provider maps a symbol + date bounds -> {record_date "YYYYMMDD": dividend_per_share}.
DpsProvider = Callable[[str, str, str], Dict[str, float]]


def build_dividend_series(dates: pd.DatetimeIndex, dps_by_date: Dict[str, float]) -> pd.Series:
    """Place each dividend on the last trading day at/before its record date; 0 elsewhere.

    Args:
        dates: the symbol's price DatetimeIndex (ascending).
        dps_by_date: {record_date "YYYYMMDD": dividend_per_share}. 다음은 제외한다 —
            0 이하 금액, 파싱 불가 날짜, **첫 봉 이전** 기준일(찍을 자리가 없다),
            **마지막 봉 이후** 기준일.

    마지막 봉 이후를 제외하는 이유는 둘이다. ① KIS 배당일정 API는 아직 도래하지 않은
    **예정 배당**도 준다 — 마지막 봉(=오늘)에 찍으면 미래 정보 누출이다. ② 상장폐지 종목의
    **청산 분배금**이 폐지 한참 뒤 기준일로 잡힌다(실측: 460280·441330·394350이 마지막 봉
    +454일, 207720 스팩이 +82일, 0001S0이 +2일). 엔진은 상폐 시 강제청산하므로 이 분배금은
    실제로 받지 못하는데, 금액이 주가와 맞먹어(청산=원금 반환) 마지막 봉에 찍으면 배당수익률이
    100%를 넘는 유령 고배당주가 된다 — 2026-08-04 실측 17종목.

    Returns:
        float Series aligned to ``dates`` (per-share cash dividend on the ex-date).
        같은 거래일로 떨어지는 배당이 둘 이상이면 합산한다(휴장 구간에 기준일이 몰린 경우).
    """
    div = pd.Series(0.0, index=dates)
    if len(dates) == 0 or not dps_by_date:
        return div
    for raw_date, dps in dps_by_date.items():
        try:
            dps = float(dps)
        except (TypeError, ValueError):
            continue
        if dps <= 0:
            continue
        try:
            record_date = pd.Timestamp(datetime.strptime(str(raw_date).strip(), "%Y%m%d"))
        except (TypeError, ValueError):
            continue
        if record_date > dates[-1]:
            continue  # 미도래 예정 배당 / 상폐 후 청산 분배금 — 받을 수 없다
        pos = dates.searchsorted(record_date, side="right") - 1
        if pos < 0:
            continue  # 상장 이전 배당 — 가격 인덱스에 배치할 자리가 없다
        div.iloc[pos] += dps
    return div


def dps_by_year_end_from_pykrx(symbol: str, start: str, end: str) -> Dict[str, float]:
    """Annual DPS from pykrx, keyed by that year's 12-31. {} on any failure.

    pykrx reports a trailing annual DPS that updates after the AGM (≈ March). We
    take, for each calendar year, the max DPS observed in that year as the payout
    attributable to it (a robust read of the announced annual dividend).

    KIS와 달리 pykrx는 배당 **건별 기준일**을 주지 않는다 — 연 단위 값뿐이라 12-31을
    기준일로 삼는다(배치 규칙상 그 해 마지막 거래일에 찍힌다). 분기 배당은 연말 한 점으로
    합쳐지므로, 기준일 정밀도가 필요하면 기본 provider인 KIS를 쓴다.
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
    return {f"{int(y)}1231": float(v) for y, v in by_year.items() if v and v > 0}


# KRX 액면가 정본 집합. 실측(120종목 표본·배당 레코드 1,369건)에서 관측된 값은 이 6종이
# 전부였고 5,000원 초과는 0건 — 그 밖의 값은 데이터 오염이다(002005의 폐지 후 레코드가
# 500,000원으로 기록돼 과거 배당이 100배로 부풀었다, 2026-08-04).
_VALID_FACE_VALUES = frozenset({100.0, 200.0, 500.0, 1000.0, 2500.0, 5000.0})


def _to_float(raw) -> float:
    try:
        return float(str(raw).replace(",", "") or 0)
    except (TypeError, ValueError):
        return 0.0


def _face_value(rec: dict) -> float:
    """레코드의 액면가 — 정본 집합 밖의 값은 오염으로 보고 0(무조정) 처리."""
    fv = _to_float(rec.get("face_val"))
    return fv if fv in _VALID_FACE_VALUES else 0.0


def _parse_kis_dividends(records: List[dict]) -> Dict[str, float]:
    """Pure: KIS 예탁원 배당 레코드 리스트 → {기준일 "YYYYMMDD": 주당 현금배당 합(분할조정)}.

    KIS ``ksdinfo/dividend`` output1 fields used:
      - ``record_date`` (기준일, YYYYMMDD) — 배당을 찍을 시점.
      - ``per_sto_divi_amt`` (주당 현금배당금, 원, 당시 액면 기준).
      - ``face_val`` (액면가) — 액면분할/병합 추적용.

    **분할조정:** parquet 가격은 (정방향)액면분할 조정 상태이므로 배당도 같은 기준으로
    맞춰야 한다. 액면가가 분할과 함께 바뀌므로(삼성 5000→100, 50:1) 각 배당을
    ``DPS × (최신 액면가 / 당시 액면가)`` 로 역조정한다. 예: 분할 전 17700원(액면 5000)
    × (100/5000) = 354원 → 분할 후 354원과 일치. 액면가 없으면 무조정(factor=1).
    중간/기말 배당은 **각자의 기준일에 남고**(같은 기준일끼리만 합산), 현금배당만(주식배당 제외).

    조정 기준은 **가장 최근의 유효한 액면가**다(=현재 주식 기준 = parquet 가격의 조정 기준).
    `_VALID_FACE_VALUES` 밖의 값은 오염으로 보고 후보에서 뺀다 — 그러지 않으면 상장폐지 후
    레코드의 500,000원이 기준이 되어 과거 배당이 100배가 된다(002005, 배당수익률 1,069%).

    .. note:: '배당이 있는 레코드 중 최신'으로 좁히는 방식은 **틀렸다**(2026-08-04 시도 후
       철회). 마지막 배당 **이후에 액면분할**한 종목이 깨진다 — 001080(1,000→100),
       002420·006345(5,000→500)는 최신 배당 레코드가 분할 전 액면가라 역조정이 사라져
       배당이 10배로 남았다. 무배당 레코드도 '현재 액면가'라는 정보는 정확히 준다.
    """
    recs = [r for r in (records or [])
            if str(r.get("record_date") or "").strip()[:4].isdigit()]
    if not recs:
        return {}

    # 최신 유효 액면가 = 현재(=조정가격) 주식 기준.
    with_face = [r for r in recs if _face_value(r) > 0]
    latest_face = (_face_value(max(with_face, key=lambda r: str(r["record_date"])))
                   if with_face else 0.0)

    by_date: Dict[str, float] = {}
    for rec in recs:
        rd = str(rec["record_date"]).strip()
        dps = _to_float(rec.get("per_sto_divi_amt"))
        if dps <= 0:
            continue
        rec_face = _face_value(rec)
        if latest_face > 0 and rec_face > 0:
            dps *= latest_face / rec_face   # split back-adjustment
        by_date[rd] = by_date.get(rd, 0.0) + dps
    return by_date


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


def dps_by_record_date_from_kis(symbol: str, start: str, end: str) -> Dict[str, float]:
    """KIS 예탁원 배당 API 기반 기준일별 주당 현금배당. 실패 시 {}."""
    return _parse_kis_dividends(_kis_dividend_records(symbol, start, end))


PROVIDERS: Dict[str, DpsProvider] = {
    "kis": dps_by_record_date_from_kis,
    "pykrx": dps_by_year_end_from_pykrx,
}


def _today() -> str:
    """조회 종료일 기본값(YYYYMMDD). 상수로 박으면 그 해가 지난 뒤 당해 배당이 조용히
    누락된다 — 실제로 `20251231`이 박혀 있어 2026년 배당 전량이 빠졌다(2026-08-04)."""
    return datetime.now().strftime("%Y%m%d")


def backfill_file(path: Path, provider: DpsProvider, dry_run: bool = False,
                  start: str = "19900101", end: str | None = None) -> dict:
    """Backfill the ``dividends`` column for one parquet. Returns a stats dict."""
    df = pd.read_parquet(path)
    symbol = path.stem
    if "date" not in df.columns:
        return {"symbol": symbol, "status": "skip", "reason": "no date column", "events": 0}

    dates = pd.DatetimeIndex(pd.to_datetime(df["date"]))
    dps_by_date = provider(symbol, start, end or _today())
    series = build_dividend_series(dates, dps_by_date)
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
    ap.add_argument("--end", default=_today(),
                    help="조회 종료일(YYYYMMDD). 기본값은 실행일 — 당해 배당 누락 방지")
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
