"""data/stock-master.json 제자리 갱신 — 전체 재빌드 없이 신선도만 되살린다(멱등).

전체 재빌드(`build_stock_master.py`)는 마스터에 누적된 섹터 후처리(묶음 분류 분할
`split_combined_sectors.py`, 27종목 외과 패치)를 통째로 되돌린다. 그래서 일상적인 갱신은
이 스크립트가 맡는다 — 기존 행의 curated 필드(sector·industry·name)를 보존한 채

  ① 로컬 OHLCV 커버리지(dataStart/dataEnd/hasOhlcv) 재스캔,
  ② FDR KRX-DELISTING의 신규 상장폐지 반영(기존 활성 행에 delistingDate 부여 + 신규 행 추가),
  ③ 신규 상장 종목 추가 및 활성 행의 상장주식수·종목명 갱신

만 수행한다.

**왜 필요한가(생존 편향)**: as-of 유니버스(`engine/universe_pit.py`)는 이 파일의
`dataStart ≤ 창끝 AND dataEnd ≥ 창시작`으로 "그 구간에 살아 있던 종목"을 정한다. 파일이
낡으면 두 가지가 동시에 일어난다 — 낡은 시점 이후 상장폐지된 종목이 유니버스에서 통째로
빠지고(전형적 생존 편향), 창 시작이 `dataEnd`보다 뒤면 as-of 결과가 0종목이 돼 엔진이
프론트가 보낸 **현재 상장 종목 목록**으로 조용히 폴백한다. 2026-09-16 실측: 마스터
생성일 2026-06-13, 2026-06-14 이후 시작 창의 as-of 결과 0종목.

Run:
    cd backend && python scripts/refresh_stock_master.py
    cd backend && python scripts/refresh_stock_master.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_stock_master import (  # noqa: E402
    _KST,
    _OUT_PATH,
    _load_active,
    _load_delisted,
    _scan_local_ohlcv_coverage,
)

# 기존 행에서 절대 덮어쓰지 않는 필드 — 재빌드로는 복원되지 않는 후처리 결과다.
_CURATED_FIELDS = ("sector", "industry")


def refresh(master: dict, coverage: dict, active: dict, delisted: dict) -> dict:
    """마스터 payload를 제자리 갱신한 새 payload를 반환한다(입력을 변경하지 않는다)."""
    rows = {s["symbol"]: dict(s) for s in master.get("stocks", [])}

    # ② 신규 상장폐지 — 기존 행이면 상폐 필드만 얹고, 없으면 새로 넣는다.
    for sym, src in delisted.items():
        row = rows.get(sym)
        if row is None:
            rows[sym] = dict(src)
            continue
        for field in ("delistingDate", "reason", "toSymbol"):
            if src.get(field) is not None:
                row[field] = src[field]
        for field in ("market", "listingDate", "shares"):
            if row.get(field) is None and src.get(field) is not None:
                row[field] = src[field]
        for field in _CURATED_FIELDS:
            if row.get(field) is None and src.get(field) is not None:
                row[field] = src[field]

    # ③ 신규 상장 + 활성 행 갱신. 상폐 이력이 있는 행은 건드리지 않는다(코드 재사용 방지).
    for sym, src in active.items():
        row = rows.get(sym)
        if row is None:
            rows[sym] = dict(src)
            continue
        if row.get("delistingDate"):
            continue
        for field in ("name", "market", "shares", "listingDate"):
            if src.get(field) is not None:
                row[field] = src[field]

    # ① 로컬 가격 커버리지 — 언제나 로컬 parquet이 정본이다.
    for sym, row in rows.items():
        cov = coverage.get(sym)
        row["dataStart"] = cov[0] if cov else None
        row["dataEnd"] = cov[1] if cov else None
        row["hasOhlcv"] = cov is not None

    stocks = sorted(rows.values(), key=lambda s: s["symbol"])
    return {
        "generatedAt": datetime.now(_KST).isoformat(),
        "delistingFloor": master.get("delistingFloor"),
        "counts": {
            "total": len(stocks),
            "active": sum(1 for s in stocks if not s.get("delistingDate")),
            "delisted": sum(1 for s in stocks if s.get("delistingDate")),
            "withOhlcv": sum(1 for s in stocks if s.get("hasOhlcv")),
            "delistedWithOhlcv": sum(1 for s in stocks if s.get("delistingDate") and s.get("hasOhlcv")),
            "delistedMissingOhlcv": sum(
                1 for s in stocks if s.get("delistingDate") and not s.get("hasOhlcv")
            ),
        },
        "stocks": stocks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="stock-master.json 제자리 갱신")
    parser.add_argument("--dry-run", action="store_true", help="파일에 쓰지 않고 변화만 출력")
    args = parser.parse_args(argv)

    if not _OUT_PATH.exists():
        print(f"[stock-master] {_OUT_PATH} 없음 — 최초 1회는 build_stock_master.py로 만든다")
        return 1
    master = json.loads(_OUT_PATH.read_text(encoding="utf-8"))

    import FinanceDataReader as fdr

    print("[stock-master] scanning local OHLCV coverage...")
    coverage = _scan_local_ohlcv_coverage()
    print(f"[stock-master]   {len(coverage)} local parquet files")
    print("[stock-master] loading FDR active listings (KOSPI/KOSDAQ)...")
    active = _load_active(fdr)
    print(f"[stock-master]   {len(active)} active commons")
    print("[stock-master] loading FDR KRX-DELISTING...")
    delisted = _load_delisted(fdr)
    print(f"[stock-master]   {len(delisted)} delisted commons")

    before = master.get("counts", {})
    payload = refresh(master, coverage, active, delisted)
    after = payload["counts"]
    print(f"[stock-master] total {before.get('total')} → {after['total']}, "
          f"delisted {before.get('delisted')} → {after['delisted']}")
    max_end = max((s.get("dataEnd") or "") for s in payload["stocks"])
    print(f"[stock-master] 최신 가격 커버리지 dataEnd={max_end}")

    if args.dry_run:
        print("[stock-master] --dry-run: 파일을 쓰지 않았습니다")
        return 0
    _OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[stock-master] wrote {_OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
