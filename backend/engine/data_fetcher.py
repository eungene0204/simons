import FinanceDataReader as fdr
import pandas as pd
import os
import json
from pathlib import Path
from .sector_mapper import get_sector_from_industry
from .fundamental_fetcher import fetch_fundamentals, enrich_ohlcv_with_fundamentals

def fetch_and_enrich(symbol, data_dir, skip_fundamentals=False):
    """
    Downloads OHLCV data from FDR, maps the sector based on krx-stocks.json,
    enriches with fundamental data (EPS/BPS/PER/PBR), and saves as parquet.
    """
    try:
        # 1. Download data
        # Start from 2000-01-01 to ensure enough history, up to current date (None)
        df = fdr.DataReader(symbol, '2000-01-01')
        if df.empty:
            print(f"[ERROR] FDR returned empty data for {symbol}")
            return False

        df = df.reset_index()
        df.columns = [col.lower() for col in df.columns]

        # 2. Get Sector from krx-stocks.json
        # Resolve project root relative to this file (backend/engine/data_fetcher.py → ../../)
        base_path = Path(__file__).resolve().parent.parent.parent
        stocks_json_path = base_path / "data" / "korea-stocks.json"

        sector = None
        if stocks_json_path.exists():
            with open(stocks_json_path, 'r', encoding='utf-8') as f:
                stocks = json.load(f)
                for s in stocks:
                    if s['symbol'] == symbol:
                        industry = s.get('industry')
                        name = s.get('name', '')
                        sector = get_sector_from_industry(symbol, industry, name)
                        break

        # 3. Add sector column if found
        if sector:
            df["sector"] = sector
            print(f"[INFO] Enriched {symbol} with sector: {sector}")
        else:
            print(f"[WARNING] Could not determine sector for {symbol}")

        # 4. Fundamental enrichment (EPS/BPS → PER/PBR)
        if not skip_fundamentals:
            fundamentals = fetch_fundamentals(symbol)
            if fundamentals:
                df = enrich_ohlcv_with_fundamentals(df, fundamentals)
                print(f"[INFO] Enriched {symbol} with fundamentals: EPS/BPS/PER/PBR")
            else:
                print(f"[WARNING] Could not fetch fundamentals for {symbol}")

        # 5. Save to parquet
        target_path = os.path.join(data_dir, f"{symbol}.parquet")
        df.to_parquet(target_path)
        print(f"[INFO] Successfully downloaded and saved {symbol} to {target_path}")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to fetch data for {symbol}: {e}")
        return False


def enrich_existing_parquet(symbol, data_dir):
    """기존 parquet 파일에 재무 데이터(EPS/BPS/PER/PBR)를 추가한다."""
    target_path = os.path.join(data_dir, f"{symbol}.parquet")
    if not os.path.exists(target_path):
        print(f"[ERROR] Parquet file not found: {target_path}")
        return False

    try:
        df = pd.read_parquet(target_path)
        fundamentals = fetch_fundamentals(symbol)
        if not fundamentals:
            print(f"[WARNING] Could not fetch fundamentals for {symbol}")
            return False

        df = enrich_ohlcv_with_fundamentals(df, fundamentals)
        df.to_parquet(target_path)
        print(f"[INFO] Enriched existing parquet {symbol} with fundamentals")
        return True

    except Exception as e:
        print(f"[ERROR] Failed to enrich {symbol}: {e}")
        return False
