"""시장지수(코스피·코스닥) 일봉 시계열 백필·갱신 → data/index/<MARKET>.parquet.

소스와 우선순위
---------------
1. **토스증권 Open API** `GET /api/v1/market-indicators/{KOSPI|KOSDAQ}/candles` (interval=1d,
   200봉/호출, before 페이지네이션). 실측(2026-09-13) 제공 하한 2014-07-01. 정본.
2. **KIS(한국투자증권)** `inquire-daily-indexchartprice`(FHKUP03500100, 코스피 0001·코스닥
   1001) — 호출당 최대 50행, 기간 지정. 토스가 없는 2014-06-30 이전 구간만 보충한다
   (실측: 코스피 1996-01~, 코스닥 2000-01~ 응답. 그 이전은 빈 응답).
   같은 날짜가 양쪽에 있으면 토스 값을 쓴다(source 컬럼에 출처 기록).

실행
----
    python backend/scripts/backfill_index_history.py            # 갱신: 토스 최근 200봉 upsert
    python backend/scripts/backfill_index_history.py --full     # 전체: 토스 전 구간 + KIS 보충
    python backend/scripts/backfill_index_history.py --markets KOSPI

야간 갱신은 scripts/sync_data.py가 기본 모드(갱신)로 부른다. 파케이가 없으면 갱신 모드도
자동으로 전체 백필을 한다. 스키마: date(Datetime us)·open·high·low·close·volume·source.

이 스크립트는 사용자 원문을 읽지 않는다(데이터 파이프라인).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "backend"))

from engine.market_index import INDEX_COLUMNS, INDEX_MARKETS  # noqa: E402

_INDEX_DIR = _PROJECT_ROOT / "data" / "index"

_TOSS = "https://openapi.tossinvest.com"
_TOSS_PAGE = 200
_TOSS_SLEEP = 0.25          # MARKET_INDICATOR_CHART 초당 5회 한도
_KIS = "https://openapi.koreainvestment.com:9443"
_KIS_CHART = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
_KIS_CODES = {"KOSPI": "0001", "KOSDAQ": "1001"}
_KIS_WINDOW_DAYS = 60       # 달력일 창(≈41거래일) — 호출당 50행 상한 아래
_KIS_FLOOR = "19960101"     # 종목 OHLCV 백필 하한과 동일(KIS 제공 하한)
_KIS_SLEEP = 0.1
_KIS_EMPTY_STREAK_STOP = 6  # 연속 빈 창이면 제공 하한에 닿은 것으로 본다
_TOSS_FLOOR = pd.Timestamp("2014-07-01")  # 실측 제공 하한 — KIS 보충 상한


# ── 순수 변환(테스트 대상) ────────────────────────────────────────────────────

def toss_rows_to_frame(rows: List[dict]) -> pd.DataFrame:
    """토스 candles 응답 행 → 표준 프레임(날짜 오름차순, source='toss')."""
    if not rows:
        return _empty()
    df = pd.DataFrame({
        "date": pd.to_datetime([r["timestamp"][:10] for r in rows]),
        "open": [float(r["openPrice"]) for r in rows],
        "high": [float(r["highPrice"]) for r in rows],
        "low": [float(r["lowPrice"]) for r in rows],
        "close": [float(r["closePrice"]) for r in rows],
        "volume": [float(r.get("volume") or 0) for r in rows],
    })
    df["source"] = "toss"
    return _normalize(df)


def kis_rows_to_frame(rows: List[dict]) -> pd.DataFrame:
    """KIS 지수 일봉 응답 행(output2) → 표준 프레임(source='kis')."""
    rows = [r for r in rows if r.get("stck_bsop_date")]
    if not rows:
        return _empty()
    df = pd.DataFrame({
        "date": pd.to_datetime([r["stck_bsop_date"] for r in rows], format="%Y%m%d"),
        "open": [float(r["bstp_nmix_oprc"]) for r in rows],
        "high": [float(r["bstp_nmix_hgpr"]) for r in rows],
        "low": [float(r["bstp_nmix_lwpr"]) for r in rows],
        "close": [float(r["bstp_nmix_prpr"]) for r in rows],
        "volume": [float(r.get("acml_vol") or 0) for r in rows],
    })
    df["source"] = "kis"
    return _normalize(df)


def merge_sources(primary: pd.DataFrame, secondary: pd.DataFrame) -> pd.DataFrame:
    """같은 날짜는 primary(토스)가 이긴다. 결과는 날짜 오름차순·중복 없음."""
    frames = [f for f in (primary, secondary) if f is not None and len(f)]
    if not frames:
        return _empty()
    merged = pd.concat(frames, ignore_index=True)
    # keep='first' — primary 행이 앞에 있으므로 primary가 남는다.
    merged = merged.drop_duplicates(subset="date", keep="first")
    return _normalize(merged)


def upsert(existing: Optional[pd.DataFrame], fresh: pd.DataFrame) -> pd.DataFrame:
    """기존 파케이에 새 봉을 덮어쓰기 병합(새 값 우선) — 야간 갱신용."""
    return merge_sources(fresh, existing if existing is not None else _empty())


def _empty() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="datetime64[ns]" if c == "date" else
                                       ("object" if c == "source" else "float64"))
                         for c in INDEX_COLUMNS})


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df[list(INDEX_COLUMNS)].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    return df.sort_values("date").drop_duplicates(subset="date", keep="first").reset_index(drop=True)


# ── 토스 ─────────────────────────────────────────────────────────────────────

class TossIndexClient:
    def __init__(self, client_id: str, client_secret: str, session: Optional[requests.Session] = None):
        self._id, self._secret = client_id, client_secret
        self._s = session or requests.Session()
        self._token: Optional[str] = None

    def _headers(self) -> dict:
        if not self._token:
            r = self._s.post(f"{_TOSS}/oauth2/token", data={
                "grant_type": "client_credentials",
                "client_id": self._id, "client_secret": self._secret,
            }, timeout=10)
            r.raise_for_status()
            self._token = r.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}"}

    def fetch_candles(self, market: str, max_pages: Optional[int] = None) -> List[dict]:
        """최신부터 과거로 200봉씩 넘겨 전부(또는 max_pages) 수집."""
        rows: List[dict] = []
        before: Optional[str] = None
        pages = 0
        while True:
            params = {"interval": "1d", "count": _TOSS_PAGE}
            if before:
                params["before"] = before
            r = self._s.get(f"{_TOSS}/api/v1/market-indicators/{market}/candles",
                            headers=self._headers(), params=params, timeout=15)
            r.raise_for_status()
            result = r.json().get("result", {})
            candles = result.get("candles", [])
            rows.extend(candles)
            pages += 1
            next_before = result.get("nextBefore")
            if not candles or len(candles) < _TOSS_PAGE or not next_before or next_before == before:
                break
            if max_pages is not None and pages >= max_pages:
                break
            before = next_before
            time.sleep(_TOSS_SLEEP)
        return rows


# ── KIS ──────────────────────────────────────────────────────────────────────

class KisIndexClient:
    def __init__(self, app_key: str, app_secret: str, session: Optional[requests.Session] = None):
        self._ak, self._sk = app_key, app_secret
        self._s = session or requests.Session()
        self._token: Optional[str] = None

    def _headers(self) -> dict:
        if not self._token:
            r = self._s.post(f"{_KIS}/oauth2/tokenP", json={
                "grant_type": "client_credentials", "appkey": self._ak, "appsecret": self._sk,
            }, timeout=15)
            r.raise_for_status()
            self._token = r.json()["access_token"]
        return {"authorization": f"Bearer {self._token}", "appkey": self._ak,
                "appsecret": self._sk, "tr_id": "FHKUP03500100", "custtype": "P"}

    def fetch_window(self, code: str, d0: str, d1: str) -> List[dict]:
        for attempt in range(4):
            try:
                r = self._s.get(f"{_KIS}{_KIS_CHART}", headers=self._headers(), params={
                    "FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": code,
                    "FID_INPUT_DATE_1": d0, "FID_INPUT_DATE_2": d1, "FID_PERIOD_DIV_CODE": "D",
                }, timeout=15)
                j = r.json()
                if j.get("rt_cd") == "0":
                    return j.get("output2", []) or []
            except Exception:
                pass
            time.sleep(0.5 * (attempt + 1))
        return []

    def fetch_before(self, market: str, until: pd.Timestamp, floor: str = _KIS_FLOOR) -> List[dict]:
        """until(배타) 이전 구간을 창 단위로 거슬러 올라가며 수집."""
        code = _KIS_CODES[market]
        rows: List[dict] = []
        end = until - timedelta(days=1)
        floor_ts = pd.Timestamp(floor)
        empty_streak = 0
        while end >= floor_ts:
            start = max(end - timedelta(days=_KIS_WINDOW_DAYS - 1), floor_ts)
            got = self.fetch_window(code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            if got:
                rows.extend(got)
                empty_streak = 0
            else:
                empty_streak += 1
                if empty_streak >= _KIS_EMPTY_STREAK_STOP:
                    break
            end = start - timedelta(days=1)
            time.sleep(_KIS_SLEEP)
        return rows


# ── 저장소 ───────────────────────────────────────────────────────────────────

def read_index(market: str, index_dir: Path = _INDEX_DIR) -> Optional[pd.DataFrame]:
    path = index_dir / f"{market}.parquet"
    if not path.exists():
        return None
    return _normalize(pd.read_parquet(path))


def write_index(market: str, df: pd.DataFrame, index_dir: Path = _INDEX_DIR) -> Path:
    index_dir.mkdir(parents=True, exist_ok=True)
    path = index_dir / f"{market}.parquet"
    out = _normalize(df)
    out["date"] = out["date"].astype("datetime64[us]")   # OHLCV 파케이와 같은 dtype(조인 키)
    tmp = path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)                                # 쓰기 도중 절단 방지(원자 교체)
    return path


# ── 실행 ─────────────────────────────────────────────────────────────────────

def _seam_report(toss: pd.DataFrame, kis: pd.DataFrame) -> str:
    """두 소스가 겹치는 날짜의 종가 차이 — 이어 붙이기 전 정합성 확인."""
    both = toss.merge(kis, on="date", suffixes=("_toss", "_kis"))
    if both.empty:
        return "겹치는 날짜 없음"
    diff = (both["close_toss"] - both["close_kis"]).abs()
    return f"겹침 {len(both)}일, 종가 최대 차이 {diff.max():.2f}p, 평균 {diff.mean():.3f}p"


def run(markets: List[str], full: bool, index_dir: Path = _INDEX_DIR,
        toss_factory: Optional[Callable[[], TossIndexClient]] = None,
        kis_factory: Optional[Callable[[], KisIndexClient]] = None) -> int:
    load_dotenv(_PROJECT_ROOT / ".env")
    toss_factory = toss_factory or (lambda: TossIndexClient(
        os.environ.get("TOSS_INVEST_CLIENT_ID", ""), os.environ.get("TOSS_INVEST_CLIENT_SECRET", "")))
    kis_factory = kis_factory or (lambda: KisIndexClient(
        os.environ.get("KIS_APP_KEY", "").strip(), os.environ.get("KIS_APP_SECRET", "").strip()))
    toss = toss_factory()
    kis: Optional[KisIndexClient] = None
    failures = 0

    for market in markets:
        existing = read_index(market, index_dir)
        do_full = full or existing is None
        label = "전체 백필" if do_full else "갱신"
        print(f"[INDEX] {market} {label} 시작", flush=True)
        try:
            toss_df = toss_rows_to_frame(toss.fetch_candles(market, max_pages=None if do_full else 1))
        except Exception as exc:  # 네트워크·인증 — 기존 파일은 건드리지 않는다
            print(f"[INDEX] {market} 토스 수집 실패: {exc}", flush=True)
            failures += 1
            continue
        if toss_df.empty:
            print(f"[INDEX] {market} 토스 응답 비어 있음 — 건너뜀", flush=True)
            failures += 1
            continue

        if do_full:
            kis = kis or kis_factory()
            until = min(toss_df["date"].min(), _TOSS_FLOOR)
            kis_df = kis_rows_to_frame(kis.fetch_before(market, until))
            # 정합성 확인용으로 토스 하한 근처 한 창을 더 받아 겹침을 비교한다.
            overlap = kis_rows_to_frame(kis.fetch_window(
                _KIS_CODES[market], until.strftime("%Y%m%d"),
                (until + timedelta(days=_KIS_WINDOW_DAYS - 1)).strftime("%Y%m%d")))
            print(f"[INDEX] {market} 소스 이음새: {_seam_report(toss_df, overlap)}", flush=True)
            merged = merge_sources(toss_df, kis_df)
        else:
            merged = upsert(existing, toss_df)

        path = write_index(market, merged, index_dir)
        print(f"[INDEX] {market} 저장 {len(merged)}행 "
              f"{merged['date'].min().date()}~{merged['date'].max().date()} "
              f"(toss {int((merged['source'] == 'toss').sum())}, kis {int((merged['source'] == 'kis').sum())}) → {path}",
              flush=True)
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="시장지수 일봉 백필·갱신 (토스 정본 + KIS 보충)")
    parser.add_argument("--full", action="store_true", help="전 구간 재수집(토스 전체 + KIS 2014-06 이전)")
    parser.add_argument("--markets", default=",".join(INDEX_MARKETS), help="쉼표 구분 (기본 KOSPI,KOSDAQ)")
    args = parser.parse_args(argv)
    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    unknown = [m for m in markets if m not in INDEX_MARKETS]
    if unknown:
        parser.error(f"지원하지 않는 시장: {unknown} (지원: {INDEX_MARKETS})")
    return run(markets, full=args.full)


if __name__ == "__main__":
    sys.exit(main())
