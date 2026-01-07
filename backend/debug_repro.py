import sys
import os
sys.path.append(os.getcwd())
from backtest_engine import BacktestEngine
import json
import pandas as pd
import numpy as np

engine = BacktestEngine(data_dir="./data/ohlcv")
# User-like request
req = {
  "symbol": "005930",
  "entry": {
    "logic": "AND",
    "conditions": [
      {
        "type": "indicator",
        "id": "ma_crossover",
        "params": {
          "shortMA": 5,
          "longMA": 20,
          "signalType": "buy"
        },
        "weight": 1.0
      }
    ]
  },
  "exit": {
    "logic": "OR",
    "conditions": []
  },
  "risk": {
    "position_size_pct": 100.0,
    "max_positions": 1,
    "stop_loss_pct": 0,
    "take_profit_pct": 0,
    "trailing_stop_pct": 0,
    "max_holding_days": 0,
    "init_cash": 10000000.0
  },
  "period": "1Y",
  "options": {
    "fee_rate": 0.0015,
    "slippage_rate": 0.002,
    "execution_type": "next_open"
  }
}

result = engine.run_backtest(req)
print(f"--- Backtest Result ---")
print(f"Total Return: {result['totalReturn']}%")
print(f"Equity[0]: {result['equity'][0]:,.0f}")
print(f"Equity[-1]: {result['equity'][-1]:,.0f}")
print(f"Profit/Loss: {result['equity'][-1] - result['equity'][0]:,.0f}")

# Check for any huge jumps in equity
equity_series = pd.Series(result['equity'])
max_diff = equity_series.diff().abs().max()
print(f"Max Daily Equity Change: {max_diff:,.0f}")

# Check signals
print(f"Total Signals: {len(result['signals'])}")
if result['signals']:
    print(f"First Signal: {result['signals'][0]}")

