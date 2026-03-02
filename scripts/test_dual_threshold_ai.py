import sys
import os
import json
import pandas as pd
import polars as pl
import numpy as np

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.engine.signals import SignalEngine

def test_dual_threshold_ai():
    engine = SignalEngine()
    
    # Create dummy data with AI scores
    df = pl.DataFrame({
        "ai_score": [0.1, 0.2, 0.4, 0.6, 0.8, 0.9, 0.5, 0.2, 0.1],
        "ai_drop_score": [0.05, 0.4, 0.6, 0.8, 0.85, 0.7, 0.2, 0.1, 0.05]
    })
    
    # Test Buy Condition (Threshold 70%)
    buy_cond = {
        'id': 'ai_model',
        'params': {
            'targetType': 'up',
            'targetThreshold': 7,
            'minProbability': 70,
            'signalType': 'buy'
        }
    }
    
    # Test Sell Condition: targetType down (Threshold 70%)
    sell_cond = {
        'id': 'ai_model',
        'params': {
            'targetType': 'down',
            'targetThreshold': 7,
            'minProbability': 70,
            'signalType': 'sell' # sell when drop prob >= 0.7
        }
    }
    
    # Test Backward Compatibility (Threshold 50, legacy direction)
    legacy_buy_cond = {
        'id': 'ai_model',
        'params': {
            'minProbability': 50,
            'signalType': 'buy'
        }
    }
    
    print("Verifying Buy Signals (Threshold 70%)...")
    for i in range(len(df)):
        res = engine.evaluate_condition(buy_cond, i, df)
        score = df["ai_score"][i]
        expected = score >= 0.7
        print(f"Index {i}: Score={score:.1f}, Signal={res}, Expected={expected}")
        assert res == expected, f"Buy signal mismatch at index {i}"
        
    print("\nVerifying Sell Signals (Drop Prob >= 70%)...")
    for i in range(len(df)):
        res = engine.evaluate_condition(sell_cond, i, df)
        score = df["ai_drop_score"][i]
        expected = score >= 0.7
        print(f"Index {i}: DropScore={score:.2f}, Signal={res}, Expected={expected}")
        assert res == expected, f"Sell signal mismatch at index {i}"

    print("\nVerifying Backward Compatibility (Buy, legacy threshold 50%)...")
    for i in range(len(df)):
        res = engine.evaluate_condition(legacy_buy_cond, i, df)
        score = df["ai_score"][i]
        expected = score >= 0.5
        print(f"Index {i}: Score={score:.1f}, Signal={res}, Expected={expected}")
        assert res == expected, f"Legacy Buy signal mismatch at index {i}"

    # Verify Descriptions
    desc_buy = engine.get_condition_description(buy_cond)
    desc_sell = engine.get_condition_description(sell_cond)
    print(f"\nDescription (Buy): {desc_buy}")
    print(f"Description (Sell): {desc_sell}")
    assert "70%" in desc_buy and "매수" in desc_buy
    assert "70%" in desc_sell and "이상 (위험 청산)" in desc_sell

    print("\nVerification successful!")

if __name__ == "__main__":
    test_dual_threshold_ai()
