"""Repair contaminated ``available_from`` dates in the fundamentals cache + parquet.

배경(2026-08-04): DART fnlttSinglAcntAll의 rcept_no는 정정공시가 있으면 **정정본**을
가리킨다. 그래서 캐시 레코드의 available_from이 원공시일(예: 2021-03)이 아니라 정정
접수일(예: 2023-03)로 기록됐고, PIT 병합이 해당 구간에서 수년 낡은 연도 값을 참조했다
(실사고: 유성티엔에스 2022-02-03 백테스트가 FY2017 재무로 판정). 전수 스캔 결과
결산일+120일 초과 레코드 3,390개 / 1,628종목.

수리 절차 (종목당):
  1. DART 공시검색(list.json)에서 연도별 **원공시** 사업보고서 접수일을 조회
     (engine.fundamental_fetcher._fetch_dart_original_filing_dates — 근본 수정과 공유)
  2. 캐시 레코드 available_from = min(기존, 원공시일) 클램프 후 캐시 재기록
  3. data/ohlcv parquet의 연간 재무 컬럼을 교정 캐시 기준으로 재구축
     (engine.fundamental_backfill.rebuild_fundamental_columns — 캐시 우선, 캐시 밖
     과거 이력만 보존, PER/PBR/PSR 정합 재계산)

Idempotent/재개 가능: min 클램프라 재실행해도 결과 불변. DART 일일 쿼터(status 020)를
만나면 종료코드 3으로 중단 — 이미 처리한 종목은 저장돼 있으므로 쿼터 리셋 후 재실행하면
남은 종목만 실질 작업이 된다. 변경된 파일 목록은 --manifest 경로에 누적 기록되어
프로덕션 스코프 rsync push(--files-from)에 쓴다.

Usage:
  python scripts/repair_fundamental_available_from.py --dry-run --limit 5
  python scripts/repair_fundamental_available_from.py --symbol 024800
  python scripts/repair_fundamental_available_from.py --manifest /path/to/manifest.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
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
sys.path.insert(0, str(_REPO_ROOT / "backend"))

import engine.fundamental_fetcher as ff  # noqa: E402
from engine.fundamental_backfill import rebuild_fundamental_columns  # noqa: E402

# 법정 제출기한은 결산 후 90일 — 여유를 두고 이보다 늦으면 정정일 오염 의심으로 조회.
_DEFAULT_GRACE_DAYS = 120


def _record_dates(record: dict) -> tuple[dt.date, dt.date] | None:
    """(year_end, available_from) as dates; None if either is absent/invalid."""
    try:
        year_end = dt.date.fromisoformat(str(record.get("year_end", ""))[:10])
        available = dt.date.fromisoformat(str(record.get("available_from", ""))[:10])
    except ValueError:
        return None
    if not record.get("available_from"):
        return None
    return year_end, available


def find_suspicious_symbols(grace_days: int) -> list[str]:
    """available_from이 결산일+grace_days를 넘는 레코드를 가진 종목 목록."""
    symbols = []
    for path in sorted(_CACHE_DIR.glob("[0-9]*.json")):
        if path.name.endswith(".nodata.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for record in payload.get("fundamentals") or []:
            parsed = _record_dates(record)
            if parsed and (parsed[1] - parsed[0]).days > grace_days:
                symbols.append(path.stem)
                break
    return symbols


def _quota_exhausted(corp_code: str) -> bool:
    """DART 일일 쿼터 소진(status 020) 여부를 직접 확인한다."""
    payload = ff._fetch_dart_json(
        "list.json",
        {"corp_code": corp_code, "bgn_de": "20260101", "end_de": "20260102",
         "pblntf_detail_ty": "A001", "page_no": "1", "page_count": "1"},
    )
    return payload.get("status") == "020"


def repair_symbol(symbol: str, *, dry_run: bool) -> tuple[str, list[str]]:
    """한 종목의 캐시 available_from 클램프 + parquet 재구축.

    Returns (status, changed_repo_relative_paths).
    """
    cache_path = _CACHE_DIR / f"{symbol}.json"
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    records = payload.get("fundamentals") or []

    corp_code = ff._get_dart_corp_code(symbol)
    if not corp_code:
        return "no_corp_code", []

    # 사업보고서 이름에서 연도별 결산월과 원공시일을 함께 읽는다 — 월을 12로 고정하던
    # 종전 방식은 비12월 결산 회사를 통째로 클램프에서 빠뜨렸다(2026-08-07 수정).
    original_dates = ff._fetch_dart_original_filing_dates(corp_code)
    if not original_dates:
        return "no_filing_dates", []

    changed = 0
    for record in records:
        parsed = _record_dates(record)
        if not parsed:
            continue
        original = original_dates.get(parsed[0].year)
        if original and original < str(record["available_from"])[:10]:
            record["available_from"] = original
            changed += 1
    if not changed:
        return "already_clean", []

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
            rebuilt = rebuild_fundamental_columns(pdf, records)
            pl.from_pandas(rebuilt).write_parquet(parquet_path)
        changed_paths.append(str(parquet_path.relative_to(_REPO_ROOT)))

    return f"repaired_{changed}rec", changed_paths


def main() -> None:
    from dotenv import load_dotenv  # 모듈 레벨 금지 — .env 오염 함정(메모리 참고)

    load_dotenv(_REPO_ROOT / ".env")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", help="single 6-digit ticker")
    ap.add_argument("--limit", type=int, help="process at most N symbols")
    ap.add_argument("--grace-days", type=int, default=_DEFAULT_GRACE_DAYS)
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--sleep", type=float, default=0.15, help="seconds between DART calls")
    ap.add_argument("--manifest", help="append changed repo-relative paths to this file")
    args = ap.parse_args()

    if not os.getenv("DART_API_KEY", "").strip():
        print("[repair] DART_API_KEY 미설정 — 중단")
        sys.exit(2)

    symbols = [args.symbol] if args.symbol else find_suspicious_symbols(args.grace_days)
    if args.limit:
        symbols = symbols[: args.limit]
    total = len(symbols)
    print(f"[repair] {total} symbol(s); grace={args.grace_days}d dry_run={args.dry_run}")

    tally: dict[str, int] = {}
    manifest_paths: list[str] = []
    consecutive_empty = 0
    for i, symbol in enumerate(symbols, 1):
        try:
            status, changed_paths = repair_symbol(symbol, dry_run=args.dry_run)
        except Exception as error:  # noqa: BLE001 — one bad symbol must not kill the batch
            status, changed_paths = "error", []
            print(f"  [{symbol}] error: {error}")
        tally[status] = tally.get(status, 0) + 1
        manifest_paths.extend(changed_paths)

        # 쿼터 소진 감지: 원공시 조회가 계속 비면 020인지 직접 확인 후 중단(재실행으로 재개).
        if status == "no_filing_dates":
            consecutive_empty += 1
            if consecutive_empty >= 3:
                corp_code = ff._get_dart_corp_code(symbol)
                if corp_code and _quota_exhausted(corp_code):
                    print(f"  [{i}/{total}] DART 일일 쿼터 소진(020) — 중단. "
                          f"쿼터 리셋 후 재실행하면 남은 종목부터 재개됩니다.")
                    _flush_manifest(args.manifest, manifest_paths)
                    print(f"[repair] aborted: {dict(sorted(tally.items()))}")
                    sys.exit(3)
                consecutive_empty = 0
        else:
            consecutive_empty = 0

        if status.startswith("repaired") and (i <= 10 or i % 50 == 0):
            print(f"  [{i}/{total}] {symbol}: {status}")
        if args.sleep:
            time.sleep(args.sleep)

    _flush_manifest(args.manifest, manifest_paths)
    print(f"[repair] done: {dict(sorted(tally.items()))}")


def _flush_manifest(manifest: str | None, paths: list[str]) -> None:
    if not manifest or not paths:
        return
    with open(manifest, "a", encoding="utf-8") as fh:
        for path in paths:
            fh.write(path + "\n")


if __name__ == "__main__":
    main()
