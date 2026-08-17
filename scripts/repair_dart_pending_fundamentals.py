"""DART 한도 소진으로 미완성인 재무 캐시를 완성한다(KIS 재조회 없음, DART만).

배경(2026-08-17 규명): 2026-08-04 새벽 전수 백필이 04시경 DART 일일 허용량(status 020)에
걸렸다. 그때의 `_fetch_cash_flow_from_dart`는 한도 소진을 조용히 None으로 돌려줬고,
`fetch_fundamentals`는 그것을 '데이터 없음'과 구분하지 않고 KIS 값만으로 **완성본** 캐시를
썼다. 결과: 약 420개 활성 종목의 캐시에 DART 유래 항목(지배주주순이익·당기순이익 정본·
영업/투자/재무현금흐름·CAPEX·FCF·자본총계)이 통째로 없고, 이후 백필·remerge가 전부
"캐시 있음"으로 건너뛰었다. 근본 수정은 fetcher 쪽(DartQuotaExhausted → dart_pending 캐시
→ 다음 날 만료)이고, 이 스크립트는 **그 이전에 만들어진 캐시**와 dart_pending 캐시를 채운다.

대상 (둘 중 하나):
  · 캐시에 dart_pending 표시가 있다
  · 캐시 어느 연도에도 operating_cash_flow가 없다(= DART 응답이 한 번도 병합된 적 없다)
  둘 다 DART 기업코드가 있는 종목만 — 코드가 없으면 조회할 방법이 없다.

처리(종목당): `_fetch_cash_flow_from_dart` → 기존 KIS 레코드에 연도별 병합 → 파생 지표
재계산(`_compute_derived_annual_metrics`, 멱등) → 캐시 재기록(dart_pending 해제) → parquet은
`rebuild_fundamental_columns`(캐시 우선)로 재구축. DART가 실제로 아무것도 안 주는 종목
(사업보고서 미제출·별도재무제표만 제출 등)은 캐시를 손대지 않고 no_dart_data로 센다 —
dart_pending 표시만 있던 경우엔 표시를 지운다(재시도 결과가 '없음'으로 확정됐으므로).

한도: status 020을 만나면 즉시 종료코드 3으로 멈춘다(그 종목은 미기록). 다음 날 재실행하면
남은 종목만 다시 대상이 된다(대상 판정이 캐시 상태에서 나오므로 진행 파일이 필요 없다).

--refresh-corpcode: DART corpCode.xml을 다시 받아 data/dart_corpcode.json에 **추가**한다
(기존 매핑은 바꾸지 않고 신규 상장사만 더한다). 매핑이 없어 DART를 못 받던 신규 상장 종목이
이 뒤에 대상으로 잡힌다.

Usage:
  python scripts/repair_dart_pending_fundamentals.py --dry-run
  python scripts/repair_dart_pending_fundamentals.py --refresh-corpcode --dry-run
  python scripts/repair_dart_pending_fundamentals.py --symbol 340810
  python scripts/repair_dart_pending_fundamentals.py --refresh-corpcode
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("POLARS_MAX_THREADS", "1")

import polars as pl
import requests
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _REPO_ROOT / "data" / "fundamentals"
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"
_CORPCODE_PATH = _REPO_ROOT / "data" / "dart_corpcode.json"
sys.path.insert(0, str(_REPO_ROOT / "backend"))
load_dotenv(_REPO_ROOT / ".env")

import engine.fundamental_fetcher as ff  # noqa: E402
from engine.fundamental_backfill import rebuild_fundamental_columns  # noqa: E402


def refresh_corpcode(*, dry_run: bool) -> int:
    """corpCode.xml을 받아 신규 상장사 매핑을 더한다. Returns 추가된 건수."""
    key = os.getenv("DART_API_KEY", "").strip()
    if not key:
        raise SystemExit("DART_API_KEY가 없다")
    existing: dict[str, str] = json.loads(_CORPCODE_PATH.read_text(encoding="utf-8")) if _CORPCODE_PATH.exists() else {}
    r = requests.get(f"{ff._DART_BASE_URL}/corpCode.xml", params={"crtfc_key": key}, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(z.read(z.namelist()[0]))
    added = 0
    for el in root.iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        cc = (el.findtext("corp_code") or "").strip()
        if len(sc) == 6 and cc and sc not in existing:
            existing[sc] = cc
            added += 1
    print(f"[corpcode] 신규 {added}건 (총 {len(existing)})")
    if added and not dry_run:
        _CORPCODE_PATH.write_text(json.dumps(existing), encoding="utf-8")
        ff._DART_CORP_CODES = None  # 다시 읽게
    return added


def _load_cache(symbol: str) -> dict | None:
    path = _CACHE_DIR / f"{symbol}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_target(payload: dict) -> bool:
    if payload.get("dart_pending"):
        return True
    records = payload.get("fundamentals") or []
    return bool(records) and not any(r.get("operating_cash_flow") is not None for r in records)


def find_targets() -> list[str]:
    symbols = []
    for path in sorted(_CACHE_DIR.glob("[0-9A-Z]*.json")):
        if path.name.endswith(".nodata.json"):
            continue
        payload = _load_cache(path.stem)
        if not payload or not is_target(payload):
            continue
        if not ff._get_dart_corp_code(path.stem):
            continue
        symbols.append(path.stem)
    return symbols


def repair_symbol(symbol: str, *, dry_run: bool) -> str:
    payload = _load_cache(symbol)
    if not payload:
        return "no_cache"
    records = payload.get("fundamentals") or []

    cash_flow = ff._fetch_cash_flow_from_dart(symbol)  # DartQuotaExhausted는 위로 던진다
    if not cash_flow:
        if payload.get("dart_pending") and not dry_run:
            payload.pop("dart_pending", None)
            (_CACHE_DIR / f"{symbol}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return "no_dart_data"

    merged = ff._merge_fundamental_records(records, cash_flow) or []
    merged = ff._compute_derived_annual_metrics(merged)
    if dry_run:
        return "would_repair"

    ff._write_cache(symbol, merged)  # dart_pending 없이 = 완성본

    parquet_path = _OHLCV_DIR / f"{symbol}.parquet"
    if parquet_path.exists():
        pdf = pl.read_parquet(parquet_path).to_pandas()
        rebuilt = rebuild_fundamental_columns(pdf, merged)
        if not rebuilt.equals(pdf):
            pl.from_pandas(rebuilt).write_parquet(parquet_path)
    return "repaired"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh-corpcode", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.05)
    args = ap.parse_args()

    if not os.getenv("DART_API_KEY", "").strip():
        raise SystemExit("DART_API_KEY가 없다")

    if args.refresh_corpcode:
        refresh_corpcode(dry_run=args.dry_run)

    symbols = [args.symbol] if args.symbol else find_targets()
    if args.limit:
        symbols = symbols[: args.limit]
    print(f"대상 {len(symbols)}종목{' (dry-run)' if args.dry_run else ''}")

    tally: dict[str, int] = {}
    for i, symbol in enumerate(symbols, 1):
        try:
            status = repair_symbol(symbol, dry_run=args.dry_run)
        except ff.DartQuotaExhausted:
            print(f"[{i}/{len(symbols)}] {symbol}: DART 일일 허용량 소진 — 중단(내일 재실행)")
            print("tally:", tally)
            sys.exit(3)
        tally[status] = tally.get(status, 0) + 1
        if i % 25 == 0 or status not in ("repaired", "would_repair"):
            print(f"[{i}/{len(symbols)}] {symbol}: {status}")
        time.sleep(args.sleep)
    print("tally:", tally)


if __name__ == "__main__":
    main()
