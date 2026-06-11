import pandas as pd
import numpy as np
import os
import polars as pl
from backtest_engine import BacktestEngine

def test_signal_mapping_robustness():
    # 1. Create data with timezone awareness
    dates = pd.date_range(start="2024-01-01", periods=60, tz='UTC')
    prices = [100 + i for i in range(30)] + [150 - i for i in range(1, 31)]
    
    ohlcv = []
    for d, p in zip(dates, prices):
        ohlcv.append({
            "date": d.strftime('%Y-%m-%d'), # Use string to avoid arrow conversion issues
            "open": float(p), "high": float(p+1), "low": float(p-1), "close": float(p), "volume": 1000000.0
        })
        
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    df_pl = pl.from_dicts(ohlcv)
    # Note: Polars might strip TZ when writing to Parquet depending on version
    df_pl.write_parquet(f"{data_dir}/TZ_ROBUST_TEST.parquet")
    
    engine = BacktestEngine(data_dir=data_dir)
    
    # 2. Run backtest with MA cross
    req = {
        "symbols": ["TZ_ROBUST_TEST"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 50, "operator": ">"}}]
        },
        "exit": {
            "logic": "AND",
            "conditions": [{"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 10, "signalType": "sell"}}]
        },
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0},
        "options": {"execution_type": "next_open"}
    }
    
    result = engine.run_backtest(req)
    
    sell_signals = [s for s in result['signals'] if s['type'] == 'sell']
    print(f"\nDEBUG: Total sell signals: {len(sell_signals)}")
    
    for s in sell_signals:
        print(f"DEBUG: Symbol {s['symbol']} at {s['date']} reason: {s['condition']}")
        if "전략 청산 시그널" in s['condition']:
            print(f"[FAIL] Found generic signal instead of specific one at {s['date']}")
        elif "5일선-10일선 데드크로스" in s['condition']:
            print(f"[SUCCESS] Specific reason found at {s['date']}")

if __name__ == "__main__":
    test_signal_mapping_robustness()
