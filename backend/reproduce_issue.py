import sys
import os
import json
import pandas as pd
import numpy as np

# Add parent directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.backtest_engine import BacktestEngine

def run_repro():
    engine = BacktestEngine()
    
    # Define a sample request that uses AI and some indicators
    # Using real symbols if available, or mock if not (assuming KOSPI symbols exist in data/ohlcv)
    # Let's try to find a real symbol in the data dir
    data_dir = "backend/data/ohlcv"
    if not os.path.exists(data_dir):
        data_dir = "data/ohlcv"
    
    symbols = []
    if os.path.exists(data_dir):
        files = [f for f in os.listdir(data_dir) if f.endswith('.parquet')]
        symbols = [f.replace('.parquet', '') for f in files[:5]]
    
    if not symbols:
        print("No symbols found in data directory. Please ensure data exists.")
        return

    req = {
        "symbols": symbols,
        "entry": {
            "type": "and",
            "conditions": [
                {"id": "ai_model", "params": {"threshold": 50}},
                {"id": "rsi", "params": {"period": 14, "operator": "<", "value": 70}}
            ]
        },
        "exit": {
            "type": "or",
            "conditions": [
                {"id": "rsi", "params": {"period": 14, "operator": ">", "value": 80}}
            ]
        },
        "risk_params": {
            "init_cash": 10000000,
            "position_size_pct": 20,
            "max_positions": 3,
            "skip_risk_management": False
        },
        "period": "1Y"
    }

    results = []
    for i in range(3):
        print(f"\n--- Run {i+1} ---")
        res = engine.run_backtest(req)
        total_return = res['totalReturn']
        trades = res['trades']
        print(f"Total Return: {total_return}")
        print(f"Total Trades: {trades}")
        results.append(res)

    # Compare returns
    returns = [r['totalReturn'] for r in results]
    if len(set(returns)) == 1:
        print("\n✅ All runs produced the exact same Total Return.")
    else:
        print("\n❌ Non-determinism detected in Total Return!")
        for i, ret in enumerate(returns):
            print(f"Run {i+1}: {ret}")

    # Compare signals
    signals_count = [len(r['signals']) for r in results]
    if len(set(signals_count)) == 1:
        print("✅ Signal counts are identical.")
    else:
        print("❌ Signal counts differ!")

if __name__ == "__main__":
    run_repro()
