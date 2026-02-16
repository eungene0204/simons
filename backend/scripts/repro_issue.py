
import os
import sys
from typing import Dict, Any

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backtest_engine import BacktestEngine

def test_identical_reasons():
    engine = BacktestEngine()
    
    # Request for 50 symbols
    import os
    data_dir = 'data/ohlcv'
    symbols = [f.split('.')[0] for f in os.listdir(data_dir) if f.endswith('.parquet')][:50]
    
    req = {
        "symbols": symbols,
        "period": "1Y",
        "entry": {
            "logic": "AND",
            "conditions": [
                {
                    "id": "ma_crossover",
                    "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}
                }
            ]
        },
        "exit": {
            "logic": "AND",
            "conditions": [
                {
                    "id": "ma_crossover",
                    "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}
                }
            ]
        },
        "risk": {
            "init_cash": 10000000,
            "position_size_pct": 100
        },
        "options": {
            "execution_type": "next_open",
            "fee_rate": 0.0015,
            "slippage_rate": 0.002
        }
    }
    
    print("Running backtest...")
    result = engine.run_backtest(req)
    
    signals = result.get('signals', [])
    print(f"Total signals: {len(signals)}")
    
    # Check for identical dates across DIFFERENT symbols
    date_to_symbols = {}
    for s in signals:
        if s['type'] == 'buy':
            dt = s['date']
            sym = s['symbol']
            if dt not in date_to_symbols: date_to_symbols[dt] = set()
            date_to_symbols[dt].add(sym)
            
    overlapping_dates = {dt: syms for dt, syms in date_to_symbols.items() if len(syms) > 1}
    print(f"Number of dates where >1 symbol bought: {len(overlapping_dates)}")
    for dt in sorted(overlapping_dates.keys())[:10]:
        print(f"  {dt}: {sorted(list(overlapping_dates[dt]))}")
        
    # Check if for any symbol, the buy reason is always the same
    symbol_reasons = {}
    for s in signals:
        if s['type'] == 'buy':
            sym = s['symbol']
            reason = s['condition']
            if sym not in symbol_reasons: symbol_reasons[sym] = set()
            symbol_reasons[sym].add(reason)
            
    for sym, reasons in symbol_reasons.items():
        print(f"Symbol {sym} has {len(reasons)} unique reasons: {reasons}")
    
if __name__ == "__main__":
    test_identical_reasons()
