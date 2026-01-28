
import vectorbt as vbt
import pandas as pd
import numpy as np

def test_vbt_multi_column():
    index = pd.date_range("2024-01-01", periods=10)
    data = {
        'A': [10, 11, 12, 11, 10, 9, 10, 11, 12, 13]
    }
    price_df = pd.DataFrame(data, index=index)
    
    entries = pd.DataFrame({
        'A': [False, True, False, False, False, False, False, False, False, False]
    }, index=index)
    
    exits = pd.DataFrame({
        'A': [False, False, False, True, False, False, False, False, False, False]
    }, index=index)
    
    pf = vbt.Portfolio.from_signals(price_df, entries, exits, init_cash=1000)
    
    print("\nTrades records_readable values:")
    print(pf.trades.records_readable[['Column', 'Entry Timestamp', 'Exit Timestamp']])
    print(type(pf.trades.records_readable['Entry Timestamp'].iloc[0]))
    
    print("\nRaw records columns:")
    print(pf.trades.records.columns)

if __name__ == "__main__":
    test_vbt_multi_column()
