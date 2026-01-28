import pandas as pd
import sys
import os
import numpy as np

# Add backend dir for imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backtest_engine import BacktestEngine

def check_signal_uniqueness():
    engine = BacktestEngine()
    symbols = ["005930", "000660", "000100", "000150"] # Diverse symbols
    
    req = {
        'symbols': symbols,
        'entry': {
            'conditions': [{'id': 'ma_crossover', 'params': {'short': 5, 'long': 20, 'signalType': 'buy'}}],
            'logic': 'AND'
        },
        'exit': {
            'conditions': [{'id': 'ma_crossover', 'params': {'short': 5, 'long': 20, 'signalType': 'sell'}}],
            'logic': 'AND'
        },
        'risk': {'init_cash': 10000000},
        'options': {'execution_type': 'next_open'}
    }
    
    print("Running backtest to check signal uniqueness...")
    
    # We need to peek into the engine's internal state if possible, or just look at the results.
    # But wait, I'll just look at the signals_list per symbol.
    result = engine.run_backtest(req)
    signals = result.get('signals', [])
    
    symbol_data = {}
    for sym in symbols:
        sym_signals = [s for s in signals if s['symbol'] == sym and s['type'] == 'buy']
        dates = sorted([s['date'] for s in sym_signals])
        symbol_data[sym] = dates
        print(f"Symbol {sym}: {len(dates)} buy signals.")

    # Compare pairs
    from itertools import combinations
    for s1, s2 in combinations(symbols, 2):
        d1 = set(symbol_data[s1])
        d2 = set(symbol_data[s2])
        overlap = d1.intersection(d2)
        jaccard = len(overlap) / len(d1.union(d2)) if len(d1.union(d2)) > 0 else 0
        print(f"Overlap between {s1} and {s2}: {len(overlap)} / {len(d1)} / {len(d2)} (Jaccard: {jaccard:.2f})")
        
        if jaccard > 0.9:
            print(f"WARNING: Symbol {s1} and {s2} have almost identical buy dates!")

if __name__ == "__main__":
    check_signal_uniqueness()
