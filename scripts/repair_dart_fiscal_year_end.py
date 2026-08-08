"""Relabel DART cache records from `{year}-12-31` to the company's real fiscal year end.

배경(2026-08-07): `_fetch_cash_flow_from_dart`가 DART 레코드의 year_end를 `{bsns_year}-12-31`로
**고정 기록**해 왔다. 12월 결산이 아닌 회사(효성오앤비 06, 금비 09, 삼일제약 03 등 실측 42종목)는
실제 결산일과 다른 날짜에 영업활동현금흐름·지배주주순이익·당기순이익·자본총계가 붙어, 같은
회계연도의 KIS 값과 **다른 레코드로 갈라진다**. 이 어긋남이 분기 행 판정까지 망가뜨렸다
(000220의 정상 연간 2026-03-31이 바로 앞 DART 2025-12-31 때문에 3개월 간격으로 보여 분기로 오인).

근본 수정은 engine.fundamental_fetcher.dart_year_end(bsns_year + 결산월). bsns_year는 **그
결산기가 끝나는 달력 연도**다(실측: 효성오앤비 bsns_year 2023 당기순이익 12.3억 = KIS 2023-06
레코드 12.4억, 금비 2024 = KIS 2024-09). 이 스크립트는 이미 캐시에 들어온 잘못된 라벨을 옮긴다.

수리 절차 (종목당):
  1. KIS 유래 레코드의 결산월 최빈값이 12가 아닌 종목만 대상으로 삼는다(문제가 보이는 집합)
  2. DART 기업개황(company.json)에서 acc_mt를 받아 결산월을 확정 — 종목당 1회, 파일 캐시
  3. `{year}-12-31` 레코드의 DART 유래 필드를 `{year}-{acc_mt}-말일` 레코드로 옮긴다
     (대상 레코드가 있으면 병합, 없으면 라벨만 바꾼다). available_from도 함께 옮긴다
  4. 파생 지표 재계산 후 캐시 재기록 + parquet 재구축(rebuild_fundamental_columns)

acc_mt가 12로 확인되면 라벨이 이미 맞는 것이므로 건드리지 않는다.

Usage:
  python scripts/repair_dart_fiscal_year_end.py --dry-run
  python scripts/repair_dart_fiscal_year_end.py --symbol 097870
  python scripts/repair_dart_fiscal_year_end.py --manifest /path/to/manifest.txt
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

import polars as pl

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _REPO_ROOT / "data" / "fundamentals"
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"
sys.path.insert(0, str(_REPO_ROOT / "backend"))

import engine.fundamental_fetcher as ff  # noqa: E402
from engine.fundamental_backfill import rebuild_fundamental_columns  # noqa: E402

# 옮길 DART 유래 필드. available_from은 공시일이라 함께 따라가야 한다.
_DART_FIELDS = (
    "available_from", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
    "operating_cf_amount", "investing_cf_amount", "financing_cf_amount",
    "capex", "fcf", "total_equity", "owner_net_income",
)
_KIS_MARKERS = ("eps", "bps", "net_margin", "sps", "roe_or_gpa", "debt_ratio")


def kis_fiscal_month(records: list[dict]) -> str | None:
    """KIS 유래 레코드만으로 본 결산월 — 대상 종목 선별용 힌트(정본은 DART acc_mt)."""
    kis = [r for r in records if any(k in r for k in _KIS_MARKERS)]
    if len(kis) < 2:
        return None
    return ff.fiscal_month(r.get("year_end", "") for r in kis)


def repair_symbol(symbol: str, *, dry_run: bool) -> tuple[str, list[str], int]:
    """Returns (status, changed_repo_relative_paths, moved_record_count)."""
    cache_path = _CACHE_DIR / f"{symbol}.json"
    if not cache_path.exists():
        return "no_cache", [], 0
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    records = payload.get("fundamentals") or []
    if not records:
        return "empty", [], 0

    hint = kis_fiscal_month(records)
    if hint is None or hint == "12":
        return "not_candidate", [], 0

    corp_code = ff._get_dart_corp_code(symbol)
    if not corp_code:
        return "no_corp_code", [], 0

    # **연도별** 결산월을 쓴다. 기업개황 acc_mt는 '현재' 결산월 하나뿐이라 결산기를 변경한
    # 회사(유유제약: 2017년 3월→12월)의 변경 이전 연도를 틀리게 만든다.
    periods = ff._fetch_dart_annual_report_periods(corp_code)
    if not periods:
        return "no_filing_dates", [], 0

    def month_for(year: int) -> str | None:
        known = periods.get(year)
        return known[0] if known else None

    by_year_end = {r.get("year_end"): r for r in records}
    moved = 0
    for record in list(records):
        year_end = str(record.get("year_end", ""))
        if not year_end.endswith("-12-31"):
            continue
        if not any(k in record for k in _DART_FIELDS if k != "available_from"):
            continue  # DART 유래가 아니면 건드리지 않는다
        month = month_for(int(year_end[:4]))
        if month is None:
            continue  # 그 해의 결산월을 모르면 손대지 않는다
        target_date = ff.dart_year_end(int(year_end[:4]), month)
        if target_date == year_end:
            continue
        target = by_year_end.get(target_date)
        if target is None:
            record["year_end"] = target_date        # 대응 KIS 레코드가 없으면 라벨만 교체
            by_year_end.pop(year_end, None)
            by_year_end[target_date] = record
        else:
            for key in _DART_FIELDS:                # 있으면 병합 후 원본 제거
                if key in record:
                    target[key] = record[key]
            records.remove(record)
            by_year_end.pop(year_end, None)
        moved += 1

    if not moved:
        return "clean", [], 0

    records = ff._compute_derived_annual_metrics(records)

    changed: list[str] = []
    if not dry_run:
        payload["fundamentals"] = records
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    changed.append(str(cache_path.relative_to(_REPO_ROOT)))

    parquet_path = _OHLCV_DIR / f"{symbol}.parquet"
    if parquet_path.exists():
        if not dry_run:
            pdf = pl.read_parquet(parquet_path).to_pandas()
            rebuilt = rebuild_fundamental_columns(pdf, records)
            pl.from_pandas(rebuilt).write_parquet(parquet_path)
        changed.append(str(parquet_path.relative_to(_REPO_ROOT)))

    return f"moved_{moved}", changed, moved


def main() -> None:
    from dotenv import load_dotenv  # 모듈 레벨 금지 — .env 오염 함정(메모리 참고)

    load_dotenv(_REPO_ROOT / ".env")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", help="single 6-digit ticker")
    ap.add_argument("--limit", type=int, help="process at most N symbols")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--manifest", help="append changed repo-relative paths to this file")
    args = ap.parse_args()

    if not os.getenv("DART_API_KEY", "").strip():
        print("[fy-repair] DART_API_KEY 미설정 — 중단")
        sys.exit(2)

    if args.symbol:
        symbols = [args.symbol]
    else:
        symbols = sorted(
            p.stem for p in _CACHE_DIR.glob("[0-9]*.json")
            if not p.name.endswith(".nodata.json")
        )
    if args.limit:
        symbols = symbols[: args.limit]

    print(f"[fy-repair] 대상 {len(symbols):,}종목 dry_run={args.dry_run}")
    tally: dict[str, int] = {}
    manifest_paths: list[str] = []
    moved_total = 0
    for i, symbol in enumerate(symbols, 1):
        try:
            status, changed, moved = repair_symbol(symbol, dry_run=args.dry_run)
        except Exception as error:  # noqa: BLE001 — 한 종목 실패가 배치를 죽이면 안 된다
            status, changed, moved = "error", [], 0
            print(f"  [{symbol}] error: {error}")
        bucket = status if not status.startswith("moved_") else "moved"
        tally[bucket] = tally.get(bucket, 0) + 1
        moved_total += moved
        manifest_paths.extend(changed)
        if status.startswith("moved_"):
            print(f"  [{i}/{len(symbols)}] {symbol}: {status}")

    if args.manifest and manifest_paths:
        with open(args.manifest, "a", encoding="utf-8") as fh:
            for path in manifest_paths:
                fh.write(path + "\n")
    print(f"[fy-repair] done: {dict(sorted(tally.items()))} / 이동 레코드 {moved_total:,}")


if __name__ == "__main__":
    main()
