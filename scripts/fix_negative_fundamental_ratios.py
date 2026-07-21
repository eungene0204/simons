"""이미 저장된 parquet의 PER/PBR/ROE 중 분모(순이익/자기자본)가 음수·0이어서
금융적으로 무의미한 값을 null로 보정한다.

배경: backfill_fundamentals.py를 --force로 재실행해도 merge_fundamentals가
combine_first(기존값 우선)라 이미 저장된 음수 값을 덮어쓰지 못한다(자가 치유 안 됨).
이 스크립트는 새 API 호출 없이 이미 parquet에 있는 eps/bps/close 컬럼만으로
로컬에서 재계산해 그 갭을 메우는 1회성 보정 패스다 — 규칙은
engine/fundamental_status.py·engine/fundamental_fetcher.enrich_ohlcv_with_fundamentals와
동일: PER=close/eps(eps>0만), PBR=close/bps(bps>0만), ROE는 bps<=0이면 null.

EV/EBITDA는 대상이 아니다 — 기존 로직이 비양수 값을 아예 삭제해 왔으므로(정보 손실은
있었지만) 저장된 값 자체는 이미 null이라 보정할 게 없다. EBIT/CAPEX/자본총계/FCF/
EV/EV-EBIT·신규 성장률 4종은 애초에 수집된 적이 없어 이 스크립트의 대상이 아니다
(전 종목 DART/KIS 재수집이 필요한 별도의 더 큰 작업).

Usage:
  python scripts/fix_negative_fundamental_ratios.py --dry-run
  python scripts/fix_negative_fundamental_ratios.py --symbol 005930 --dry-run
  python scripts/fix_negative_fundamental_ratios.py                 # 전체 실행(쓰기)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import polars as pl

_REPO_ROOT = Path(__file__).resolve().parent.parent
_OHLCV_DIR = _REPO_ROOT / "data" / "ohlcv"


def fix_symbol(path: Path, *, dry_run: bool) -> tuple[str, int]:
    """한 parquet을 보정한다. (status, 보정된 셀 수)를 반환한다."""
    pdf = pl.read_parquet(path).to_pandas()
    corrected = 0

    if "eps" in pdf.columns and "per" in pdf.columns:
        invalid = pdf["eps"].notna() & (pdf["eps"] <= 0)
        corrected += int((invalid & pdf["per"].notna()).sum())
        close = pdf["close"].astype(float)
        valid = pdf["eps"].notna() & (pdf["eps"] > 0)
        pdf["per"] = (close / pdf["eps"]).where(valid).replace([np.inf, -np.inf], np.nan)

    if "bps" in pdf.columns and "pbr" in pdf.columns:
        invalid = pdf["bps"].notna() & (pdf["bps"] <= 0)
        corrected += int((invalid & pdf["pbr"].notna()).sum())
        close = pdf["close"].astype(float)
        valid = pdf["bps"].notna() & (pdf["bps"] > 0)
        pdf["pbr"] = (close / pdf["bps"]).where(valid).replace([np.inf, -np.inf], np.nan)

    if "bps" in pdf.columns and "roe_or_gpa" in pdf.columns:
        bad_equity = pdf["bps"].notna() & (pdf["bps"] <= 0) & pdf["roe_or_gpa"].notna()
        corrected += int(bad_equity.sum())
        pdf.loc[bad_equity, "roe_or_gpa"] = np.nan

    if corrected == 0:
        return "unchanged", 0

    if not dry_run:
        pl.from_pandas(pdf).write_parquet(path)
    return "corrected", corrected


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", help="single 6-digit ticker")
    ap.add_argument("--limit", type=int, help="process at most N parquets")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    if args.symbol:
        paths = [_OHLCV_DIR / f"{args.symbol}.parquet"]
    else:
        paths = sorted(_OHLCV_DIR.glob("*.parquet"))
    if args.limit:
        paths = paths[: args.limit]

    total = len(paths)
    print(f"[fix] {total} parquet(s); dry_run={args.dry_run}")

    tally: dict[str, int] = {}
    total_cells = 0
    for i, path in enumerate(paths, 1):
        if not path.exists():
            print(f"  [{path.stem}] missing parquet")
            tally["missing"] = tally.get("missing", 0) + 1
            continue
        try:
            status, cells = fix_symbol(path, dry_run=args.dry_run)
        except Exception as e:  # noqa: BLE001 — one bad file must not kill the batch
            status, cells = "error", 0
            print(f"  [{path.stem}] error: {e}")
        tally[status] = tally.get(status, 0) + 1
        total_cells += cells
        if status == "corrected" and (i <= 20 or i % 200 == 0):
            print(f"  [{i}/{total}] {path.stem}: corrected {cells} cell(s)")

    print(f"[fix] done: {dict(sorted(tally.items()))} total_cells_corrected={total_cells}")


if __name__ == "__main__":
    main()
