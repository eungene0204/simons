"""KIS로 OHLCV 히스토리를 출범 초기(~1996)까지 백필한다.

기존 parquet은 ~2013부터다 — 무료 소스(FDR/pykrx)가 더는 깊은 과거를 주지 않기 때문.
KIS `inquire-daily-itemchartprice`는 ~1996년부터 수정주가 일봉을 제공한다(실측: 005930
1996-01-03~). 이 스크립트는 각 종목의 상장일(없으면 1996 floor)부터 전체 히스토리를
재수집해 parquet을 다시 쓴다 — 비어 있던 2013 이전 구간을 채운다.

resync_kis_adjusted.py의 KIS 페치/병합 로직을 그대로 재사용한다(차이는 start floor뿐).
KIS가 윈도우당 ≤100행을 주므로 종목마다 과거로 페이지네이션하며, 상장 이전은 빈 응답으로
자연히 멈춘다. 진행 파일로 재개 가능. 길다 — 수만 건의 KIS 호출(대략 8~14시간).

실행:
    cd backend && python scripts/backfill_ohlcv_history.py
    cd backend && python scripts/backfill_ohlcv_history.py --limit 5   # 소규모 검증
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resync_kis_adjusted as rk  # KIS 페치/병합 로직 재사용 (DRY)

# KIS가 제공하는 개별종목 일봉의 실측 하한 (005930 기준 1996-01-03; 1995 이전은 빈 응답).
_FLOOR = "19960101"
_PROGRESS_PATH = rk._OHLCV_DIR / ".kis_backfill_done.json"


def _load_done() -> set[str]:
    if _PROGRESS_PATH.exists():
        try:
            return set(json.loads(_PROGRESS_PATH.read_text()))
        except Exception:
            return set()
    return set()


def _save_done(done: set[str]) -> None:
    _PROGRESS_PATH.write_text(json.dumps(sorted(done)))


def _start_for(stock: dict) -> str:
    """상장일(있으면)과 KIS 하한 중 더 늦은 쪽. 상장 이전은 KIS가 빈 응답으로 멈춘다."""
    listing = (stock.get("listingDate") or "").replace("-", "")
    return max(_FLOOR, listing) if listing else _FLOOR


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N개만 처리(검증용)")
    args = parser.parse_args()

    master = json.loads(rk._MASTER_PATH.read_text(encoding="utf-8"))
    targets = [s for s in master["stocks"] if s.get("hasOhlcv")]
    if args.limit:
        targets = targets[: args.limit]
    done = _load_done()
    print(f"[backfill] {len(targets)} commons, {len(done)} already done", flush=True)

    ok = fail = skip = 0
    today = datetime.now().strftime("%Y%m%d")
    for i, s in enumerate(targets, 1):
        sym = s["symbol"]
        if sym in done:
            continue
        start = _start_for(s)
        end = (s.get("dataEnd") or today).replace("-", "")
        try:
            df = rk._fetch_full(sym, start, end)
            if df is None or len(df) < 5:
                skip += 1
            else:
                df = rk._merge_fundamentals(df, sym)
                out = pl.from_pandas(df).with_columns(pl.col("date").cast(pl.Datetime("us")))
                out.write_parquet(rk._OHLCV_DIR / f"{sym}.parquet")
                ok += 1
                print(f"[backfill] {sym} {str(df['date'].min())[:10]}~{str(df['date'].max())[:10]} rows={len(df)}", flush=True)
        except Exception as e:
            fail += 1
            print(f"[backfill] {sym} FAIL {repr(e)[:80]}", flush=True)
        done.add(sym)
        if i % 50 == 0:
            _save_done(done)
            print(f"[backfill] {i}/{len(targets)} ok={ok} skip={skip} fail={fail}", flush=True)
    _save_done(done)
    print(f"[backfill] DONE ok={ok} skip={skip} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
