import os
import sys
import pandas as pd
import polars as pl
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backtest_engine import BacktestEngine

def create_mock_data(symbol, end_date_str, days=500):
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
    dates = [end_date - timedelta(days=i) for i in range(days)]
    dates.sort()
    
    df = pd.DataFrame({
        'date': dates,
        'open': [100.0] * days,
        'high': [110.0] * days,
        'low': [90.0] * days,
        'close': [105.0] * days,
        'volume': [1000] * days,
        'adj_close': [105.0] * days
    })
    
    # Save to mock data directory
    os.makedirs('backend/tests/mock_data', exist_ok=True)
    file_path = f'backend/tests/mock_data/{symbol}.parquet'
    pl.from_pandas(df).write_parquet(file_path)
    return file_path

def test_period_consistency():
    # Setup mock data with different end dates
    # Today is 2026-02-11
    create_mock_data('SYM_NEW', '2026-02-11')
    create_mock_data('SYM_OLD', '2025-06-01') # Finished 8 months ago
    
    engine = BacktestEngine(data_dir='backend/tests/mock_data')
    
    req = {
        'symbols': ['SYM_NEW', 'SYM_OLD'],
        'period': '1Y',
        'entry': {'logic': 'AND', 'conditions': []},
        'exit': {'logic': 'OR', 'conditions': []},
        'risk': {'init_cash': 10000000, 'position_size_pct': 10, 'max_positions': 10},
        'options': {'execution_type': 'next_open'}
    }
    
    print("Running backtest with 1Y period...")
    result = engine.run_backtest(req)
    
    dates = result['dates']
    min_date = dates[0]
    max_date = dates[-1]
    
    print(f"Result dates: {min_date} to {max_date}")
    
    # Yesterday or today (depending on today's normalize output)
    today = pd.to_datetime('today').normalize()
    one_year_ago = today - pd.DateOffset(years=1)
    
    expected_start = one_year_ago.strftime('%Y-%m-%d')
    expected_end = today.strftime('%Y-%m-%d')
    
    print(f"Expected range around: {expected_start} to {expected_end}")
    
    # Verify that the min_date is not too far in the past (it should be roughly 1 year ago from today)
    # The old symbol finished in 2025-06-01. Previously, it would have used 2025-06-01 as ref_date and gone back to 2024-06-01.
    # Now it should use today (2026-02-11) as ref_date for both.
    
    if min_date < expected_start:
        print(f"FAILURE: Start date {min_date} is before expected {expected_start}")
    else:
        print("SUCCESS: Start date is consistent with global ref_date.")

if __name__ == "__main__":
    try:
        test_period_consistency()
    finally:
        # Cleanup
        import shutil
        if os.path.exists('backend/tests/mock_data'):
            shutil.rmtree('backend/tests/mock_data')
