import sys
import os
import pandas as pd
import numpy as np

# Add current directory to path
sys.path.append(os.getcwd())

from backtest_engine import BacktestEngine

def debug_metrics():
    engine = BacktestEngine(data_dir="../data/ohlcv")
    
    # Simple strategy on Samsung
    req = {
        "symbol": "005930",
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "indicator", "id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}}
            ]
        },
        "exit": {
            "logic": "AND",
            "conditions": [
                {"type": "indicator", "id": "rsi", "params": {"period": 14, "value": 70, "operator": ">"}}
            ]
        },
        "risk": {
            "position_size_pct": 100
        }
    }
    
    print("Running backtest for Samsung (005930)...")
    result = engine.run_backtest(req)
    
    print("\n--- Extracted Metrics ---")
    print(f"Total Return: {result['totalReturn']}")
    print(f"CAGR: {result['cagr']}")
    print(f"Max Drawdown: {result['maxDrawdown']}")
    print(f"Sharpe: {result['sharpe']}")
    print(f"Win Rate: {result['winRate']}")
    print(f"Trades Count: {len(result['signals'])}")
    
    # Check if dates have proper format
    print(f"\nFirst 5 dates: {result['dates'][:5]}")

if __name__ == "__main__":
    debug_metrics()
