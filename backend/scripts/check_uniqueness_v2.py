import pandas as pd
import sys
import os
import numpy as np

# Add backend dir for imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backtest_engine import BacktestEngine

def check_signal_uniqueness():
    engine = BacktestEngine()
    # Use symbols that are likely to have good data
    symbols = ["005930", "000660", "035420", "035720"] # Samsung, Hynix, Naver, Kakao
    
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
        'period': '1Y',
        'options': {'execution_type': 'next_open'}
    }
    
    print("Running backtest with verified symbols...")
    try:
        result = engine.run_backtest(req)
        signals = result.get('signals', [])
        
        buy_signals = [s for s in signals if s['type'] == 'buy']
        print(f"Total Buy Signals across all: {len(buy_signals)}")
        
        symbol_data = {}
        for sym in symbols:
            sym_buys = [s for s in buy_signals if s['symbol'] == sym]
            dates = [s['date'] for s in sym_buys]
            symbol_data[sym] = dates
            print(f"Symbol {sym}: {len(dates)} buys. First 3: {dates[:3]}")

        # Check for exact date duplicates across symbols at index level
        for i in range(min(5, len(buy_signals))):
            s = buy_signals[i]
            print(f"Signal {i}: {s['symbol']} on {s['date']}")

    except Exception as e:
        print(f"Failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_signal_uniqueness()
