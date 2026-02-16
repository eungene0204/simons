import pandas as pd
import sys
import os

# Add backend dir for imports
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backtest_engine import BacktestEngine

def test_multiple_reasons():
    engine = BacktestEngine()
    
    # Symbols: Samsung (005930), SK Hynix (000660)
    symbols = ["005930", "000660"]
    
    # Strategy with TWO conditions (OR logic)
    # 1. 5/20 Golden Cross
    # 2. RSI < 40 (Lower than usual to get some hits)
    req = {
        'symbols': symbols,
        'entry': {
            'conditions': [
                {'id': 'ma_crossover', 'params': {'short': 5, 'long': 20, 'signalType': 'buy'}},
                {'id': 'rsi', 'params': {'period': 14, 'operator': '<', 'value': 40}}
            ],
            'logic': 'OR'
        },
        'exit': {
            'conditions': [{'id': 'ma_crossover', 'params': {'short': 5, 'long': 20, 'signalType': 'sell'}}],
            'logic': 'AND'
        },
        'risk': {'init_cash': 10000000, 'position_size_pct': 50},
        'period': '1Y', # Last 1 year for speed
        'options': {'execution_type': 'next_open'}
    }
    
    print("Running backtest with Multiple OR conditions...")
    result = engine.run_backtest(req)
    
    signals = result.get('signals', [])
    buy_signals = [s for s in signals if s['type'] == 'buy']
    
    print(f"\nTotal Buy Signals: {len(buy_signals)}")
    
    # Analysis per symbol
    for sym in symbols:
        sym_buys = [s for s in buy_signals if s['symbol'] == sym]
        reasons = set(s['condition'] for s in sym_buys)
        print(f"\n--- Symbol: {sym} ---")
        print(f"Number of Buys: {len(sym_buys)}")
        print(f"Unique Reasons: {reasons}")
        if sym_buys:
            print(f"Sample Buy: Date={sym_buys[0]['date']}, Reason={sym_buys[0]['condition']}")

if __name__ == "__main__":
    test_multiple_reasons()
