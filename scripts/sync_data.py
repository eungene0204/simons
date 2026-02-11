import os
import sys
import json
import pandas as pd
import polars as pl
import FinanceDataReader as fdr
from tqdm import tqdm
from pathlib import Path
from datetime import datetime

# Add root and backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.engine.data_fetcher import fetch_and_enrich
from backend.engine.sector_mapper import get_sector_from_industry

def sync_symbols(stocks_path):
    """Fetch latest KOSPI/KOSDAQ symbols and update korea-stocks.json."""
    print("Fetching latest stock listings from KRX...")
    try:
        # Fetch KOSPI and KOSDAQ
        kospi = fdr.StockListing('KOSPI')
        kosdaq = fdr.StockListing('KOSDAQ')
        
        # Merge and format
        all_stocks = pd.concat([kospi, kosdaq])
        all_stocks = all_stocks[['Code', 'Name', 'Market', 'Industry']]
        all_stocks.columns = ['symbol', 'name', 'market', 'industry']
        
        new_list = []
        for _, row in all_stocks.iterrows():
            symbol = row['symbol']
            industry = row['industry']
            name = row['name']
            
            # Map sector using existing logic
            sector = get_sector_from_industry(symbol, industry, name)
            
            new_list.append({
                'symbol': symbol,
                'name': name,
                'market': row['market'],
                'sector': sector,
                'industry': industry
            })
            
        # Compare with existing
        existing_stocks = []
        if os.path.exists(stocks_path):
            with open(stocks_path, 'r', encoding='utf-8') as f:
                existing_stocks = json.load(f)
        
        existing_symbols = {s['symbol'] for s in existing_stocks}
        new_symbols_found = [s for s in new_list if s['symbol'] not in existing_symbols]
        
        if new_symbols_found:
            print(f"Found {len(new_symbols_found)} new symbols!")
            for ns in new_symbols_found[:5]:
                print(f"  - {ns['name']} ({ns['symbol']})")
            if len(new_symbols_found) > 5:
                print("  ...")
        
        # Save updated list
        with open(stocks_path, 'w', encoding='utf-8') as f:
            json.dump(new_list, f, ensure_ascii=False, indent=2)
        
        print(f"Updated {stocks_path} with {len(new_list)} symbols.")
        return new_list, new_symbols_found
        
    except Exception as e:
        print(f"Error syncing symbols: {e}")
        return [], []

def update_ohlcv_incremental(symbol, data_dir):
    """Update parquet file with latest data if exists, else full download."""
    file_path = os.path.join(data_dir, f"{symbol}.parquet")
    
    if not os.path.exists(file_path):
        return fetch_and_enrich(symbol, data_dir)
        
    try:
        # Load existing
        df_old = pl.read_parquet(file_path)
        last_date = df_old['date'].max()
        if isinstance(last_date, str):
            last_date = datetime.strptime(last_date, '%Y-%m-%d')
        
        # Fetch new data since last date
        start_date_str = last_date.strftime('%Y-%m-%d')
        df_new_pd = fdr.DataReader(symbol, start_date_str)
        
        if df_new_pd.empty:
            return True # Already up to date
            
        # Convert new data to Polars
        df_new_pd = df_new_pd.reset_index()
        df_new_pd.columns = [col.lower() for col in df_new_pd.columns]
        
        # Cast columns to match typical schema
        # OHLC typically float, Volume typically int or float
        float_cols = ['open', 'high', 'low', 'close', 'adj close', 'change']
        for col in float_cols:
            if col in df_new_pd.columns:
                df_new_pd[col] = df_new_pd[col].astype(float)
        
        df_new = pl.from_pandas(df_new_pd)
        if 'date' in df_new.columns:
            df_new = df_new.with_columns(pl.col('date').cast(pl.Datetime))
        
        # Ensure df_old types match
        df_old = df_old.with_columns([
            pl.col(c).cast(pl.Float64) for c in float_cols if c in df_old.columns
        ])
        if 'volume' in df_old.columns:
            df_old = df_old.with_columns(pl.col('volume').cast(pl.Float64))
        if 'volume' in df_new.columns:
            df_new = df_new.with_columns(pl.col('volume').cast(pl.Float64))

        # Combine
        df_combined = pl.concat([df_old, df_new]).unique(subset=['date'], keep='last').sort('date')
        
        # Re-save
        df_combined.write_parquet(file_path)
        return True
    except Exception as e:
        print(f"[WARNING] Failed to update {symbol} incrementally: {e}")
        print(f"[INFO] Attempting full re-download for {symbol}...")
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return fetch_and_enrich(symbol, data_dir)
        except Exception as e2:
            print(f"[ERROR] Full re-download failed for {symbol}: {e2}")
            return False

def main():
    base_dir = Path(os.getcwd())
    stocks_path = base_dir / "data" / "korea-stocks.json"
    data_dir = base_dir / "data" / "ohlcv"
    
    if not data_dir.exists():
        data_dir.mkdir(parents=True)
        
    # 1. Sync Symbols
    stocks, new_symbols = sync_symbols(str(stocks_path))
    
    if not stocks:
        print("[WARNING] Symbol sync failed. Falling back to existing korea-stocks.json...")
        if stocks_path.exists():
            with open(stocks_path, 'r', encoding='utf-8') as f:
                stocks = json.load(f)
            new_symbols = []
        else:
            print("[ERROR] No existing stock list found. Aborting.")
            return

    # 2. Sync OHLCV
    print(f"Starting OHLCV synchronization for {len(stocks)} symbols...")
    success_count = 0
    fail_count = 0
    
    # We use a progress bar for OHLCV
    for s in tqdm(stocks, desc="Updating OHLCV"):
        symbol = s['symbol']
        if update_ohlcv_incremental(symbol, str(data_dir)):
            success_count += 1
        else:
            fail_count += 1
            
    print(f"\nFinal Summary:")
    print(f"- Total Stocks: {len(stocks)}")
    print(f"- New symbols added: {len(new_symbols)}")
    print(f"- OHLCV Update Success: {success_count}")
    print(f"- OHLCV Update Failure: {fail_count}")

if __name__ == "__main__":
    main()
