"""Remove KIS interim (분기) records from the fundamentals cache + rebuild parquet.

배경(2026-08-07): KIS 재무 엔드포인트는 연간(FID_DIV_CLS_CODE=0)을 요청해도 **최신 분기
한 행**을 맨 앞에 끼워 보낸다(현대차 실측: stac_yymm 202603, 202512, 202412, 202312 …).
파라미터로 뺄 수 없어 우리가 걸러야 하는데 그러지 않고 연간처럼 캐시에 넣어 왔다.

그 행의 비율은 연환산돼 정상이지만 유량은 기중 누적이라 1분기치다(현대차: ROE 89%·
부채비율 101%인데 EPS 25%·영업이익 22%·EBITDA 23%·당기순이익 25%). 성장률은 분기 행이
직전 '연간'과 비교되면서 순이익증가율 -75%·영업이익증가율 -78%로 오염되고, PER은
종가÷EPS라 약 4배로 부푼다. 실측 3,220종목 중 **2,150종목(67%)** 의 최신 레코드가 분기다.

근본 수정은 engine.fundamental_fetcher.drop_kis_interim_records(앞으로 받는 데이터).
이 스크립트는 **이미 캐시에 들어온 분기 행**을 걷어내고 parquet을 재구축한다.

수리 절차 (종목당):
  1. 캐시 레코드에서 결산월(월 최빈값)과 다른 레코드를 제거 — DART 유래 필드가 붙어 있는
     레코드는 건드리지 않는다(연간 사업보고서 유래라 애초에 분기가 아니다)
  2. 남은 레코드로 파생 지표(성장률·상태코드 등)를 재계산 후 캐시 재기록
  3. parquet의 연간 재무 컬럼을 교정 캐시 기준으로 **재구축**
     (engine.fundamental_backfill.rebuild_fundamental_columns — 캐시 우선, PER/PBR/PSR 정합)

DART·KIS 호출이 없다(순수 로컬 재계산). 멱등이라 재실행해도 결과가 같다.

Usage:
  python scripts/repair_interim_fundamental_records.py --dry-run --limit 5
  python scripts/repair_interim_fundamental_records.py --symbol 005380
  python scripts/repair_interim_fundamental_records.py --manifest /path/to/manifest.txt
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

# DART(사업보고서) 유래 필드 — 이 키가 붙은 레코드는 연간이 확실하므로 지우지 않는다.
_DART_MARKERS = ("operating_cash_flow", "owner_net_income", "total_equity", "capex")
# KIS 유래 필드 — 분기 혼입은 KIS 쪽에서만 생기므로 판정 시퀀스는 이 레코드들로만 만든다.
_KIS_MARKERS = ("eps", "bps", "net_margin", "sps", "roe_or_gpa", "debt_ratio")


def interim_records(records: list[dict]) -> list[dict]:
    """캐시에 쌓인 분기 레코드. 판정은 근본 수정과 같은 규칙(직전 레코드와의 간격)을 쓴다.

    근본 수정(drop_kis_interim_records)은 KIS 응답만 다루므로 매번 최신 한 행만 보면 되지만,
    캐시에는 과거 갱신 때 들어온 분기 행이 여러 개 남아 있을 수 있어 더 이상 걸리지 않을
    때까지 반복 적용한다.

    **판정 시퀀스는 KIS 유래 레코드로만 만든다.** 비12월 결산 회사는 DART 레코드가
    `{year}-12-31`로 잘못 라벨돼 있어(3월 결산인데 12-31) 그대로 섞으면 간격이 뒤틀린다 —
    실측: 000220의 정상 연간 2026-03-31이 바로 앞 DART 2025-12-31과 3개월 차라 분기로
    오인됐다. 12월 결산 회사는 KIS·DART가 같은 레코드에 병합되므로 시퀀스에 그대로 남는다.
    DART 유래 레코드는 어떤 경우에도 지우지 않는다(현금흐름·지배주주순이익·자본총계 보호).
    """
    protected = {
        id(r) for r in records if any(k in r for k in _DART_MARKERS)
    }
    remaining = [r for r in records if any(k in r for k in _KIS_MARKERS)]
    dropped: list[dict] = []
    while len(remaining) > 1:
        kept = ff.drop_kis_interim_records(remaining)
        if len(kept) == len(remaining):
            break
        removed = [r for r in remaining if not any(r is k for k in kept)]
        if any(id(r) in protected for r in removed):
            break  # DART 유래를 지우려 하면 중단한다
        dropped.extend(removed)
        remaining = kept
    return dropped


def repair_symbol(symbol: str, *, dry_run: bool) -> tuple[str, list[str], int]:
    """Returns (status, changed_repo_relative_paths, removed_record_count)."""
    cache_path = _CACHE_DIR / f"{symbol}.json"
    if not cache_path.exists():
        return "no_cache", [], 0
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    records = payload.get("fundamentals") or []

    drop = interim_records(records)
    if not drop:
        return "clean", [], 0

    drop_keys = {r["year_end"] for r in drop}
    kept = [r for r in records if r.get("year_end") not in drop_keys]
    if not kept:
        return "would_empty", [], 0  # 전부 분기로 판정되면 손대지 않는다(판별 실패)

    kept = ff._compute_derived_annual_metrics(kept)

    changed: list[str] = []
    if not dry_run:
        payload["fundamentals"] = kept
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    changed.append(str(cache_path.relative_to(_REPO_ROOT)))

    parquet_path = _OHLCV_DIR / f"{symbol}.parquet"
    if parquet_path.exists():
        if not dry_run:
            pdf = pl.read_parquet(parquet_path).to_pandas()
            rebuilt = rebuild_fundamental_columns(pdf, kept)
            pl.from_pandas(rebuilt).write_parquet(parquet_path)
        changed.append(str(parquet_path.relative_to(_REPO_ROOT)))

    return f"removed_{len(drop)}", changed, len(drop)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", help="single 6-digit ticker")
    ap.add_argument("--limit", type=int, help="process at most N symbols")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--manifest", help="append changed repo-relative paths to this file")
    args = ap.parse_args()

    if args.symbol:
        symbols = [args.symbol]
    else:
        symbols = sorted(
            p.stem for p in _CACHE_DIR.glob("[0-9]*.json")
            if not p.name.endswith(".nodata.json")
        )
    if args.limit:
        symbols = symbols[: args.limit]

    print(f"[interim-repair] 대상 {len(symbols):,}종목 dry_run={args.dry_run}")
    tally: dict[str, int] = {}
    manifest_paths: list[str] = []
    removed_total = 0
    for i, symbol in enumerate(symbols, 1):
        try:
            status, changed, removed = repair_symbol(symbol, dry_run=args.dry_run)
        except Exception as error:  # noqa: BLE001 — 한 종목 실패가 배치를 죽이면 안 된다
            status, changed, removed = "error", [], 0
            print(f"  [{symbol}] error: {error}")
        bucket = status if status in {"clean", "no_cache", "would_empty", "error"} else "removed"
        tally[bucket] = tally.get(bucket, 0) + 1
        removed_total += removed
        manifest_paths.extend(changed)
        if i % 500 == 0:
            print(f"  [{i}/{len(symbols)}] {symbol}: {status}")

    if args.manifest and manifest_paths:
        with open(args.manifest, "a", encoding="utf-8") as fh:
            for path in manifest_paths:
                fh.write(path + "\n")
    print(f"[interim-repair] done: {dict(sorted(tally.items()))} / 제거 레코드 {removed_total:,}")


if __name__ == "__main__":
    main()
