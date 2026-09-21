"""Backfill DART ROIC·FCF 마진 원재료 into the fundamentals cache + parquet (엔진 v16.14).

배경(2026-09-19): ROIC(투하자본이익률)와 FCF 마진(잉여현금흐름 ÷ 매출액)은 이미 부르던
`fnlttSinglAcntAll.json` 응답의 재무상태표·손익계산서 계정으로 계산할 수 있지만, 캐시는 파싱
결과만 남기고 raw 응답을 보관하지 않으므로 과거 구간은 재조회 없이 채울 수 없다.
매출액(revenue)도 2026-08-17 이후 조회분에만 있어 표본 200종목 중 12종목뿐이었다.

수집 항목(원 단위, 같은 응답에서 추가 호출 0 — engine.fundamental_fetcher.parse_dart_roic_inputs):
  cash_and_equivalents · interest_bearing_debt(차입금·사채, 리스 제외) · pretax_income ·
  income_tax_expense · 매출액(→ revenue 억원)
파생(engine.fundamental_fetcher._compute_derived_annual_metrics):
  roic = 영업이익 × (1 − 유효세율) ÷ (자본총계 + 이자부부채 − 현금)
  fcf_margin = FCF ÷ 매출액

**조회 범위를 OCF 보유 연도로 좁힌다** — OCF와 이 계정들은 한 응답에서 나오므로 OCF가 없는
연도는 그 응답 자체가 없었다는 뜻이다(지배주주순이익 백필과 같은 논리·같은 규모의 호출 예산).

재개 가능: 완료 종목을 progress 파일에 기록해 재실행 시 건너뛴다.
쿼터 분할: --max-calls로 1회 실행의 DART 호출 예산을 정한다. status 020이면 진행 상황을
저장하고 종료코드 3으로 중단 — 리셋 후 재실행하면 남은 종목부터 재개된다.

**정본=프로덕션**(project_data_mirror): 로컬 parquet은 야간 pull이 되돌린다. 캐시(JSON)가
정본 재료이고, pull 이후엔 `--remerge-only`(DART 0회)로 parquet에 다시 내린다. **parquet의 방향은
프로덕션 → 로컬 하나뿐이다**(CLAUDE.md, 2026-09-21) — 프로덕션 parquet은 프로덕션에서 이 스크립트를
돌려 쓰고, 로컬 parquet은 올리지 않는다. parquet 쓰기는 **빈 칸만 채우는 병합**이다
(_rebuild_parquet 주석 — 캐시가 이기는 재구축은 기존 값을 지운다).

Usage:
  python scripts/backfill_roic_fcf_margin.py --dry-run --limit 5
  python scripts/backfill_roic_fcf_margin.py --max-calls 15000 --manifest /tmp/m.txt
  python scripts/backfill_roic_fcf_margin.py --symbol 005930
  python scripts/backfill_roic_fcf_margin.py --remerge-only
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

import polars as pl  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _REPO_ROOT / "data" / "fundamentals"
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"
_PROGRESS_PATH = _REPO_ROOT / "data" / "roic-fcf-margin-backfill.progress.json"
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
    """OCF가 있는 연도(= 그 해에 DART 응답이 있었다 — 재조회 가치가 있다)."""
    years = []
    for record in records:
        if record.get("operating_cash_flow") is None:
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
    """한 연도의 ROIC·FCF 마진 원재료. Returns (values, dart_calls_used).

    연결(CFS)을 먼저 보고, 원재료가 하나도 없으면 별도(OFS)로 떨어진다 — OCF 파서와 같은 순서라
    한 레코드 안에서 연결/별도가 섞이지 않는다(OCF가 CFS에서 왔으면 여기서도 CFS가 먼저 잡힌다).
    """
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
        values = ff.parse_dart_roic_inputs(payload.get("list", []))
        if values:
            return values, calls
    return {}, calls


def _rebuild_parquet(symbol: str, records: list[dict], dry_run: bool) -> list[str]:
    parquet_path = _OHLCV_DIR / f"{symbol}.parquet"
    if not parquet_path.exists():
        return []
    pdf = pl.read_parquet(parquet_path).to_pandas()
    # **빈 칸만 채운다**(merge_fundamentals — 기존 값 우선). 종전에는 캐시가 이기는 rebuild를
    # 썼는데, 그 재구축은 캐시 지배 구간을 NaN까지 포함해 통째로 덮어 **캐시 밖에서 채워진 값**을
    # 지운다(2026-09-21 실측: 운영과 전수 대조하니 백필을 거친 199종목에서 EPS·BPS·부채비율·
    # ROE·PBR이 2016년부터 통째로 비어 있었다 — 001140). 이 백필이 더하는 것은 새 컬럼
    # (roic·fcf_margin·revenue)뿐이고, 캐시의 다른 키는 백필 전후가 같다(운영 캐시와 3,220종목
    # 전수 대조: 새 키 밖 차이 0) — 덮어쓸 이유가 없다. 운영 야간 동기화와 같은 병합이다.
    rebuilt = merge_fundamentals(pdf, records)
    if rebuilt.equals(pdf):
        return []
    if not dry_run:
        pl.from_pandas(rebuilt).write_parquet(parquet_path)
    return [str(parquet_path.relative_to(_REPO_ROOT))]


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

    by_year = {
        str(r.get("year_end", ""))[:4]: r
        for r in records
        if r.get("operating_cash_flow") is not None
    }
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
    changed.extend(_rebuild_parquet(symbol, records, dry_run))
    return f"filled_{filled}y", changed, calls


def remerge_symbol(symbol: str, *, dry_run: bool) -> tuple[str, list[str]]:
    """DART 호출 없이 캐시 → parquet 재병합(미러 pull 이후 복원용)."""
    cache_path = _CACHE_DIR / f"{symbol}.json"
    if not cache_path.exists():
        return "no_cache", []
    records = json.loads(cache_path.read_text(encoding="utf-8")).get("fundamentals") or []
    if not any("roic" in r or "fcf_margin" in r for r in records):
        return "nothing_to_merge", []
    changed = _rebuild_parquet(symbol, records, dry_run)
    return ("remerged" if changed else "unchanged"), changed


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
        symbols = [args.symbol] if args.symbol else sorted(
            p.stem for p in _CACHE_DIR.glob("[0-9]*.json") if not p.name.endswith(".nodata.json"))
        tally: dict[str, int] = {}
        paths: list[str] = []
        for symbol in symbols[: args.limit] if args.limit else symbols:
            try:
                status, changed = remerge_symbol(symbol, dry_run=args.dry_run)
            except Exception as error:  # noqa: BLE001
                status, changed = "error", []
                print(f"  [{symbol}] error: {error}")
            tally[status] = tally.get(status, 0) + 1
            paths.extend(changed)
        _flush_manifest(args.manifest, paths)
        print(f"[roic-backfill] remerge done: {dict(sorted(tally.items()))}")
        return

    if not os.getenv("DART_API_KEY", "").strip():
        print("[roic-backfill] DART_API_KEY 미설정 — 중단")
        sys.exit(2)

    done = load_progress()
    symbols = [args.symbol] if args.symbol else [s for s in find_target_symbols() if s not in done]
    if args.limit:
        symbols = symbols[: args.limit]
    total = len(symbols)
    print(f"[roic-backfill] 대상 {total:,}종목 (완료 기록 {len(done):,}종목 제외) "
          f"max_calls={args.max_calls or '무제한'} dry_run={args.dry_run}")

    tally = {}
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
        if not args.dry_run and status != "error":
            done.add(symbol)
        if i <= 5 or i % 100 == 0:
            print(f"  [{i}/{total}] {symbol}: {status} (누적 호출 {calls_used:,})", flush=True)
        # 진행 기록은 **중간에도** 남긴다 — 마지막에만 저장하면 중단(절전·세션 종료) 시
        # 이미 쓴 DART 호출이 통째로 헛돈다(하루 한도가 자원이다).
        if not args.dry_run and i % 25 == 0:
            save_progress(done)
            _flush_manifest(args.manifest, manifest_paths)
            manifest_paths = []
        if args.max_calls and calls_used >= args.max_calls:
            aborted = "budget"
            print(f"  [{i}/{total}] 호출 예산 {args.max_calls:,} 도달 — 중단(재실행으로 재개).")
            break
        if args.sleep:
            time.sleep(args.sleep)

    if not args.dry_run:
        save_progress(done)
    _flush_manifest(args.manifest, manifest_paths)
    print(f"[roic-backfill] {'aborted(' + aborted + ')' if aborted else 'done'}: "
          f"{dict(sorted(tally.items()))} / DART 호출 {calls_used:,}")
    if aborted == "quota":
        sys.exit(3)


if __name__ == "__main__":
    main()
