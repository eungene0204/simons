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
        "symbols": ["VALIDATION_STOCK"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 50, "operator": ">"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0},
        "period": "FULL",
    }
    
    result = engine.run_backtest(req)
    assert len(result['signals']) > 0
    first_entry = next(s for s in result['signals'] if s['type'] == 'buy')
    assert any(pytest.approx(first_entry['price'], rel=0.1) == d['open'] for d in reference_data['ohlcv'])

def test_performance_metrics(engine, reference_data):
    os.makedirs("backend/tests/data", exist_ok=True)
    df_pl = pl.from_dicts(reference_data['ohlcv'])
    df_pl.write_parquet("backend/tests/data/VALIDATION_STOCK.parquet")
    
    req = {
        "symbols": ["VALIDATION_STOCK"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "rsi", "params": {"period": 14, "value": 110, "operator": "<"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0},
        "period": "FULL",
    }
    
    result = engine.run_backtest(req)
    assert "totalReturn" in result
    assert "maxDrawdown" in result
    assert "sharpe" in result
    assert result['totalReturn'] > -100 # Just ensure it ran

def test_configurable_options(engine):
    # Test Same Day Close execution
    ohlcv = [
        {"date": "2024-01-01", "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1000000.0},
        {"date": "2024-01-02", "open": 105.0, "high": 120.0, "low": 100.0, "close": 115.0, "volume": 1000000.0},
        {"date": "2024-01-03", "open": 115.0, "high": 130.0, "low": 110.0, "close": 125.0, "volume": 1000000.0},
    ]
    os.makedirs("backend/tests/data", exist_ok=True)
    df_pl = pl.from_dicts(ohlcv)
    df_pl.write_parquet("backend/tests/data/CONFIG_TEST.parquet")
    
    req = {
        "symbols": ["CONFIG_TEST"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 102, "operator": ">"}}] 
        },
        "exit": {"logic": "AND", "conditions": []},
        "options": {
            "execution_type": "same_close",
            "fee_rate": 0.0,
            "slippage_rate": 0.0
        },
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0},
        "period": "FULL",
    }
    
    result = engine.run_backtest(req)
    entry_signals = [s for s in result['signals'] if s['type'] == 'buy']
    assert len(entry_signals) > 0
    assert entry_signals[0]['date'] == "2024-01-01"
    assert entry_signals[0]['price'] == 105.0 

def test_liquidity_filter(engine):
    ohlcv = [
        {"date": "2024-01-01", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000000.0},
        {"date": "2024-01-02", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 10.0}, 
        {"date": "2024-01-03", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000000.0},
        {"date": "2024-01-04", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000000.0},
        {"date": "2024-01-05", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000000.0},
    ]
    os.makedirs("backend/tests/data", exist_ok=True)
    df_pl = pl.from_dicts(ohlcv)
    df_pl.write_parquet("backend/tests/data/LIQUIDITY_TEST.parquet")
    
    req = {
        "symbols": ["LIQUIDITY_TEST"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 50, "operator": ">"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {
            "position_size_pct": 100, 
            "init_cash": 10000000.0,
            "liquidity_multiplier": 10.0
        },
        "period": "FULL",
    }
    
    result = engine.run_backtest(req)
    entry_dates = [s['date'] for s in result['signals'] if s['type'] == 'buy']
    
    # 2024-01-01 has no D-1 volume -> Skip
    # 2024-01-02 signal check D-1 (01-01) vol=1M -> OK. Execute at 01-03.
    # 2024-01-03 signal check D-1 (01-02) vol=10 -> FAIL.
    # So we expect entry at 2024-01-03 (execution of 01-02 signal).
    assert "2024-01-03" in entry_dates


def _write_test_ohlcv(path, start_date: str, periods: int):
    rows = []
    for index, date in enumerate(pd.date_range(start=start_date, periods=periods, freq="D")):
        price = 100.0 + index
        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": price,
            "high": price + 1.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1000000.0,
        })
    pl.from_dicts(rows).write_parquet(str(path))


def test_symbol_is_included_when_backtest_period_overlaps_available_data(tmp_path):
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    _write_test_ohlcv(data_dir / "PARTIAL_HISTORY.parquet", "2024-01-01", 5)

    engine = BacktestEngine(data_dir=str(data_dir))
    result = engine.run_backtest({
        "symbols": ["PARTIAL_HISTORY"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 50, "operator": ">"}}],
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0},
        "period": "FULL",
        "startDate": "2024-01-02",
        "endDate": "2024-01-04",
    })

    assert any(signal["symbol"] == "PARTIAL_HISTORY" for signal in result["signals"])
    assert not any(
        warning.startswith("PARTIAL_HISTORY: 상장폐지 종목")
        for warning in result["warnings"]
    )


def test_symbol_without_period_overlap_is_not_processed_without_delisting_warning(tmp_path):
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    _write_test_ohlcv(data_dir / "OLD_HISTORY.parquet", "2023-01-01", 5)
    _write_test_ohlcv(data_dir / "ACTIVE.parquet", "2024-01-01", 5)

    engine = BacktestEngine(data_dir=str(data_dir))
    result = engine.run_backtest({
        "symbols": ["OLD_HISTORY", "ACTIVE"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 50, "operator": ">"}}],
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0},
        "period": "FULL",
        "startDate": "2024-01-02",
        "endDate": "2024-01-04",
    })

    assert any(signal["symbol"] == "ACTIVE" for signal in result["signals"])
    assert not any(signal["symbol"] == "OLD_HISTORY" for signal in result["signals"])
    assert not any(
        warning.startswith("OLD_HISTORY: 상장폐지 종목")
        for warning in result["warnings"]
    )


def test_symbol_with_partial_period_data_is_included_until_data_ends(tmp_path):
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    _write_test_ohlcv(data_dir / "PARTIAL_PERIOD.parquet", "2024-01-01", 3)
    _write_test_ohlcv(data_dir / "ACTIVE.parquet", "2024-01-01", 12)

    engine = BacktestEngine(data_dir=str(data_dir))
    result = engine.run_backtest({
        "symbols": ["PARTIAL_PERIOD", "ACTIVE"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 50, "operator": ">"}}],
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 40, "liquidity_multiplier": 0},
        "period": "FULL",
        "startDate": "2024-01-01",
        "endDate": "2024-01-20",
    })

    assert any(signal["symbol"] == "ACTIVE" for signal in result["signals"])
    partial_signals = [
        signal for signal in result["signals"]
        if signal["symbol"] == "PARTIAL_PERIOD"
    ]
    assert partial_signals
    assert max(signal["date"] for signal in partial_signals) <= "2024-01-03"
    assert not any(
        warning.startswith("PARTIAL_PERIOD: 상장폐지 종목")
        for warning in result["warnings"]
    )
