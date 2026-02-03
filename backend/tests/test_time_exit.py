import pandas as pd
import polars as pl
import os
from backtest_engine import BacktestEngine

def test_time_based_exit_reasons():
    # Setup test data
    dates = pd.date_range(start="2024-01-01", periods=30)
    prices = [100.0] * 30
    
    ohlcv = []
    for d, p in zip(dates, prices):
        ohlcv.append({
            "date": d.strftime('%Y-%m-%d'),
            "open": float(p), "high": float(p+1), "low": float(p-1), "close": float(p), "volume": 1000000.0
        })
        
    data_dir = "backend/tests/data"
    os.makedirs(data_dir, exist_ok=True)
    pl.from_dicts(ohlcv).write_parquet(f"{data_dir}/TIME_EXIT_TEST_V2.parquet")
    
    engine = BacktestEngine(data_dir=data_dir)
    
    # Strategy: Buy ONLY ON THE FIRST DAY
    req = {
        "symbols": ["TIME_EXIT_TEST_V2"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 101, "operator": "<"}, "date": "2024-01-01"}] # Try to limit entry
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {
            "position_size_pct": 100, 
            "max_holding_days": 5,
            "liquidity_multiplier": 0
        },
        "options": {"execution_type": "same_close"}
    }
    
    # Force single entry by adjusting conditions more aggressively
    req['entry']['conditions'] = [{"id": "price", "params": {"value": 0, "operator": "=="}}] # Will fail
    # Use a trick: only the first day has price 100, others 110
    prices = [100.0] + [110.0] * 29
    ohlcv = []
    for d, p in zip(dates, prices):
        ohlcv.append({
            "date": d.strftime('%Y-%m-%d'),
            "open": float(p), "high": float(p+1), "low": float(p-1), "close": float(p), "volume": 1000000.0
        })
    pl.from_dicts(ohlcv).write_parquet(f"{data_dir}/TIME_EXIT_TEST_V2.parquet")
    
    req['entry']['conditions'] = [{"id": "price", "params": {"value": 105, "operator": "<"}}] # Only day 1
    
    result = engine.run_backtest(req)
    
    sell_signals = [s for s in result['signals'] if s['type'] == 'sell']
    print(f"\nDEBUG: Total sell signals: {len(sell_signals)}")
    
    found_time_exit = False
    for s in sell_signals:
        print(f"DEBUG: Sell reason: {s['condition']}")
        if "보유 기간 만료 (5일 보유)" in s['condition']:
            found_time_exit = True
            print("[SUCCESS] Found specific 5-day time exit.")
            
    assert found_time_exit

if __name__ == "__main__":
    test_time_based_exit_reasons()
