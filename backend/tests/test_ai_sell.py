
import os
import sys
import pandas as pd
import numpy as np
import polars as pl

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from engine.signals import SignalEngine

def test_ai_sell_logic():
    engine = SignalEngine()
    
    # Mock data with ai_score
    # score 0.1 should be a sell if threshold is 0.3
    df = pl.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "ai_score": [0.8, 0.1],
        "close": [10000, 9500]
    })
    
    # AI Sell Condition (Threshold 30% -> 0.3)
    sell_cond = {
        "id": "ai_model",
        "params": {
            "signalType": "sell",
            "sellThreshold": 30.0
        }
    }
    
    # AI Buy Condition (Threshold 70% -> 0.7)
    buy_cond = {
        "id": "ai_model",
        "params": {
            "signalType": "buy",
            "buyThreshold": 70.0
        }
    }
    
    # Test Index 0: Score 0.8
    res_buy_0 = engine.evaluate_condition(buy_cond, 0, df)
    res_sell_0 = engine.evaluate_condition(sell_cond, 0, df)
    print(f"Day 0 (Score 0.8): Buy={res_buy_0}, Sell={res_sell_0}")
    
    # Test Index 1: Score 0.1
    res_buy_1 = engine.evaluate_condition(buy_cond, 1, df)
    res_sell_1 = engine.evaluate_condition(sell_cond, 1, df)
    print(f"Day 1 (Score 0.1): Buy={res_buy_1}, Sell={res_sell_1}")

    # Assertions
    assert res_buy_0 == True, "Score 0.8 should trigger buy (>= 0.7)"
    assert res_sell_0 == False, "Score 0.8 should NOT trigger sell (<= 0.3)"
    assert res_buy_1 == False, "Score 0.1 should NOT trigger buy"
    assert res_sell_1 == True, "Score 0.1 should trigger sell (<= 0.3)"
    
    print("\nVerification Successful: AI Sell logic is correctly implemented and works with parameters.")

if __name__ == "__main__":
    test_ai_sell_logic()
