
import polars as pl
import os

data_dir = 'data/ohlcv'
files = [f for f in os.listdir(data_dir) if f.endswith('.parquet')]

print(f"Checking first 10 files in {data_dir}:")
for f in files[:10]:
    df = pl.read_parquet(os.path.join(data_dir, f))
    print(f"{f}: {df['date'].min()}")
