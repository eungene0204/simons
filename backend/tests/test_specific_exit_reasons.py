import pandas as pd
import polars as pl
import os
from backtest_engine import BacktestEngine

def test_specific_exit_reasons():
    # Setup test data
    dates = pd.date_range(start="2024-01-01", periods=60)
    # 1. Stability at 100 (Days 0-20)
    # 2. Bull run to 200 (Days 21-30)
    # 3. Crash to 50 (Days 31-40)
    # 4. Stability at 50 (Days 41-59)
    prices = [100] * 21 + [100 + (i*10) for i in range(1, 11)] + [200 - (i*15) for i in range(1, 11)] + [50.0] * 19
    
    df = pd.DataFrame({"date": dates, "close": prices})
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    
    # Find crossover point
    found_cross = -1
    for i in range(1, len(df)):
        if df['ma5'].iloc[i-1] >= df['ma10'].iloc[i-1] and df['ma5'].iloc[i] < df['ma10'].iloc[i]:
            found_cross = i
            print(f"DEBUG: Theoretical dead cross at index {i} ({df['date'].iloc[i]}), MA5={df['ma5'].iloc[i]:.2f}, MA10={df['ma10'].iloc[i]:.2f}")
            break
            
    ohlcv = []
    for i, row in df.iterrows():
        p = row['close']
        ohlcv.append({
            "date": row['date'].strftime('%Y-%m-%d'),
            "open": float(p), "high": float(p+1), "low": float(p-1), "close": float(p), "volume": 1000000.0
        })
        
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    pl.from_dicts(ohlcv).write_parquet(f"{data_dir}/SPECIFIC_EXIT_FINAL_V2.parquet")
    
    engine = BacktestEngine(data_dir=data_dir)
    
    req = {
        "symbols": ["SPECIFIC_EXIT_FINAL_V2"],
        "entry": {
            "logic": "AND",
            # Only buy when price is exactly 100 (which is the first 21 days)
            # This avoids re-entry during the crash at 50.
            "conditions": [{"id": "price", "params": {"value": 90, "operator": ">"}, "params2": {"value": 110, "operator": "<"}}] 
        },
        "exit": {
            "logic": "AND",
            "conditions": [{"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 10, "signalType": "sell"}}]
        },
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0},
        "options": {"execution_type": "next_open", "fee_rate": 0, "slippage_rate": 0}
    }
    
    # Re-using the logic but making it simpler for the engine
    req['entry']['conditions'] = [{"id": "price", "params": {"value": 150, "operator": ">"}}] # Buy only during bull run
    # Bull run starts index 26 (p=150). So entry at 26, execute at 27.
    
    result = engine.run_backtest(req)
    
    sell_signals = [s for s in result['signals'] if s['type'] == 'sell']
    print(f"\nDEBUG: Total tokens: {len(result['signals'])}")
    found_specific = False
    for s in sell_signals:
        print(f"DEBUG: Sell at {s['date']} reason: {s['condition']}")
        if "5일선-10일선 데드크로스" in s['condition']:
            found_specific = True
            
    assert found_specific

if __name__ == "__main__":
    test_specific_exit_reasons()
