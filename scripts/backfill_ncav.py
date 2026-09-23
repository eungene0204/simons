"""Backfill DART NCAV 원재료(유동자산·부채총계) into the fundamentals cache + parquet (엔진 v16.27).

배경(2026-09-23): 그레이엄 NCAV(순유동자산 = 유동자산 − 부채총계) 전략은 국내 퀀트의 단골이지만
재무 캐시(data/fundamentals)에도 parquet에도 유동자산·부채총계가 없었다. 이미 부르던
`fnlttSinglAcntAll.json` 재무상태표(BS)에 두 계정이 있어 **재조회**로 채운다(ROIC 백필과 같은 구조).

수집 항목(원 단위, engine.fundamental_fetcher.parse_dart_ncav_inputs): current_assets · total_liabilities
파생(_compute_derived_annual_metrics): ncav = 유동자산 − 부채총계 → parquet 컬럼 `ncav`(원).
런타임(data_resolver.recompute_ncav_ratio): ncav_ratio = 시가총액 ÷ NCAV × 100(%).

조회 범위는 **DART 응답이 있던 연도**(total_equity 또는 operating_cash_flow 보유)로 좁힌다.
재개 가능(progress 파일), 쿼터 분할(--max-calls, 020이면 종료코드 3).

**정본=프로덕션**(CLAUDE.md, 2026-09-21): 이 스크립트는 프로덕션에서 돌리고 로컬은 pull 한다.
parquet 쓰기는 **빈 칸만 채우는 병합**(merge_fundamentals)이다.

Usage:
  python scripts/backfill_ncav.py --dry-run --limit 5
  python scripts/backfill_ncav.py --max-calls 19000
  python scripts/backfill_ncav.py --symbol 005930
  python scripts/backfill_ncav.py --remerge-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import polars as pl  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _REPO_ROOT / "data" / "fundamentals"
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"
_PROGRESS_PATH = _REPO_ROOT / "data" / "ncav-backfill.progress.json"
sys.path.insert(0, str(_REPO_ROOT / "backend"))

import engine.fundamental_fetcher as ff  # noqa: E402
from engine.fundamental_backfill import merge_fundamentals  # noqa: E402


class QuotaExhausted(Exception):
    """DART 일일 허용량(status 020) 소진."""


def load_progress() -> set[str]:
    if not _PROGRESS_PATH.exists():
        return set()
    try:
        return set(json.loads(_PROGRESS_PATH.read_text(encoding="utf-8")).get("done", []))
    except Exception:
        return set()


def save_progress(done: set[str]) -> None:
    _PROGRESS_PATH.write_text(json.dumps({"done": sorted(done)}, ensure_ascii=False), encoding="utf-8")


def pending_years(records: list[dict]) -> list[int]:
    """DART 응답이 있던 연도(자본총계 또는 OCF 보유) 중 NCAV 원재료가 아직 없는 연도."""
    years = []
    for record in records:
        if record.get("total_equity") is None and record.get("operating_cash_flow") is None:
            continue
        if record.get("current_assets") is not None and record.get("total_liabilities") is not None:
            continue
        year_end = str(record.get("year_end", ""))[:4]
        if year_end.isdigit():
            years.append(int(year_end))
    return sorted(set(years))


def find_target_symbols() -> list[str]:
    symbols = []
    for path in sorted(_CACHE_DIR.glob("[0-9]*.json")):
        if path.name.endswith(".nodata.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if pending_years(payload.get("fundamentals") or []):
            symbols.append(path.stem)
    return symbols


def fetch_year_inputs(corp_code: str, year: int) -> tuple[dict, int]:
    """한 연도의 NCAV 원재료. 연결(CFS) 먼저, 없으면 별도(OFS) — OCF·ROIC 파서와 같은 순서."""
    calls = 0
    for fs_div in ("CFS", "OFS"):
        payload = ff._fetch_dart_json(
            "fnlttSinglAcntAll.json",
            {"corp_code": corp_code, "bsns_year": str(year),
             "reprt_code": ff._DART_ANNUAL_REPORT_CODE, "fs_div": fs_div},
        )
        calls += 1
        if payload.get("status") == "020":
            raise QuotaExhausted()
        if payload.get("status") != "000":
            continue
        values = ff.parse_dart_ncav_inputs(payload.get("list", []))
        if values:
            return values, calls
    return {}, calls


def _merge_parquet(symbol: str, records: list[dict], dry_run: bool) -> list[str]:
    parquet_path = _OHLCV_DIR / f"{symbol}.parquet"
    if not parquet_path.exists():
        return []
    pdf = pl.read_parquet(parquet_path).to_pandas()
    rebuilt = merge_fundamentals(pdf, records)     # 빈 칸만 채운다(기존 값 우선)
    if rebuilt.equals(pdf):
        return []
    if not dry_run:
        tmp = parquet_path.with_suffix(".parquet.tmp")
        pl.from_pandas(rebuilt).write_parquet(tmp)
        os.replace(tmp, parquet_path)            # 원자적 교체
    return [str(parquet_path.relative_to(_REPO_ROOT))]


def backfill_symbol(symbol: str, *, dry_run: bool) -> tuple[str, list[str], int]:
    cache_path = _CACHE_DIR / f"{symbol}.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    records = payload.get("fundamentals") or []
    years = pending_years(records)
    if not years:
        return "nothing_pending", [], 0
    corp_code = ff._get_dart_corp_code(symbol)
    if not corp_code:
        return "no_corp_code", [], 0
    by_year = {str(r.get("year_end", ""))[:4]: r for r in records}
    filled, calls = 0, 0
    for year in years:
        values, used = fetch_year_inputs(corp_code, year)
        calls += used
        if not values:
            continue
        by_year[str(year)].update(values)
        filled += 1
    if not filled:
        return "no_inputs", [], calls
    records = ff._compute_derived_annual_metrics(records)
    payload["fundamentals"] = records
    changed = []
    if not dry_run:
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    changed.append(str(cache_path.relative_to(_REPO_ROOT)))
    changed.extend(_merge_parquet(symbol, records, dry_run))
    return f"filled_{filled}y", changed, calls


def remerge_symbol(symbol: str, *, dry_run: bool) -> tuple[str, list[str]]:
    cache_path = _CACHE_DIR / f"{symbol}.json"
    if not cache_path.exists():
        return "no_cache", []
    records = json.loads(cache_path.read_text(encoding="utf-8")).get("fundamentals") or []
    if not any("ncav" in r for r in records):
        return "nothing_to_merge", []
    changed = _merge_parquet(symbol, records, dry_run)
    return ("remerged" if changed else "unchanged"), changed


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-calls", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--remerge-only", action="store_true", help="DART 호출 없이 캐시 → parquet 재병합")
    args = ap.parse_args()

    if args.remerge_only:
        symbols = [args.symbol] if args.symbol else sorted(p.stem for p in _CACHE_DIR.glob("[0-9]*.json")
                                                             if not p.name.endswith(".nodata.json"))
        tally = {}
        for symbol in symbols:
            status, _ = remerge_symbol(symbol, dry_run=args.dry_run)
            tally[status] = tally.get(status, 0) + 1
        print(f"[ncav-backfill] remerge: {dict(sorted(tally.items()))}")
        return

    if not os.getenv("DART_API_KEY", "").strip():
        print("[ncav-backfill] DART_API_KEY 미설정 — 중단")
        sys.exit(2)

    done = load_progress()
    symbols = [args.symbol] if args.symbol else [s for s in find_target_symbols() if s not in done]
    if args.limit:
        symbols = symbols[: args.limit]
    total = len(symbols)
    print(f"[ncav-backfill] 대상 {total:,}종목 (완료 기록 {len(done):,} 제외) "
          f"max_calls={args.max_calls or '무제한'} dry_run={args.dry_run}", flush=True)

    tally, calls_used, aborted = {}, 0, None
    for i, symbol in enumerate(symbols, 1):
        try:
            status, _changed, calls = backfill_symbol(symbol, dry_run=args.dry_run)
        except QuotaExhausted:
            aborted = "quota"
            print(f"  [{i}/{total}] {symbol}: DART 일일 쿼터 소진(020) — 중단(재실행으로 재개)", flush=True)
            break
        except Exception as error:  # noqa: BLE001
            status, calls = "error", 0
            print(f"  [{symbol}] error: {error}", flush=True)
        calls_used += calls
        tally[status] = tally.get(status, 0) + 1
        if not args.dry_run and status != "error":
            done.add(symbol)
        if i <= 5 or i % 100 == 0:
            print(f"  [{i}/{total}] {symbol}: {status} (누적 호출 {calls_used:,})", flush=True)
        if not args.dry_run and i % 25 == 0:
            save_progress(done)
        if args.max_calls and calls_used >= args.max_calls:
            aborted = "budget"
            print(f"  [{i}/{total}] 호출 예산 {args.max_calls:,} 도달 — 중단(재실행으로 재개)", flush=True)
            break
        if args.sleep:
            time.sleep(args.sleep)
    if not args.dry_run:
        save_progress(done)
    print(f"[ncav-backfill] {'aborted(' + aborted + ')' if aborted else 'done'}: "
          f"{dict(sorted(tally.items()))} / DART 호출 {calls_used:,}", flush=True)
    if aborted == "quota":
        sys.exit(3)


if __name__ == "__main__":
    main()
