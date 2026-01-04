import polars as pl
import sys
import os

def convert(csv_path, output_parquet):
    # Read CSV
    df = pl.read_csv(csv_path)
    
    # Standardize column names to lowercase
    df.columns = [c.lower() for c in df.columns]
    
    # Rename 'time' to 'date' if it exists
    if 'time' in df.columns:
        df = df.rename({'time': 'date'})
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_parquet), exist_ok=True)
    
    # Write to Parquet
    df.write_parquet(output_parquet)
    print(f"Converted {csv_path} to {output_parquet}")
    print(df.head())

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python convert_to_parquet.py <csv_path> <output_parquet>")
    else:
        convert(sys.argv[1], sys.argv[2])
