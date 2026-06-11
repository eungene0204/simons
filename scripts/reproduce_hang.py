import sys
import os
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backtest_engine import BacktestEngine
import json

engine = BacktestEngine()

# Sample request similar to what frontend sends
req = {
    "symbols": ["005930", "000660", "035420", "035720", "005380", "005490", "000270", "068270", "105560", "055550"], 
    "entry": {
        "logic": "AND",
        "conditions": [
            {
                "type": "indicator",
                "id": "ma_crossover",
                "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"},
                "weight": 1.0
            }
        ]
    },
    "exit": {
        "logic": "OR",
        "conditions": []
    },
    "risk": {
        "position_size_pct": 10.0,
        "max_positions": 5,
        "skip_risk_management": True,
        "skip_position_setting": False,
        "init_cash": 10000000.0
    },
    "period": "1Y",
    "options": {
        "fee_rate": 0.0015,
        "slippage_rate": 0.002,
        "execution_type": "next_open"
    }
}

print("Starting test backtest...")
try:
    result = engine.run_backtest(req)
    print("Backtest completed successfully!")
    print(f"Total Return: {result.get('totalReturn')}%")
except Exception as e:
    print(f"Backtest failed with error: {e}")
    import traceback
    traceback.print_exc()
