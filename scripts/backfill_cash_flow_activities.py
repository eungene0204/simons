"""Backfill 투자·재무활동 현금흐름 into the fundamentals cache + parquet.

배경(2026-08-05): DART 현금흐름표 3분류 중 영업활동(OCF)만 수집하고 있었다. 투자·재무
활동 총계는 같은 `fnlttSinglAcntAll.json` 응답에 들어 있었지만 파싱하지 않고 버려졌다
(근본 수정: engine/fundamental_fetcher._parse_dart_activity_cash_flow). 캐시에는 파싱
결과만 남기고 raw 응답을 보관하지 않으므로 과거 구간은 재조회 없이 채울 수 없다.

**조회 범위를 OCF 보유 연도로 좁힌다.** 세 분류는 한 응답에서 나오므로, OCF가 없는
연도는 그 응답에 CF 총계 자체가 없었다는 뜻이고 재조회해도 투자·재무가 나올 리 없다.
전 종목 전 연도(≈5.5만 호출) 대신 22,694 호출로 줄어든다.

처리 절차 (종목당):
  1. 캐시 레코드 중 operating_cash_flow가 있고 investing_cash_flow가 없는 연도를 추림
  2. 연도별 fnlttSinglAcntAll.json 조회(CFS → 실패 시 OFS) 후 투자·재무 총계만 파싱
  3. 해당 year_end 레코드에 두 키만 추가(기존 필드·available_from 불변) 후 캐시 재기록
  4. parquet은 merge_fundamentals(기존 값 우선, 결측만 채움)로 두 컬럼만 신규 추가

재개 가능: 완료 종목을 progress 파일에 기록해 재실행 시 건너뛴다. "투자·재무가 실제로
없는 종목"과 "아직 조회 안 한 종목"이 캐시만으로는 구분되지 않기 때문에 필요하다
(available_from 수리 스크립트가 min 클램프로 멱등했던 것과 다른 점).

쿼터 분할: --max-calls로 1회 실행의 DART 호출 예산을 정한다. status 020을 만나면
진행 상황을 저장하고 종료코드 3으로 중단 — 리셋 후 재실행하면 남은 종목부터 재개된다.

Usage:
  python scripts/backfill_cash_flow_activities.py --dry-run --limit 5
  python scripts/backfill_cash_flow_activities.py --max-calls 15000 --manifest /tmp/m.txt
  python scripts/backfill_cash_flow_activities.py --symbol 005930
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# polars/torch deadlock + libomp guards (must precede polars import — see memory).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import polars as pl

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _REPO_ROOT / "data" / "fundamentals"
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"
_PROGRESS_PATH = _REPO_ROOT / "data" / "cashflow-activity-backfill.progress.json"
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
    _PROGRESS_PATH.write_text(
        json.dumps({"done": sorted(done)}, ensure_ascii=False), encoding="utf-8"
    )


def pending_years(records: list[dict]) -> list[int]:
    """OCF는 있는데 투자활동이 없는 연도 (= 재조회 대상)."""
    years = []
    for record in records:
        if record.get("operating_cash_flow") is None:
            continue
        if record.get("investing_cash_flow") is not None:
            continue
        year_end = str(record.get("year_end", ""))[:4]
        if year_end.isdigit():
            years.append(int(year_end))
    return sorted(set(years))


def find_target_symbols() -> list[str]:
    """재조회할 연도가 하나라도 있는 종목."""
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


def _fetch_activity_totals(corp_code: str, year: int) -> tuple[dict, int]:
    """한 연도의 투자·재무활동 총계. Returns (parsed_keys, dart_calls_used)."""
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
        rows = payload.get("list", [])
        found = {}
        for key, account_id, names in (
            ("investing_cash_flow",
             ff._DART_INVESTING_CASH_FLOW_ACCOUNT_ID, ff._DART_INVESTING_CASH_FLOW_NAMES),
            ("financing_cash_flow",
             ff._DART_FINANCING_CASH_FLOW_ACCOUNT_ID, ff._DART_FINANCING_CASH_FLOW_NAMES),
        ):
            parsed = ff._parse_dart_activity_cash_flow(rows, account_id, names)
            if parsed is not None:
                found[key] = parsed["amount"]
        if found:
            return found, calls
    return {}, calls


def remerge_symbol(symbol: str, *, dry_run: bool) -> tuple[str, list[str]]:
    """DART 호출 없이 캐시의 현금흐름 3분류를 parquet에 다시 반영한다.

    프로덕션 미러 pull로 parquet이 되돌아온 뒤(정본=프로덕션이라 pull이 이긴다) 새 컬럼만
    복원하는 용도. 캐시(data/fundamentals)는 미러 대상이 아니라 값이 보존돼 있다.
    """
    cache_path = _CACHE_DIR / f"{symbol}.json"
    if not cache_path.exists():
        return "no_cache", []
    records = json.loads(cache_path.read_text(encoding="utf-8")).get("fundamentals") or []
    if not any(r.get("investing_cash_flow") is not None
               or r.get("financing_cash_flow") is not None for r in records):
        return "nothing_to_merge", []

    parquet_path = _OHLCV_DIR / f"{symbol}.parquet"
    if not parquet_path.exists():
        return "no_parquet", []
    if not dry_run:
        pdf = pl.read_parquet(parquet_path).to_pandas()
        merged = merge_fundamentals(pdf, records)
        pl.from_pandas(merged).write_parquet(parquet_path)
    return "remerged", [str(parquet_path.relative_to(_REPO_ROOT))]


def backfill_symbol(symbol: str, *, dry_run: bool) -> tuple[str, list[str], int]:
    """Returns (status, changed_repo_relative_paths, dart_calls_used)."""
    cache_path = _CACHE_DIR / f"{symbol}.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    records = payload.get("fundamentals") or []

    years = pending_years(records)
    if not years:
        return "nothing_pending", [], 0

    corp_code = ff._get_dart_corp_code(symbol)
    if not corp_code:
        return "no_corp_code", [], 0

    # 연도 키는 OCF 보유 레코드로만 만든다 — 같은 해에 결산월이 다른 레코드가 함께 있으면
    # (예: KIS 유래 2025-09-30 + DART 유래 2025-12-31) 연도만으로는 키가 충돌해 OCF가 없는
    # 쪽에 값이 실릴 수 있다. pending_years가 고른 연도와 갱신 대상을 같은 술어로 맞춘다.
    by_year = {
        str(r.get("year_end", ""))[:4]: r
        for r in records
        if r.get("operating_cash_flow") is not None
    }
    filled, calls = 0, 0
    for year in years:
        found, used = _fetch_activity_totals(corp_code, year)
        calls += used
        if not found:
            continue
        by_year[str(year)].update(found)
        filled += 1

    if not filled:
        return "no_activity_data", [], calls

    changed_paths = []
    if not dry_run:
        cache_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    changed_paths.append(str(cache_path.relative_to(_REPO_ROOT)))

    parquet_path = _OHLCV_DIR / f"{symbol}.parquet"
    if parquet_path.exists():
        if not dry_run:
            pdf = pl.read_parquet(parquet_path).to_pandas()
            merged = merge_fundamentals(pdf, records)
            pl.from_pandas(merged).write_parquet(parquet_path)
        changed_paths.append(str(parquet_path.relative_to(_REPO_ROOT)))

    return f"filled_{filled}y", changed_paths, calls


def _run_remerge(args) -> None:
    """--remerge-only: 캐시에 3분류가 있는 모든 종목의 parquet을 재병합한다."""
    symbols = [args.symbol] if args.symbol else sorted(
        path.stem for path in _CACHE_DIR.glob("[0-9]*.json")
        if not path.name.endswith(".nodata.json")
    )
    if args.limit:
        symbols = symbols[: args.limit]

    tally: dict[str, int] = {}
    manifest_paths: list[str] = []
    for i, symbol in enumerate(symbols, 1):
        try:
            status, changed_paths = remerge_symbol(symbol, dry_run=args.dry_run)
        except Exception as error:  # noqa: BLE001
            status, changed_paths = "error", []
            print(f"  [{symbol}] error: {error}")
        tally[status] = tally.get(status, 0) + 1
        manifest_paths.extend(changed_paths)
        if i % 500 == 0:
            print(f"  [{i}/{len(symbols)}] {symbol}: {status}")

    _flush_manifest(args.manifest, manifest_paths)
    print(f"[cf-backfill] remerge done: {dict(sorted(tally.items()))}")


def _flush_manifest(manifest: str | None, paths: list[str]) -> None:
    if not manifest or not paths:
        return
    with open(manifest, "a", encoding="utf-8") as fh:
        for path in paths:
            fh.write(path + "\n")


def main() -> None:
    from dotenv import load_dotenv  # 모듈 레벨 금지 — .env 오염 함정(메모리 참고)

    load_dotenv(_REPO_ROOT / ".env")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", help="single 6-digit ticker")
    ap.add_argument("--limit", type=int, help="process at most N symbols this run")
    ap.add_argument("--max-calls", type=int, default=0,
                    help="stop after roughly N DART calls (쿼터 분할용, 0=무제한)")
    ap.add_argument("--dry-run", action="store_true", help="fetch but do not write")
    ap.add_argument("--sleep", type=float, default=0.05, help="seconds between symbols")
    ap.add_argument("--manifest", help="append changed repo-relative paths to this file")
    ap.add_argument("--remerge-only", action="store_true",
                    help="DART 호출 없이 캐시→parquet 재병합만 (미러 pull 이후 복원용)")
    args = ap.parse_args()

    if args.remerge_only:
        _run_remerge(args)
        return

    if not os.getenv("DART_API_KEY", "").strip():
        print("[cf-backfill] DART_API_KEY 미설정 — 중단")
        sys.exit(2)

    done = load_progress()
    if args.symbol:
        symbols = [args.symbol]
    else:
        symbols = [s for s in find_target_symbols() if s not in done]
    if args.limit:
        symbols = symbols[: args.limit]

    total = len(symbols)
    print(f"[cf-backfill] 대상 {total:,}종목 (완료 기록 {len(done):,}종목 제외) "
          f"max_calls={args.max_calls or '무제한'} dry_run={args.dry_run}")

    tally: dict[str, int] = {}
    manifest_paths: list[str] = []
    calls_used = 0
    aborted = None

    for i, symbol in enumerate(symbols, 1):
        try:
            status, changed_paths, calls = backfill_symbol(symbol, dry_run=args.dry_run)
        except QuotaExhausted:
            aborted = "quota"
            print(f"  [{i}/{total}] {symbol}: DART 일일 쿼터 소진(020) — 중단. "
                  f"리셋 후 재실행하면 남은 종목부터 재개됩니다.")
            break
        except Exception as error:  # noqa: BLE001 — 한 종목 실패가 배치를 죽이면 안 된다
            status, changed_paths, calls = "error", [], 0
            print(f"  [{symbol}] error: {error}")

        calls_used += calls
        tally[status] = tally.get(status, 0) + 1
        manifest_paths.extend(changed_paths)
        if not args.dry_run and status not in {"error"}:
            done.add(symbol)

        if i <= 5 or i % 100 == 0:
            print(f"  [{i}/{total}] {symbol}: {status} (누적 호출 {calls_used:,})")

        if args.max_calls and calls_used >= args.max_calls:
            aborted = "budget"
            print(f"  [{i}/{total}] 호출 예산 {args.max_calls:,} 도달 — 중단(재실행으로 재개).")
            break
        if args.sleep:
            time.sleep(args.sleep)

    if not args.dry_run:
        save_progress(done)
    _flush_manifest(args.manifest, manifest_paths)
    print(f"[cf-backfill] {'aborted(' + aborted + ')' if aborted else 'done'}: "
          f"{dict(sorted(tally.items()))} / DART 호출 {calls_used:,}")
    if aborted == "quota":
        sys.exit(3)


if __name__ == "__main__":
    main()
