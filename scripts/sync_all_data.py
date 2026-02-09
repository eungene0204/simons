import json
import os
import sys
from pathlib import Path
from tqdm import tqdm

# Add backend to path for data_fetcher
sys.path.append(os.path.join(os.getcwd(), "backend"))
from engine.data_fetcher import fetch_and_enrich

def main():
    base_dir = Path("/Users/eugene/nullalgo/simons")
    stocks_path = base_dir / "data" / "korea-stocks.json"
    data_dir = base_dir / "data" / "ohlcv"
    
    if not data_dir.exists():
        data_dir.mkdir(parents=True)
        
    print(f"Loading {stocks_path}...")
    with open(stocks_path, "r", encoding="utf-8") as f:
        stocks = json.load(f)
        
    missing_stocks = []
    for s in stocks:
        symbol = s['symbol']
        file_path = data_dir / f"{symbol}.parquet"
        if not file_path.exists():
            missing_stocks.append(s)
            
    print(f"Found {len(missing_stocks)} stocks missing price data.")
    
    if not missing_stocks:
        print("All stocks are already synchronized.")
        return

    success_count = 0
    fail_count = 0
    
    for s in tqdm(missing_stocks, desc="Syncing data"):
        symbol = s['symbol']
        name = s.get('name', '?')
        # print(f"Syncing {name} ({symbol})...")
        if fetch_and_enrich(symbol, str(data_dir)):
            success_count += 1
        else:
            fail_count += 1
            
    print(f"\nSync complete!")
    print(f"Successfully synced: {success_count}")
    print(f"Failed to sync: {fail_count}")

if __name__ == "__main__":
    main()
