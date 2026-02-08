import sys
import os
from pathlib import Path

# Add backend to path to import Loader
sys.path.append(str(Path("/Users/eugene/nullalgo/simons/backend")))

from engine.loader import DataLoader

def test_auto_download():
    symbol = "010620" # HD Hyundai Mipo
    data_dir = "/Users/eugene/nullalgo/simons/data/ohlcv"
    target_file = os.path.join(data_dir, f"{symbol}.parquet")
    
    # 1. Ensure file is gone before test (if somehow it appeared)
    if os.path.exists(target_file):
        print(f"Removing existing {target_file} for clean test...")
        os.remove(target_file)
        
    # 2. Try to load data - this should trigger download
    loader = DataLoader(data_dir)
    print(f"Attempting to load {symbol} (this should trigger download)...")
    try:
        df = loader.load_symbol_data(symbol)
        print("Load successful!")
        
        # 3. Check if file exists and has sector
        if os.path.exists(target_file):
            print(f"SUCCESS: File {target_file} was created.")
            import polars as pl
            df_check = pl.read_parquet(target_file)
            if "sector" in df_check.columns:
                sector = df_check["sector"][0]
                print(f"SUCCESS: Sector '{sector}' found in parquet.")
            else:
                print("FAILURE: 'sector' column missing from parquet.")
        else:
            print(f"FAILURE: File {target_file} was NOT created.")
            
    except Exception as e:
        print(f"FAILURE: Error during load: {e}")

if __name__ == "__main__":
    test_auto_download()
