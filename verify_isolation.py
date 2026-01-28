import pandas as pd
import polars as pl
import os
import sys

# Add backend dir for imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine.loader import DataLoader
from engine.indicators import IndicatorEngine
from engine.signals import SignalEngine

def test_isolation():
    data_dir = "data/ohlcv"
    loader = DataLoader(data_dir)
    indicators = IndicatorEngine()
    signals = SignalEngine()
    
    symbols = ["005930", "000660"]
    results = {}
    
    all_conds = [{'id': 'ma_crossover', 'params': {'short': 5, 'long': 20, 'signalType': 'buy'}}]
    
    print("--- Isolation Test Start ---")
    for sym in symbols:
        df_pl = loader.load_symbol_data(sym)
        # Check raw price
        raw_close = df_pl['close'][:5].to_list()
        print(f"Symbol {sym} raw close (head): {raw_close}")
        
        # Calculate indicators
        df_pl_ind = indicators.calculate(df_pl, all_conds)
        sma5 = df_pl_ind['close_5_sma'][:10].to_list()
        print(f"Symbol {sym} SMA5 (head): {sma5}")
        
        # Evaluate signals
        entries = []
        for i in range(len(df_pl_ind)):
            can_enter, _ = signals.evaluate_group({'conditions': all_conds, 'logic': 'AND'}, i, df_pl_ind)
            if can_enter: entries.append(i)
        
        print(f"Symbol {sym} signal indices: {entries[:5]}")
        results[sym] = {
            'raw': raw_close,
            'sma': sma5,
            'entries': entries
        }
    
    # Final Comparison
    if results["005930"]['raw'] == results["000660"]['raw']:
        print("ERROR: Raw prices are IDENTICAL!")
    else:
        print("SUCCESS: Raw prices are DIFFERENT.")
        
    if results["005930"]['sma'] == results["000660"]['sma']:
        print("ERROR: Computed indicators are IDENTICAL!")
    else:
        print("SUCCESS: Computed indicators are DIFFERENT.")

    if results["005930"]['entries'] == results["000660"]['entries']:
         print("ERROR: Signal indices are IDENTICAL!")
    else:
         print("SUCCESS: Signal indices are DIFFERENT.")

if __name__ == "__main__":
    test_isolation()
