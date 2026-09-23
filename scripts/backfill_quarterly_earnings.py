"""Backfill 분기 EPS·실적 발표일 (DART) — SUE·발표일 초과수익률(PEAD)의 원재료.

배경(2026-09-20): 재무 캐시는 **연간**뿐이라 SUE(직전 8개 분기 EPS 서프라이즈의 표준편차
정규화)도, 발표일 전후 초과수익률도 계산할 재료가 없었다. `engine.quarterly_earnings`가
DART 분기보고서에서 3개월 EPS와 공시 접수일(=발표일)을 받아 종목별 JSON으로 적재한다.

**시가총액 큰 순으로 받는다** — PEAD 유니버스가 시총 상위 구간이라 위에서부터 채우면 전량
수집(약 12일)을 기다리지 않고도 상위 구간 검증을 시작할 수 있다. 시총은 ohlcv parquet의
마지막 행을 읽는다(없으면 목록 끝으로).

호출 예산: 종목당 연 4회(분기 3 + 연간 1), 기준(연결/별도)을 고르는 첫 연도만 최대 8회.
2016~올해 = 종목당 약 44회이므로 전 종목은 약 25만 회 = DART 일 한도(2만) 기준 12~13일이다.
`--max-calls`로 1회 실행 예산을 정하고, 한도 소진(status 020)이면 진행 상황을 저장한 뒤
종료코드 3으로 멈춘다 — 다음 날 재실행하면 남은 종목부터 재개한다.

Usage:
  python scripts/backfill_quarterly_earnings.py --dry-run --limit 3
  python scripts/backfill_quarterly_earnings.py --symbol 005930
  python scripts/backfill_quarterly_earnings.py --max-calls 19000
  python scripts/backfill_quarterly_earnings.py --report
  python scripts/backfill_quarterly_earnings.py --repair-dates   # 이미 받은 종목의 발표일을 원공시일로 교정

`--repair-dates`(2026-09-21): 09-21 이전 수집분은 발표일이 **정정공시 접수일**로 오염돼 있다
(engine.quarterly_earnings 모듈 docstring ③). EPS는 다시 받지 않고 공시검색 1회(종목당)로
원공시 접수일만 받아 min 클램프한다 — 재실행해도 결과 불변, 한도 소진 시 종료코드 3.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# polars/torch deadlock + libomp guards (must precede polars import — see memory).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import polars as pl  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"
_STOCK_MASTER = _REPO_ROOT / "data" / "korea-stocks.json"
_PROGRESS_PATH = _REPO_ROOT / "data" / "quarterly-earnings-backfill.progress.json"
_ORDER_CACHE = _REPO_ROOT / "data" / "quarterly-earnings-backfill.order.json"

load_dotenv(_REPO_ROOT / ".env")
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from engine.fundamental_fetcher import DartQuotaExhausted  # noqa: E402
from engine import quarterly_earnings as qe  # noqa: E402


def load_progress() -> dict:
    if not _PROGRESS_PATH.exists():
        return {"done": [], "empty": []}
    try:
        payload = json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"done": [], "empty": []}
    return {"done": payload.get("done", []), "empty": payload.get("empty", [])}


def save_progress(done: set[str], empty: set[str]) -> None:
    _PROGRESS_PATH.write_text(
        json.dumps({"done": sorted(done), "empty": sorted(empty)}, ensure_ascii=False),
        encoding="utf-8",
    )


def _latest_market_cap(symbol: str) -> float:
    """parquet 마지막 행의 시가총액. 없으면 0(목록 끝으로 밀린다)."""
    path = _OHLCV_DIR / f"{symbol}.parquet"
    if not path.exists():
        return 0.0
    try:
        frame = pl.read_parquet(path, columns=["market_cap"])
    except Exception:
        return 0.0
    series = frame["market_cap"].drop_nulls()
    return float(series[-1]) if len(series) else 0.0


def symbols_by_market_cap(refresh: bool) -> list[str]:
    """시총 큰 순 종목 목록. parquet 5천여 개를 매번 읽지 않도록 순서를 캐시한다."""
    if not refresh and _ORDER_CACHE.exists():
        try:
            cached = json.loads(_ORDER_CACHE.read_text(encoding="utf-8")).get("symbols")
            if isinstance(cached, list) and cached:
                return cached
        except (OSError, ValueError):
            pass

    master = json.loads(_STOCK_MASTER.read_text(encoding="utf-8"))
    symbols = [row["symbol"] for row in master if row.get("symbol")]
    ordered = sorted(symbols, key=_latest_market_cap, reverse=True)
    _ORDER_CACHE.write_text(
        json.dumps({"symbols": ordered}, ensure_ascii=False), encoding="utf-8"
    )
    return ordered


def backfill_symbol(symbol: str, *, start_year: int, dry_run: bool) -> tuple[str, int]:
    """Returns (status, dart_calls_used)."""
    qe.reset_dart_calls()
    records = qe.fetch_quarterly_earnings(symbol, start_year=start_year)
    calls = qe.dart_calls_used()
    if records is None:
        return "no_data", calls
    if not dry_run:
        qe.save_quarterly_earnings(symbol, records)
    return f"saved_{len(records)}q", calls


def repair_dates(*, dry_run: bool) -> int:
    """수집된 전 종목의 발표일을 원공시 접수일로 클램프한다. 반환값은 종료코드."""
    from engine.fundamental_fetcher import _get_dart_corp_code

    qe.reset_dart_calls()
    symbols = changed_symbols = changed_records = 0
    for path in sorted((_REPO_ROOT / "data" / "quarterly-earnings").glob("*.json")):
        symbol = path.stem
        records = qe.load_quarterly_earnings(symbol)
        corp_code = _get_dart_corp_code(symbol) if records else None
        if not corp_code:
            continue
        try:
            originals = qe.fetch_original_filing_dates(corp_code)
        except DartQuotaExhausted:
            print(f"[한도] DART 일일 허용량 소진 — {symbols}종목 처리 후 중단")
            return 3
        symbols += 1
        changed = qe.clamp_to_original_filing(records, originals)
        if changed:
            changed_symbols += 1
            changed_records += changed
            if not dry_run:
                qe.save_quarterly_earnings(symbol, records)
            print(f"{symbol} 발표일 교정 {changed}건")
    print(f"완료: {symbols}종목 조회, {changed_symbols}종목·{changed_records}건 교정 "
          f"(DART {qe.dart_calls_used()}회{', dry-run' if dry_run else ''})")
    return 0


def report() -> None:
    cached = sorted((_REPO_ROOT / "data" / "quarterly-earnings").glob("*.json"))
    quarters = 0
    with_eight = 0
    for path in cached:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        count = len(payload.get("quarters") or [])
        quarters += count
        if count >= 8:
            with_eight += 1
    progress = load_progress()
    print(f"수집 종목      : {len(cached)}")
    print(f"분기 레코드    : {quarters}")
    print(f"8개 분기 이상  : {with_eight}  (SUE 산출 가능 종목)")
    print(f"진행 기록      : done={len(progress['done'])} empty={len(progress['empty'])}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", help="단일 종목만 수집")
    parser.add_argument("--limit", type=int, help="이번 실행에서 처리할 종목 수 상한")
    parser.add_argument("--max-calls", type=int, default=19000,
                        help="이번 실행의 DART 호출 예산(기본 19000 — 일 한도 20000 여유분)")
    parser.add_argument("--start-year", type=int, default=qe.QUARTERLY_YEAR_FLOOR)
    parser.add_argument("--refresh-order", action="store_true",
                        help="시총 순서 캐시를 다시 만든다")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true", help="수집 없이 현황만")
    parser.add_argument("--repair-dates", action="store_true",
                        help="수집된 종목의 발표일을 원공시 접수일로 교정(EPS 재수집 없음)")
    parser.add_argument("--refetch-income", action="store_true",
                        help="분기 손익 3항목(v16.27)이 없는 기수집 종목을 먼저 다시 받는다(시총 순)")
    args = parser.parse_args()

    if args.repair_dates:
        return repair_dates(dry_run=args.dry_run)

    if args.report:
        report()
        return 0

    progress = load_progress()
    done, empty = set(progress["done"]), set(progress["empty"])

    if args.symbol:
        targets = [args.symbol]
    else:
        ordered = symbols_by_market_cap(args.refresh_order)
        targets = [s for s in ordered if s not in done and s not in empty]
        if args.refetch_income:
            # 09-23 이전 EPS 전용 수집분은 매출·영업이익·순이익이 없다 — 시총 큰 순으로 먼저 다시 받는다.
            stale = [s for s in ordered if s in done and not qe.has_income_items(qe.load_quarterly_earnings(s))]
            targets = stale + targets
        if args.limit:
            targets = targets[:args.limit]

    used = 0
    processed = 0
    try:
        for symbol in targets:
            if used >= args.max_calls:
                print(f"[예산] DART 호출 {used}회 — 이번 실행 종료")
                break
            status, calls = backfill_symbol(
                symbol, start_year=args.start_year, dry_run=args.dry_run
            )
            used += calls
            processed += 1
            if status == "no_data":
                empty.add(symbol)
            else:
                done.add(symbol)
            print(f"{symbol} {status} (calls={calls}, 누적={used})")
    except DartQuotaExhausted:
        if not args.dry_run:
            save_progress(done, empty)
        print(f"[한도] DART 일일 허용량 소진 — {processed}종목 처리 후 중단 (누적 {used}회)")
        return 3

    if not args.dry_run:
        save_progress(done, empty)
    print(f"완료: {processed}종목, DART {used}회 (done={len(done)}, empty={len(empty)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
