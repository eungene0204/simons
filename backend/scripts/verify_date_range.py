import polars as pl
import pandas as pd
from datetime import datetime

def test_date_range():
    # Mock data up to 2024-12-30
    dates = pd.date_range(start="2010-01-01", end="2024-12-30", freq="D")
    df_pl = pl.DataFrame({"date": dates})
    
    last_date = df_pl['date'].max()
    ref_date = last_date if isinstance(last_date, datetime) else pd.to_datetime(last_date)
    
    print(f"Reference Date: {ref_date}")
    
    # Test 5Y
    df_5y = df_pl.filter(pl.col("date") >= pd.Timestamp(year=ref_date.year - 4, month=1, day=1))
    print(f"5Y Start: {df_5y['date'].min()}")
    print(f"5Y End: {df_5y['date'].max()}")
    
    # Test 1Y (rolling)
    df_1y = df_pl.filter(pl.col("date") >= (ref_date - pd.DateOffset(years=1)))
    print(f"1Y Start: {df_1y['date'].min()}")
    print(f"1Y End: {df_1y['date'].max()}")

if __name__ == "__main__":
    test_date_range()
