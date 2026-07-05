#!/usr/bin/env python3
"""
백필: 전 종목의 정확한 섹터 데이터를 parquet에 기록한다 (source of truth).

소스 우선순위:
  1. engine/sector_mapper.OVERRIDDEN_SYMBOLS (수작업 확정 매핑)
  2. data/korea-stocks.json의 industry(KRX KIND 공식 업종) → get_sector_from_industry()
  3. industry 정보가 없는 종목(상장폐지 등)은 종목명 키워드만으로 매핑

data/ohlcv/*.parquet의 sector 컬럼 전체를 최신 분류 로직으로 다시 기록한다.
(data_fetcher.fetch_and_enrich()가 신규 종목에 sector를 채우는 것과 동일한 로직을 재사용)

용법:
  python scripts/backfill_sector_data.py
"""

import json
import sys
from pathlib import Path
from collections import Counter

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OHLCV_DIR = DATA_DIR / "ohlcv"
STOCK_MASTER_FILE = DATA_DIR / "stock-master.json"
KOREA_STOCKS_FILE = DATA_DIR / "korea-stocks.json"

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from engine.sector_mapper import get_sector_from_industry


def _load_industry_lookup() -> dict[str, dict]:
    """korea-stocks.json에서 symbol -> {industry, name, sector} 조회 테이블 생성"""
    with open(KOREA_STOCKS_FILE, encoding="utf-8") as f:
        stocks = json.load(f)
    return {s["symbol"]: s for s in stocks}


def _load_all_symbols() -> dict[str, str]:
    """stock-master.json에서 전 종목 symbol -> name 조회 테이블 생성"""
    with open(STOCK_MASTER_FILE, encoding="utf-8") as f:
        master = json.load(f)
    return {s["symbol"]: s["name"] for s in master["stocks"]}


def main() -> None:
    all_symbols = _load_all_symbols()
    industry_lookup = _load_industry_lookup()

    print(f"전체 종목: {len(all_symbols)}개, korea-stocks.json 등재(업종 데이터 있음): {len(industry_lookup)}개\n")

    sector_counts: Counter[str] = Counter()
    updated = 0
    missing_parquet = 0

    for symbol, name in all_symbols.items():
        ref = industry_lookup.get(symbol)
        industry = ref["industry"] if ref else None
        sector = get_sector_from_industry(symbol, industry, name)

        parquet_path = OHLCV_DIR / f"{symbol}.parquet"
        if not parquet_path.exists():
            missing_parquet += 1
            continue

        df = pd.read_parquet(parquet_path)
        df["sector"] = sector
        df.to_parquet(parquet_path, index=False)

        sector_counts[sector] += 1
        updated += 1

    print(f"✅ parquet 업데이트: {updated}개 (parquet 없음: {missing_parquet}개)\n")
    print("섹터별 분포:")
    for sector, cnt in sector_counts.most_common():
        print(f"  {sector:20s} {cnt:5d}")


if __name__ == "__main__":
    main()
