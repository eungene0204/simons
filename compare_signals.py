import pandas as pd
import sys
import os
import numpy as np

# Add backend dir for imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backtest_engine import BacktestEngine

def compare_signal_bitmasks():
    engine = BacktestEngine()
    # diverse symbols
    symbols = ["005930", "000660", "035420", "035720", "005380"]
    
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
        'period': '1Y'
    }
    
    print("Comparing Signal Bitmasks...")
    result = engine.run_backtest(req)
    signals = result.get('signals', [])
    
    # Organize by symbol
    sim_data = {}
    for sym in symbols:
        sym_signals = [s for s in signals if s['symbol'] == sym and s['type'] == 'buy']
        dates = [s['date'] for s in sym_signals]
        sim_data[sym] = dates
        print(f"Symbol {sym} has {len(dates)} buys.")

    # Check for identical lists
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            if sim_data[s1] == sim_data[s2] and len(sim_data[s1]) > 0:
                print(f"!!! CRITICAL: Symbol {s1} and {s2} have IDENTICAL signal lists!")
            else:
                print(f"Symbol {s1} and {s2} are distinct.")

if __name__ == "__main__":
    compare_signal_bitmasks()
