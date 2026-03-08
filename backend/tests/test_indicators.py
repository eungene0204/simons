import pytest
import pandas as pd
import polars as pl
from engine.indicators import IndicatorEngine

def test_indicator_index_alignment():
    # Create DataFrame with RangeIndex but specific dates
    df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=30),
        'open': [100.0] * 30,
        'high': [105.0] * 30,
        'low': [95.0] * 30,
        'close': [102.0] * 30,
        'volume': [1000000.0] * 30
    })
    
    # Intentionally do not set index to 'date' here, just like how it comes from loader
    df_pl = pl.from_pandas(df)
    
    conditions = [
        {'id': 'ma_crossover', 'params': {'short': 5, 'long': 20}}
    ]
    
    res_pl = IndicatorEngine.calculate(df_pl, conditions)
    res_df = res_pl.to_pandas()
    
    # Check that moving averages were calculated and are not all NaNs
    assert 'close_5_sma' in res_df.columns
    assert 'close_20_sma' in res_df.columns
    
    # The first 4 rows of 5 SMA will be NaN, but the 5th should have a value
    assert not res_df['close_5_sma'].isna().all(), "close_5_sma is entirely NaN due to index alignment issue"
    assert not res_df['close_20_sma'].isna().all(), "close_20_sma is entirely NaN due to index alignment issue"
    
    # Check specific value
    assert res_df['close_5_sma'].iloc[4] == 102.0
    assert res_df['close_20_sma'].iloc[19] == 102.0
