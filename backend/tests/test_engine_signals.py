import pytest
import polars as pl
import numpy as np
from engine.signals import SignalEngine

@pytest.fixture
def signal_engine():
    return SignalEngine()

def test_evaluate_condition_ma_crossover(signal_engine):
    # Setup dummy data for golden cross and dead cross
    data = {"close_5_sma": [10, 10, 12, 8], "close_20_sma": [11, 11, 11, 11]}
    df = pl.DataFrame(data)
    
    # Golden cross: short crosses above long
    cond_buy = {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
    
    assert signal_engine.evaluate_condition(cond_buy, 1, df) == False # 10 < 11
    assert signal_engine.evaluate_condition(cond_buy, 2, df) == True  # 10 < 11 -> 12 > 11 (Golden Cross)
    assert signal_engine.evaluate_condition(cond_buy, 3, df) == False # 12 > 11 -> 8 < 11 (Dead Cross, but looking for buy)

    # Dead cross: short crosses below long
    cond_sell = {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}}
    assert signal_engine.evaluate_condition(cond_sell, 2, df) == False
    assert signal_engine.evaluate_condition(cond_sell, 3, df) == True  # 12 > 11 -> 8 < 11 (Dead Cross)

def test_evaluate_condition_rsi(signal_engine):
    data = {"rsi_14": [20, 30, 40, 80]}
    df = pl.DataFrame(data)
    
    cond_under_30 = {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}}
    assert signal_engine.evaluate_condition(cond_under_30, 0, df) == True
    assert signal_engine.evaluate_condition(cond_under_30, 1, df) == False # Not < 30
    
    cond_over_70 = {"id": "rsi", "params": {"period": 14, "value": 70, "operator": ">="}}
    assert signal_engine.evaluate_condition(cond_over_70, 3, df) == True

def test_evaluate_condition_price_limit_exit(signal_engine):
    data = {"close": [100.0, 120.0, 80.0]}
    df = pl.DataFrame(data)
    
    # Stop loss krw
    cond_sl = {"id": "price_limit_exit", "params": {"stopLoss": 90, "stopLossMode": "krw"}}
    assert signal_engine.evaluate_condition(cond_sl, 0, df) == False # 100
    assert signal_engine.evaluate_condition(cond_sl, 2, df) == True  # 80 <= 90
    
    # Take profit krw
    cond_tp = {"id": "price_limit_exit", "params": {"takeProfit": 110, "takeProfitMode": "krw"}}
    assert signal_engine.evaluate_condition(cond_tp, 0, df) == False # 100
    assert signal_engine.evaluate_condition(cond_tp, 1, df) == True  # 120 >= 110
    
    # Combined
    cond_both = {"id": "price_limit_exit", "params": {"stopLoss": 90, "stopLossMode": "krw", "takeProfit": 110, "takeProfitMode": "krw"}}
    assert signal_engine.evaluate_condition(cond_both, 0, df) == False
    assert signal_engine.evaluate_condition(cond_both, 1, df) == True # TP
    assert signal_engine.evaluate_condition(cond_both, 2, df) == True # SL

def test_evaluate_condition_ai_model(signal_engine):
    data = {"ai_score": [0.3, 0.7, 0.9]} # Probabilities 30%, 70%, 90%
    df = pl.DataFrame(data)
    
    cond_buy_70 = {"id": "ai_model", "params": {"signalType": "buy", "minProbability": 70}} # threshold 0.7
    assert signal_engine.evaluate_condition(cond_buy_70, 0, df) == False
    assert signal_engine.evaluate_condition(cond_buy_70, 1, df) == True
    assert signal_engine.evaluate_condition(cond_buy_70, 2, df) == True
    
    cond_sell_60 = {"id": "ai_model", "params": {"signalType": "sell", "minProbability": 50}} # threshold 0.5
    assert signal_engine.evaluate_condition(cond_sell_60, 0, df) == True # 0.3 <= 0.5
    assert signal_engine.evaluate_condition(cond_sell_60, 1, df) == False # 0.7 <= 0.5 (False)

def test_evaluate_condition_ai_drop_model(signal_engine):
    data = {"ai_drop_score": [0.2, 0.6, 0.9]} # Drop probs 20%, 60%, 90%
    df = pl.DataFrame(data)
    
    # Buy strategy: Drop prob must be <= threshold (e.g. 50%)
    cond_buy_50 = {"id": "ai_drop_model", "params": {"signalType": "buy", "minProbability": 50}}
    assert signal_engine.evaluate_condition(cond_buy_50, 0, df) == True  # 0.2 <= 0.5
    assert signal_engine.evaluate_condition(cond_buy_50, 1, df) == False # 0.6 <= 0.5 (False)
    
    # Sell strategy: Drop prob must be >= threshold (e.g. 80%)
    cond_sell_80 = {"id": "ai_drop_model", "params": {"signalType": "sell", "minProbability": 80}}
    assert signal_engine.evaluate_condition(cond_sell_80, 1, df) == False # 0.6 >= 0.8 (False)
    assert signal_engine.evaluate_condition(cond_sell_80, 2, df) == True  # 0.9 >= 0.8

def test_evaluate_group_logic(signal_engine):
    data = {
        "rsi_14": [20, 40],
        "close_5_sma": [10, 12],
        "close_20_sma": [11, 11]
    }
    df = pl.DataFrame(data)
    
    group_and = {
        "logic": "AND",
        "conditions": [
            {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}},
            {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
        ]
    }
    
    # Index 0: rsi < 30 is True, ma cross is False
    assert signal_engine.evaluate_group(group_and, 0, df)[0] == False
    
    # Change df so index 1 has rsi < 30 AND ma cross is True
    data_true = {
        "rsi_14": [20, 20],
        "close_5_sma": [10, 12],
        "close_20_sma": [11, 11]
    }
    df_true = pl.DataFrame(data_true)
    assert signal_engine.evaluate_group(group_and, 1, df_true)[0] == True
    
    # Testing OR logic
    group_or = {
        "logic": "OR",
        "conditions": [
            {"id": "rsi", "params": {"period": 14, "value": 30, "operator": "<"}},
            {"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}
        ]
    }
    
    # Index 0: rsi < 30 is True, ma cross is False -> True because OR
    assert signal_engine.evaluate_group(group_or, 0, df)[0] == True
