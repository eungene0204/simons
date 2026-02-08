import pandas as pd
import json
from pathlib import Path

def verify():
    base_dir = Path("/Users/eugene/nullalgo/simons")
    stocks_path = base_dir / "data" / "korea-stocks.json"
    ohlcv_dir = base_dir / "data" / "ohlcv"
    
    # Check JSON
    print("Checking korea-stocks.json...")
    with open(stocks_path, "r", encoding="utf-8") as f:
        stocks = json.load(f)
    
    mapped = [s for s in stocks if s.get("sector") is not None]
    print(f"JSON: {len(mapped)} / {len(stocks)} stocks have sectors.")
    
    # Check a few Parquet files
    print("\nChecking sample Parquet files...")
    samples = ["005930", "000660", "373220", "207940", "005380"] # Samsung, Hynix, Energy, Bio, Auto
    for sym in samples:
        file_path = ohlcv_dir / f"{sym}.parquet"
        if file_path.exists():
            df = pd.read_parquet(file_path)
            sector = df["sector"].iloc[0] if "sector" in df.columns else "MISSING"
            print(f"  {sym}: {sector}")
        else:
            print(f"  {sym}: File not found")

if __name__ == "__main__":
    verify()
