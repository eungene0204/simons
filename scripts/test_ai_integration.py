import sys
import os
import json
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.backtest_engine import BacktestEngine

def test_ai_backtest():
    engine = BacktestEngine(data_dir="/Users/eugene/nullalgo/simons/data/ohlcv")
    
    # Strategy using AI Score > 0.6
    req = {
        "symbols": ["005930"], # Samsung Electronics
        "period": "1y",
        'entry': {
            'id': 'group_1',
            'operator': 'or',
            'conditions': [
                {'id': 'ai_model', 'params': {'threshold': 0.05, 'direction': 'above'}}
            ]
        },
        "exit": {
            "logic": "OR",
            "conditions": [
                {
                    "id": "ma_crossover",
                    "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}
                }
            ]
        },
        "risk_params": {
            "stopLoss": 5.0,
            "takeProfit": 10.0,
            "maxHoldingDays": 20
        },
        "options": {
            "initial_cash": 10000000,
            "execution_type": "next_open"
        }
    }
    
    print(f"Starting AI Backtest for {req['symbols']}...")
    try:
        result = engine.run_backtest(req)
        print("Backtest completed successfully!")
        
        # Verify AI score was calculated
        summary = result.get('summary', {})
        total_trades = summary.get('total_trades', 0)
        print(f"Total Trades: {total_trades}")
        
        # Checking trade logs for AI exit reason if triggered
        logs = result.get('trade_logs', [])
        if logs:
            print("Sample Trade Logs:")
            for log in logs[:3]:
                print(f"- Entry: {log['entry_date']}, Exit: {log['exit_date']}, Reason: {log['exit_reason']}")
        
    except Exception as e:
        print(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ai_backtest()
