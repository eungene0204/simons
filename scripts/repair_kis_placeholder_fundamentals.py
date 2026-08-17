"""KIS 0 자리표시자 연도로 오염된 재무 캐시·parquet을 수리한다.

배경(2026-08-17 규명): KIS 재무 엔드포인트는 재무를 싣지 않은 회사·연도에도 행을 돌려주되
값을 전부 0으로 채운다(삼진제약 005500: 22개 연도 전부 eps 0·sps 0·bps 0·부채비율 0). 연결
재무제표를 만들지 않는 회사와 KIS 이력 시작 전 연도(2004~2009년 다수)가 이렇다. 0을 진짜
값으로 받아 forward-fill한 결과 —
  · PER·PBR·PSR·ROE가 분모 0으로 null → 가치 필터에서 통째로 사라짐(활성 124종목이 최근 1년
    내내 이 상태: 동국제강·케이카·크라운제과·삼진제약·현대약품 …)
  · 부채비율 0 → '부채비율 ≤ N' 필터를 **거짓 통과**
  · 활성 636종목이 어느 연도엔가 자리표시자를 가진다(대부분 2004~2009 선행 연도)

근본 수정은 engine.fundamental_fetcher.drop_kis_placeholder_records + Naver 보충(앞으로 받는
데이터). 이 스크립트는 **이미 캐시·parquet에 들어온** 자리표시자를 걷어낸다.

수리 절차 (종목당, 기본 모드):
  1. fetch_fundamentals(use_cache=False)로 재조회 — KIS(자리표시자 제거) + Naver 보충 + DART.
     엔진과 같은 한 경로를 타므로 캐시가 엔진 출력과 정확히 같다.
  2. DART 일일 허용량 소진(dart_pending)이면 **옛 캐시를 복원**하고 종료코드 3으로 멈춘다 —
     DART 항목(현금흐름·지배주주순이익)이 빠진 캐시로 parquet을 덮지 않기 위해서다. 다음 날
     재실행하면 남은 종목만 다시 대상이 된다(대상 판정이 캐시 상태에서 나온다).
  3. parquet에서 자리표시자 서명 행(eps=bps=sps=0)의 연간 재무 컬럼·PER/PBR/PSR을 비운 뒤
     교정 캐시로 재구축(engine.fundamental_backfill.rebuild_fundamental_columns). 재구축은
     '캐시가 모르는 날은 기존 값 보존'이라 먼저 비우지 않으면 옛 0이 살아남는다. 서명은
     parquet 자체에서 나오므로 옛 캐시 없이도(프로덕션에서도) 같은 결과다.

--rebuild-only: 재조회 없이 3단계만 한다(프로덕션 반영용 — 로컬에서 수리한 캐시를 push한 뒤
현지 parquet을 재구축). --since YYYY-MM-DD 로 그날 이후 갱신된 캐시만 고른다.

대상 순서: 최신 연도가 자리표시자인 종목(지금 필터에서 사라진 종목)을 먼저, 과거 연도만인
종목을 나중에 — DART 한도에 걸려 끊겨도 급한 쪽이 먼저 끝난다.

Usage:
  python scripts/repair_kis_placeholder_fundamentals.py --dry-run
  python scripts/repair_kis_placeholder_fundamentals.py --symbol 005500
  python scripts/repair_kis_placeholder_fundamentals.py --limit 150
  python scripts/repair_kis_placeholder_fundamentals.py --rebuild-only --since 2026-08-17   # 프로덕션
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

import numpy as np
import pandas as pd
import polars as pl
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _REPO_ROOT / "data" / "fundamentals"
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"
_ACTIVE_PATH = _REPO_ROOT / "data" / "korea-stocks.json"
sys.path.insert(0, str(_REPO_ROOT / "backend"))
load_dotenv(_REPO_ROOT / ".env")

import engine.fundamental_fetcher as ff  # noqa: E402
from engine.fundamental_backfill import rebuild_fundamental_columns  # noqa: E402

# 자리표시자 서명 행에서 비우는 컬럼 — 연간 재무 전부 + 그 파생 비율. 재구축이 캐시로 다시
# 채우고, 캐시가 모르는(자리표시자였던 선행) 연도는 비어 있는 채로 남아 fail-closed가 된다.
_CLEAR_COLUMNS = list(ff.ANNUAL_FUNDAMENTAL_KEYS) + list(ff.ANNUAL_FUNDAMENTAL_STATUS_KEYS) + ["per", "pbr", "psr"]

# 판정 키의 정본은 엔진(fundamental_fetcher._KIS_PLACEHOLDER_KEYS). 폴백은 --rebuild-only를
# 엔진 배포 전의 프로덕션(구 fundamental_fetcher)에서 돌리기 위한 것이며 값은 정본과 같다.
_PLACEHOLDER_KEYS = getattr(ff, "_KIS_PLACEHOLDER_KEYS", ("eps", "bps", "sps"))


def _is_placeholder(record: dict) -> bool:
    return all(record.get(k) is not None and record.get(k) == 0 for k in _PLACEHOLDER_KEYS)


def _load_cache(symbol: str) -> dict | None:
    path = _CACHE_DIR / f"{symbol}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _placeholder_years(payload: dict) -> list[str]:
    return [r["year_end"] for r in (payload.get("fundamentals") or []) if _is_placeholder(r)]


def _latest_is_placeholder(payload: dict) -> bool:
    kis = sorted((r for r in (payload.get("fundamentals") or []) if "eps" in r), key=lambda r: r["year_end"])
    return bool(kis) and _is_placeholder(kis[-1])


def find_targets() -> list[str]:
    active = {s["symbol"] for s in json.loads(_ACTIVE_PATH.read_text(encoding="utf-8"))}
    urgent, later = [], []
    for symbol in sorted(active):
        payload = _load_cache(symbol)
        if not payload or not _placeholder_years(payload):
            continue
        (urgent if _latest_is_placeholder(payload) else later).append(symbol)
    return urgent + later


def clear_placeholder_rows(pdf: pd.DataFrame) -> int:
    """parquet의 자리표시자 서명 행(eps=bps=sps=0)에서 연간 재무 컬럼을 비운다. Returns 행 수."""
    if not all(c in pdf.columns for c in _PLACEHOLDER_KEYS):
        return 0
    mask = np.ones(len(pdf), dtype=bool)
    for c in _PLACEHOLDER_KEYS:
        mask &= (pdf[c] == 0).to_numpy()
    n = int(mask.sum())
    if n:
        for c in _CLEAR_COLUMNS:
            if c in pdf.columns:
                pdf.loc[mask, c] = None if pdf[c].dtype == object else np.nan
    return n


def rebuild_parquet(symbol: str, records: list[dict], *, dry_run: bool) -> tuple[int, bool]:
    """Returns (cleared_rows, written)."""
    path = _OHLCV_DIR / f"{symbol}.parquet"
    if not path.exists():
        return 0, False
    pdf = pl.read_parquet(path).to_pandas()
    cleared = clear_placeholder_rows(pdf)
    rebuilt = rebuild_fundamental_columns(pdf, records)
    if not dry_run:
        pl.from_pandas(rebuilt).write_parquet(path)
    return cleared, not dry_run


def repair_symbol(symbol: str, *, dry_run: bool, rebuild_only: bool) -> str:
    old = _load_cache(symbol)
    if not old:
        return "no_cache"

    if rebuild_only:
        records = old.get("fundamentals") or []
        if any(_is_placeholder(r) for r in records):
            return "cache_still_placeholder"  # 수리된 캐시가 아니다 — 먼저 기본 모드로 돌릴 것
        cleared, _ = rebuild_parquet(symbol, records, dry_run=dry_run)
        return f"rebuilt(cleared {cleared})"

    if dry_run:
        return f"would_refetch({len(_placeholder_years(old))} placeholder years)"

    records = ff.fetch_fundamentals(symbol, use_cache=False)
    if not records:
        # 재조회가 비면 옛 캐시는 그대로 남아 있다(fetch는 양성 캐시를 지우지 않는다).
        (_CACHE_DIR / f"{symbol}.nodata.json").unlink(missing_ok=True)
        return "no_data"

    if ff.is_dart_pending(symbol):
        (_CACHE_DIR / f"{symbol}.json").write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
        raise ff.DartQuotaExhausted(symbol)

    if any(_is_placeholder(r) for r in records):
        return "still_placeholder"  # 근본 수정이 걷어내지 못했다 — 조사 필요

    cleared, _ = rebuild_parquet(symbol, records, dry_run=False)
    return f"repaired(cleared {cleared})"


def wait_for_kis_token(max_wait_s: float = 300) -> None:
    """KIS 토큰을 먼저 확보한다 — 발급은 1분당 1회라 직전 프로세스와 겹치면 403이 난다.

    토큰 없이 fetch_fundamentals를 돌리면 KIS 단계가 조용히 None이 되어 'KIS에 없음'과 구분되지
    않고, Naver 3개년만으로 캐시가 90일짜리 완성본으로 덮인다(2026-08-17 실측: 첫 실행에서
    토큰 403 뒤 2분간 30여 종목이 그렇게 기록돼 되돌렸다). 확보될 때까지 기다린다.
    """
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        if ff._get_kis_token():
            return
        print("[KIS] 토큰 대기 중(발급 제한 1분/1회) …")
        time.sleep(65)
    raise SystemExit("KIS 토큰을 확보하지 못했다 — 중단")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol")
    ap.add_argument("--symbols-file", help="한 줄에 한 종목코드 — 이 목록만 처리(대상 판정 무시)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rebuild-only", action="store_true", help="재조회 없이 캐시로 parquet만 재구축")
    ap.add_argument("--since", help="--rebuild-only 대상: 이 날짜(YYYY-MM-DD) 이후 갱신된 캐시 전부")
    ap.add_argument("--sleep", type=float, default=0.3, help="종목 사이 대기(초) — Naver 스크래핑 예의")
    args = ap.parse_args()

    if args.symbol:
        symbols = [args.symbol]
    elif args.symbols_file:
        symbols = [ln.strip() for ln in Path(args.symbols_file).read_text().splitlines() if ln.strip()]
    elif args.rebuild_only and args.since:
        symbols = sorted(
            p.stem for p in _CACHE_DIR.glob("[0-9A-Z]*.json")
            if not p.name.endswith(".nodata.json")
            and ((_load_cache(p.stem) or {}).get("fetched_at") or "") >= args.since
        )
    else:
        symbols = find_targets()
    if args.limit:
        symbols = symbols[: args.limit]
    mode = "rebuild-only" if args.rebuild_only else "refetch"
    print(f"대상 {len(symbols)}종목 [{mode}]{' (dry-run)' if args.dry_run else ''}")
    if symbols and not args.dry_run and not args.rebuild_only:
        wait_for_kis_token()

    tally: dict[str, int] = {}
    for i, symbol in enumerate(symbols, 1):
        try:
            status = repair_symbol(symbol, dry_run=args.dry_run, rebuild_only=args.rebuild_only)
        except ff.DartQuotaExhausted:
            print(f"[{i}/{len(symbols)}] {symbol}: DART 일일 허용량 소진 — 옛 캐시 복원 후 중단(내일 재실행)")
            print("tally:", tally)
            sys.exit(3)
        key = status.split("(")[0]
        tally[key] = tally.get(key, 0) + 1
        if i % 25 == 0 or key not in ("repaired", "rebuilt", "would_refetch"):
            print(f"[{i}/{len(symbols)}] {symbol}: {status}")
        if not args.dry_run and not args.rebuild_only:
            time.sleep(args.sleep)
    print("tally:", tally)


if __name__ == "__main__":
    main()
