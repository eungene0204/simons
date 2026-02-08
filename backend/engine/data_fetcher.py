import FinanceDataReader as fdr
import pandas as pd
import os
import json
from pathlib import Path
from .sector_mapper import get_sector_from_industry

def fetch_and_enrich(symbol, data_dir):
    """
    Downloads OHLCV data from FDR, maps the sector based on krx-stocks.json,
    and saves as parquet.
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
        base_path = Path("/Users/eugene/nullalgo/simons")
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
            
        # 4. Save to parquet
        target_path = os.path.join(data_dir, f"{symbol}.parquet")
        df.to_parquet(target_path)
        print(f"[INFO] Successfully downloaded and saved {symbol} to {target_path}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch data for {symbol}: {e}")
        return False
