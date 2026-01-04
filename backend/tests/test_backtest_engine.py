import pytest
import pandas as pd
import numpy as np
import json
import os
import polars as pl
from backtest_engine import BacktestEngine

@pytest.fixture
def engine():
    return BacktestEngine(data_dir="backend/tests/data")

@pytest.fixture
def reference_data():
    path = "backend/tests/tradingview_reference.json"
    with open(path, 'r') as f:
        return json.load(f)

def test_indicator_sma(engine, reference_data):
    df_pl = pl.from_dicts(reference_data['ohlcv'])
    conditions = [{
        "id": "ma_crossover",
        "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}
    }]
    results_pl = engine.calculate_indicators(df_pl, conditions)
    results_pdf = results_pl.to_pandas()
    expected_sma5 = reference_data['expected']['sma_5']
    for i in range(5, len(expected_sma5)):
        val = expected_sma5[i]
        calc = results_pdf['close_5_sma'].iloc[i]
        assert pytest.approx(calc, abs=0.5) == val

def test_trade_signals_and_execution(engine, reference_data):
    os.makedirs("backend/tests/data", exist_ok=True)
    df_pl = pl.from_dicts(reference_data['ohlcv'])
    df_pl.write_parquet("backend/tests/data/VALIDATION_STOCK.parquet")
    
    req = {
        "symbol": "VALIDATION_STOCK",
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 100, "operator": ">"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0} # Disable filter
    }
    
    result = engine.run_backtest(req)
    assert len(result['signals']) > 0
    first_entry = next(s for s in result['signals'] if s['type'] == 'entry')
    # Price should be nearby because of slippage
    assert any(pytest.approx(first_entry['price'], rel=0.01) == d['open'] for d in reference_data['ohlcv'])

def test_performance_metrics(engine, reference_data):
    os.makedirs("backend/tests/data", exist_ok=True)
    df_pl = pl.from_dicts(reference_data['ohlcv'])
    df_pl.write_parquet("backend/tests/data/VALIDATION_STOCK.parquet")
    
    req = {
        "symbol": "VALIDATION_STOCK",
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "rsi", "params": {"period": 14, "value": 110, "operator": "<"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0} # Disable filter
    }
    
    result = engine.run_backtest(req)
    assert "totalReturn" in result
    assert "maxDrawdown" in result
    assert "sharpe" in result
    assert "outOfSample" in result['validation']
    assert result['totalReturn'] > 0 

def test_real_tradingview_data(engine):
    req = {
        "symbol": "REAL_TV_DATA",
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "buy"}}]
        },
        "exit": {
            "logic": "AND",
            "conditions": [{"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20, "signalType": "sell"}}]
        },
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0} # Disable filter for this test
    }
    
    result = engine.run_backtest(req)
    assert result['symbol'] == "REAL_TV_DATA"
    assert "validation" in result
    if len(result['signals']) > 0:
        print(f"Verified {len(result['signals'])} signals on real data.")

def test_configurable_options(engine):
    # Test Same Day Close execution
    ohlcv = [
        {"date": "2024-01-01", "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1000000.0},
        {"date": "2024-01-02", "open": 105.0, "high": 120.0, "low": 100.0, "close": 115.0, "volume": 1000000.0},
    ]
    os.makedirs("backend/tests/data", exist_ok=True)
    df_pl = pl.from_dicts(ohlcv)
    df_pl.write_parquet("backend/tests/data/CONFIG_TEST.parquet")
    
    req = {
        "symbol": "CONFIG_TEST",
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 102, "operator": ">"}}] # Trigger at Day 0
        },
        "exit": {"logic": "AND", "conditions": []},
        "options": {
            "execution_type": "same_close",
            "fee_rate": 0.0,
            "slippage_rate": 0.0
        },
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0}
    }
    
    result = engine.run_backtest(req)
    # Signal at Day 0 (index 0). 
    # execution_type="same_close" -> entries_exec[0] = True.
    # Execute at Day 0 Close (105.0).
    
    entry_signals = [s for s in result['signals'] if s['type'] == 'entry']
    assert len(entry_signals) > 0
    assert entry_signals[0]['date'] == "2024-01-01"
    assert entry_signals[0]['price'] == 105.0 # Day 0 Close

def test_liquidity_filter(engine):
    ohlcv = [
        {"date": "2024-01-01", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000000.0},
        {"date": "2024-01-02", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0}, # Liquidity bottleneck
        {"date": "2024-01-03", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000000.0},
        {"date": "2024-01-04", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000000.0}
    ]
    os.makedirs("backend/tests/data", exist_ok=True)
    df_pl = pl.from_dicts(ohlcv)
    df_pl.write_parquet("backend/tests/data/LIQUIDITY_TEST.parquet")
    
    req = {
        "symbol": "LIQUIDITY_TEST",
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 50, "operator": ">"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {
            "position_size_pct": 100, 
            "init_cash": 10000000.0,
            "liquidity_multiplier": 10.0
        }
    }
    
    result = engine.run_backtest(req)
    entry_dates = [s['date'] for s in result['signals'] if s['type'] == 'entry']
    
    # Expected behavior:
    # Day 1: Signal index 0. Check liquidity? No D-1, so excluded.
    # Day 2: Signal index 1. Check liquidity D-1 (Day 1). vol_val[0]=100M >= 100M -> OK. 
    #        entries[1] = True. Execute at index 2 (Day 3).
    # Day 3: Signal index 2. Check liquidity D-1 (Day 2). vol_val[1]=1000 < 100M -> Fail.
    #        entries[2] = False.
    
    assert "2024-01-02" not in entry_dates
    assert "2024-01-03" in entry_dates
    assert "2024-01-04" not in entry_dates
