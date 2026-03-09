import polars as pl
import numpy as np
from engine.signals import SignalEngine

def test_logic():
    engine = SignalEngine()
    
    # 5-day SMA and 20-day SMA data
    # Index 0: No cross
    # Index 1: Short crosses above Long (Golden Cross)
    data = {
        "close_5_sma": [10, 12, 11, 13],
        "close_20_sma": [11, 11, 11, 11],
        "ai_score": [0.3, 0.5, 0.8, 0.9] # 80%+ at index 2
    }
    df = pl.DataFrame(data)
    
    ma_cross_cond = {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
    ai_cond = {"id": "ai_model", "params": {"signalType": "buy", "minProbability": 70}} # 0.7 threshold
    
    # Test AND Logic
    group_and = {
        "logic": "AND",
        "conditions": [ma_cross_cond, ai_cond]
    }
    
    # Index 1: MA Golden Cross (T), AI Score 0.5 (F) -> AND: False
    res_and_1, desc_and_1 = engine.evaluate_group(group_and, 1, df)
    print(f"AND Logic Index 1: {res_and_1}, {desc_and_1}")
    
    # Index 2: MA Golden Cross (F - already crossed), AI Score 0.8 (T) -> AND: False
    res_and_2, desc_and_2 = engine.evaluate_group(group_and, 2, df)
    print(f"AND Logic Index 2: {res_and_2}, {desc_and_2}")
    
    # Test OR Logic
    group_or = {
        "logic": "OR",
        "conditions": [ma_cross_cond, ai_cond]
    }
    
    # Index 1: MA Golden Cross (T), AI Score 0.5 (F) -> OR: True
    res_or_1, desc_or_1 = engine.evaluate_group(group_or, 1, df)
    print(f"OR Logic Index 1: {res_or_1}, {desc_or_1}")
    
    # Index 2: MA Golden Cross (F), AI Score 0.8 (T) -> OR: True
    res_or_2, desc_or_2 = engine.evaluate_group(group_or, 2, df)
    print(f"OR Logic Index 2: {res_or_2}, {desc_or_2}")
    
    # Verify the specific description for OR
    if res_or_2:
        if " 또는 " in desc_or_2:
            print("SUCCESS: '또는' found in OR signal description")
        else:
            print(f"FAILED: '또는' NOT found in OR signal description: {desc_or_2}")

if __name__ == "__main__":
    test_logic()
