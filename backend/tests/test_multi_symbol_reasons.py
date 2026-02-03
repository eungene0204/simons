import pandas as pd
import polars as pl
import os
from backtest_engine import BacktestEngine

def test_multi_symbol_reasons():
    data_dir = "backend/tests/data"
    os.makedirs(data_dir, exist_ok=True)
    
    def get_prices():
        # Growth for 40 days, then drop
        return [100 + (i*5) for i in range(40)] + [300 - (i*10) for i in range(1, 21)] + [100.0] * 20

    # SYM_A starts Jan 1
    dates_a = pd.date_range(start="2024-01-01", periods=80)
    prices_a = get_prices()
    
    # SYM_B starts Jan 15
    dates_b = pd.date_range(start="2024-01-15", periods=80)
    prices_b = get_prices()
    
    def save_parquet(sym, dates, prices):
        ohlcv = []
        for d, p in zip(dates, prices):
            ohlcv.append({
                "date": d.strftime('%Y-%m-%d'),
                "open": float(p), "high": float(p+1), "low": float(p-1), "close": float(p), "volume": 1000000.0
            })
        pl.from_dicts(ohlcv).write_parquet(f"{data_dir}/{sym}.parquet")

    save_parquet("SYM_A", dates_a, prices_a)
    save_parquet("SYM_B", dates_b, prices_b)
    
    engine = BacktestEngine(data_dir=data_dir)
    
    req = {
        "symbols": ["SYM_A", "SYM_B"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 150, "operator": "=="}}] 
        },
        "exit": {
            "logic": "AND",
            "conditions": [{"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 10, "signalType": "sell"}}]
        },
        "risk": {"position_size_pct": 40, "liquidity_multiplier": 0},
        "options": {"execution_type": "next_open", "fee_rate": 0, "slippage_rate": 0}
    }
    
    result = engine.run_backtest(req)
    
    sell_signals = [s for s in result['signals'] if s['type'] == 'sell']
    print(f"\nDEBUG: Total sell signals: {len(sell_signals)}")
    
    found_a = False
    found_b = False
    for s in sell_signals:
        print(f"DEBUG: Symbol {s['symbol']} Sell at {s['date']} reason: {s['condition']}")
        if "5일선-10일선 데드크로스" in s['condition']:
            if s['symbol'] == "SYM_A": found_a = True
            if s['symbol'] == "SYM_B": found_b = True
            
    assert found_a, "Symbol A specific reason not found"
    assert found_b, "Symbol B specific reason not found"
    print("\n[SUCCESS] Multi-symbol specific reasons verified successfully.")

if __name__ == "__main__":
    test_multi_symbol_reasons()
