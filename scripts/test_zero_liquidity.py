
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backtest_engine import BacktestEngine
import json

def test_zero_liquidity():
    engine = BacktestEngine()
    # Using symbols that were reported as failing
    req = {
        "symbols": ["008110", "006380", "007610"],
        "risk_params": {
            "init_cash": 10000000,
            "position_size_pct": 10,
            "liquidity_limit_pct": 0, # Should disable filtering
            "ranking_enabled": False
        },
        "entry": {"conditions": [{"id": "price_above_sma", "params": {"period": 20}}]},
        "exit": {"conditions": [{"id": "price_below_sma", "params": {"period": 20}}]},
        "period": "1Y"
    }
    
    print("Running backtest with 0% liquidity limit...")
    result = engine.run_backtest(req)
    
    warnings = result.get("warnings", [])
    print(f"Warnings: {warnings}")
    
    liquidity_warnings = [w for w in warnings if "유동성" in w]
    if not liquidity_warnings:
        print("SUCCESS: No liquidity warnings found with 0% limit.")
    else:
        print(f"FAILED: Found liquidity warnings: {liquidity_warnings}")

if __name__ == "__main__":
    test_zero_liquidity()
