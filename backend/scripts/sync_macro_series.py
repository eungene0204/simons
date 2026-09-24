"""매크로 시계열 동기화(엔진 v16.31) — `data/macro/<series>.parquet`.

실행: python backend/scripts/sync_macro_series.py [--series vix,usdkrw] [--start 2005-01-01] [--data-dir data/ohlcv]

정본은 `engine/macro_data.ALL_SERIES`(조건 필터용 MACRO_SERIES + 결과 기준값용 REFERENCE_SERIES). 야후(yfinance)와 FRED(FinanceDataReader 'FRED:' 접두)에서 전체
이력을 받아 원자적으로 교체한다(한 시리즈 실패는 그 파일만 건너뛰고 나머지는 계속). scripts/sync_data.py의
야간 동기화가 시장지수 갱신 뒤에 이 스크립트를 부른다. parquet 정본은 프로덕션이며 로컬은
`scripts/mirror_data.py --macro`로 받는다(parquet 방향 규칙).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from engine.macro_data import ALL_SERIES, macro_dir_for  # noqa: E402

DEFAULT_START = "2005-01-01"


def _fetch_yfinance(code: str, start: str) -> pd.Series:
    import yfinance as yf

    df = yf.download(code, start=start, progress=False, auto_adjust=False)
    if df is None or len(df) == 0:
        raise RuntimeError(f"yfinance 응답 없음: {code}")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    s = pd.Series(close.astype(float).values, index=pd.DatetimeIndex(pd.to_datetime(df.index)).tz_localize(None))
    return s.dropna()


def _fetch_fred(code: str, start: str) -> pd.Series:
    import FinanceDataReader as fdr

    df = fdr.DataReader(f"FRED:{code}", start)
    if df is None or len(df) == 0:
        raise RuntimeError(f"FRED 응답 없음: {code}")
    s = pd.Series(df.iloc[:, 0].astype(float).values, index=pd.DatetimeIndex(pd.to_datetime(df.index)))
    return s.dropna()


def _fetch_worldbank(code: str, start: str) -> pd.Series:
    """세계은행 지표 API(키 불필요). code는 "<국가>/<지표>" (예: "KR/FP.CPI.TOTL"). 연간 관측."""
    import json
    import urllib.request

    country, indicator = code.split("/", 1)
    url = (f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
           f"?format=json&per_page=500&date={start[:4]}:2100")
    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else None
    if not rows:
        raise RuntimeError(f"세계은행 응답 없음: {code}")
    obs = {pd.Timestamp(f"{r['date']}-01-01"): float(r["value"])
           for r in rows if r.get("value") is not None}
    if not obs:
        raise RuntimeError(f"세계은행 값 없음: {code}")
    return pd.Series(obs).sort_index()


def fetch_series(series_id: str, start: str) -> pd.Series:
    spec = ALL_SERIES[series_id]
    if spec["source"] == "yfinance":
        return _fetch_yfinance(spec["code"], start)
    if spec["source"] == "fred":
        return _fetch_fred(spec["code"], start)
    if spec["source"] == "worldbank":
        return _fetch_worldbank(spec["code"], start)
    raise ValueError(f"알 수 없는 출처: {spec['source']}")


def write_series(series_id: str, values: pd.Series, macro_dir: Path) -> Path:
    macro_dir.mkdir(parents=True, exist_ok=True)
    spec = ALL_SERIES[series_id]
    dates = pd.DatetimeIndex(values.index)
    if spec["freq"] == "monthly":
        # 월간 시계열(월 평균)은 그 달이 끝나야 알 수 있다 — 관측일을 월말로 옮겨 다음 달부터 보이게 한다.
        dates = dates + pd.offsets.MonthEnd(0)
    elif spec["freq"] == "annual":
        # 연간 시계열도 같은 이유로 연말로 옮긴다(그 해가 끝나야 알 수 있는 값).
        dates = dates + pd.offsets.YearEnd(0)
    out = pd.DataFrame({
        "date": dates.astype("datetime64[us]"),
        "value": values.astype(float).values,
        "source": spec["source"],
    }).drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
    path = macro_dir / f"{series_id}.parquet"
    tmp = path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="매크로 시계열 동기화(data/macro)")
    parser.add_argument("--series", default="", help="쉼표 구분 시리즈 id(기본 전체)")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--data-dir", default=str(_REPO_ROOT / "data" / "ohlcv"),
                        help="OHLCV 데이터 루트 — 형제 디렉터리 data/macro에 쓴다")
    args = parser.parse_args(argv)
    targets = [s.strip() for s in args.series.split(",") if s.strip()] or list(ALL_SERIES)
    macro_dir = macro_dir_for(args.data_dir)
    ok = fail = 0
    for sid in targets:
        if sid not in ALL_SERIES:
            print(f"[macro] 알 수 없는 시리즈: {sid}")
            fail += 1
            continue
        try:
            s = fetch_series(sid, args.start)
            path = write_series(sid, s, macro_dir)
            print(f"[macro] {sid}: {len(s)}행 {s.index.min().date()}~{s.index.max().date()} → {path}")
            ok += 1
        except Exception as exc:  # noqa: BLE001 — 한 시리즈 실패가 나머지를 막지 않는다
            print(f"[macro] {sid} 실패: {exc}")
            fail += 1
    print(f"[macro] 완료: 성공 {ok} · 실패 {fail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
