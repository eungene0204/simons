import os
import pytest
import polars as pl
import pandas as pd
import numpy as np
from engine.loader import DataLoader

@pytest.fixture
def loader():
    return DataLoader(data_dir=os.path.join(os.path.dirname(__file__), "data"))

def test_preprocess_data_adj_close(loader):
    # Test if adj_close is correctly applied to OHLC
    data = {
        "date": pd.date_range("2024-01-01", periods=3),
        "open": [100.0, 100.0, 100.0],
        "high": [110.0, 110.0, 110.0],
        "low": [90.0, 90.0, 90.0],
        "close": [100.0, 100.0, 100.0],
        "adj_close": [50.0, 100.0, 200.0], # 0.5x, 1x, 2x
        "volume": [1000, 1000, 1000]
    }
    df_pl = pl.DataFrame(data)
    
    pdf = loader.preprocess_data(df_pl)
    
    assert pdf.iloc[0]['open'] == 50.0
    assert pdf.iloc[0]['high'] == 55.0
    assert pdf.iloc[0]['low'] == 45.0
    assert pdf.iloc[0]['close'] == 50.0

    assert pdf.iloc[1]['open'] == 100.0
    assert pdf.iloc[2]['high'] == 220.0
    assert pdf.iloc[2]['close'] == 200.0

def test_preprocess_data_fill_nan(loader):
    # Test if NaN or 0 prices are correctly ffill/bfilled
    data = {
        "date": pd.date_range("2024-01-01", periods=3),
        "open": [np.nan, 100.0, 0.0],
        "high": [110.0, np.nan, 110.0],
        "low": [0.0, 90.0, np.nan],
        "close": [100.0, 0.0, 120.0],
        "volume": [1000, 1000, 1000]
    }
    df_pl = pl.DataFrame(data)
    
    pdf = loader.preprocess_data(df_pl)
    
    # open: leading nan uses the same bar's close; trailing 0 uses the prior valid open.
    assert pdf.iloc[0]['open'] == 100.0
    assert pdf.iloc[2]['open'] == 100.0
    
    # close: 100, 0, 120 -> 100, 100 (ffill from 100), 120
    assert pdf.iloc[0]['close'] == 100.0
    assert pdf.iloc[1]['close'] == 100.0
    assert pdf.iloc[2]['close'] == 120.0


def test_preprocess_data_does_not_backfill_leading_prices_from_future(loader):
    """Leading invalid bars must stay unavailable instead of borrowing future prices."""
    data = {
        "date": pd.date_range("2024-01-01", periods=3),
        "open": [np.nan, 110.0, 120.0],
        "high": [np.nan, 115.0, 125.0],
        "low": [np.nan, 105.0, 115.0],
        "close": [np.nan, 110.0, 120.0],
        "volume": [0, 1000, 1000],
    }

    pdf = loader.preprocess_data(pl.DataFrame(data))

    assert pdf.iloc[0][["open", "high", "low", "close"]].isna().all()

def test_check_liquidity(loader):
    data = {
        "date": pd.date_range("2024-01-01", periods=4),
        "close": [100.0, 100.0, 100.0, 100.0],
        "volume": [100, 1000, 10, 500] 
        # Trading values: 10_000, 100_000, 1_000, 50_000
    }
    pdf = pd.DataFrame(data).set_index("date")
    
    # Target amount: 50,000, Limit pct: 100%
    # This means yesterday's trading value must be >= 50,000 to trade today.
    # Day 0: false (no yesterday)
    # Day 1: yesterday was 10_000 -> false
    # Day 2: yesterday was 100_000 -> true
    # Day 3: yesterday was 1_000 -> false
    liquidity_ok = loader.check_liquidity(pdf, target_amount=50000.0, limit_pct=100.0)
    
    assert list(liquidity_ok) == [False, False, True, False]

def test_check_liquidity_no_limit(loader):
    data = {
        "date": pd.date_range("2024-01-01", periods=2),
        "close": [100.0, 100.0],
        "volume": [100, 10] 
    }
    pdf = pd.DataFrame(data).set_index("date")
    
    liquidity_ok = loader.check_liquidity(pdf, target_amount=50000.0, limit_pct=0.0)
    
    assert list(liquidity_ok) == [True, True]
