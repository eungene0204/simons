import pytest
import polars as pl
from engine.signals import SignalEngine

@pytest.fixture
def signal_engine():
    return SignalEngine()

def test_per_block_logic_sequential(signal_engine):
    """
    Test that per-block logic is applied sequentially.
    Scenario: (RSI < 30) AND (Price > 100) OR (MA Cross)
    """
    # Create data where:
    # 1. RSI < 30 is True (25)
    # 2. Price > 100 is False (90)
    # 3. MA Golden Cross is True (10 < 11 -> 12 > 11)
    data = {
        "rsi_14": [25, 25],
        "close": [90, 90],
        "close_5_sma": [10, 12],
        "close_20_sma": [11, 11]
    }
    df = pl.DataFrame(data)
    
    # 1. Cond A: RSI < 30 (logic=AND, ignored for first)
    # 2. Cond B: Price > 100 (logic=AND) -> (A AND B) = (T AND F) = F
    # 3. Cond C: MA Cross (logic=OR) -> ((A AND B) OR C) = (F OR T) = T
    
    group = {
        "conditions": [
            {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}, "logic": "AND"},
            {"id": "price", "params": {"value": 100, "operator": ">"}, "logic": "AND"},
            {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}, "logic": "OR"}
        ]
    }
    
    res, desc = signal_engine.evaluate_group(group, 1, df)
    
    assert res == True
    # Description should include parts that were True
    assert "RSI 30 이하" in desc
    assert "5일선-20일선 골든크로스" in desc
    assert "또는" in desc
    assert "현재가 100원 이상" not in desc

def test_per_block_logic_all_and(signal_engine):
    """
    Standard behavior: All AND
    (RSI < 30) AND (Price > 100)
    """
    data = {
        "rsi_14": [25],
        "close": [90]
    }
    df = pl.DataFrame(data)
    
    group = {
        "conditions": [
            {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}, "logic": "AND"},
            {"id": "price", "params": {"value": 100, "operator": ">"}, "logic": "AND"}
        ]
    }
    
    res, _ = signal_engine.evaluate_group(group, 0, df)
    assert res == False

def test_per_block_logic_leading_or(signal_engine):
    """
    Check if leading OR works (though logically it's the same as AND for the first item)
    (A OR B) where A=False, B=True -> True
    """
    data = {
        "rsi_14": [40],   # False
        "close": [120]    # True
    }
    df = pl.DataFrame(data)
    
    group = {
        "conditions": [
            {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}, "logic": "AND"},
            {"id": "price", "params": {"value": 100, "operator": ">"}, "logic": "OR"}
        ]
    }
    
    res, desc = signal_engine.evaluate_group(group, 0, df)
    assert res == True
    assert "현재가 100원 이상" in desc
