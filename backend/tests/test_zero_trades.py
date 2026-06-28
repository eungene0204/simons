import pytest
import pandas as pd
import polars as pl
import os
import json
from backtest_engine import BacktestEngine

def test_zero_trades_warning():
    # Setup test data
    ohlcv = [
        {"date": "2024-01-01", "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1000000.0},
        {"date": "2024-01-02", "open": 105.0, "high": 120.0, "low": 100.0, "close": 115.0, "volume": 1000000.0},
        {"date": "2024-01-03", "open": 115.0, "high": 130.0, "low": 110.0, "close": 125.0, "volume": 1000000.0},
    ]
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    df_pl = pl.from_dicts(ohlcv)
    df_pl.write_parquet(f"{data_dir}/ZERO_TRADE_TEST.parquet")
    
    engine = BacktestEngine(data_dir=data_dir)
    
    # Strategy that will never trigger (Price > 1000)
    req = {
        "symbols": ["ZERO_TRADE_TEST"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 1000, "operator": ">"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0}
    }
    
    result = engine.run_backtest(req)
    
    # 유동성 필터 OFF(liquidity_multiplier=0)이므로 제외 종목 부연 없이 순수 매매 없음 경고만 떠야 함
    no_trade_warnings = [w for w in result["warnings"] if "매매 기록이 생성되지 않았습니다" in w]
    assert "warnings" in result
    assert len(no_trade_warnings) == 1
    assert "매수 조건 또는 유동성/포지션 설정을 확인" in no_trade_warnings[0]
    assert "유동성 기준 미달로 제외된 종목" not in no_trade_warnings[0]
    assert len(result["signals"]) == 0
    print("\n[SUCCESS] Zero trade warning verified successfully.")


def test_zero_trades_warning_includes_liquidity_excluded():
    """일부 종목은 처리됐지만 거래 0건이고, 유동성으로 제외된 종목이 있으면
    요약 경고에 제외 종목 부연 설명이 포함되어야 한다."""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    # 유동성 통과 종목 (거래량 큼) — 매수 조건은 절대 미발동(price > 1000)
    liquid = [
        {"date": "2024-01-01", "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1_000_000_000.0},
        {"date": "2024-01-02", "open": 105.0, "high": 120.0, "low": 100.0, "close": 115.0, "volume": 1_000_000_000.0},
        {"date": "2024-01-03", "open": 115.0, "high": 130.0, "low": 110.0, "close": 125.0, "volume": 1_000_000_000.0},
    ]
    # 유동성 미달 종목 (거래량 1주)
    illiquid = [
        {"date": "2024-01-01", "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1.0},
        {"date": "2024-01-02", "open": 105.0, "high": 120.0, "low": 100.0, "close": 115.0, "volume": 1.0},
        {"date": "2024-01-03", "open": 115.0, "high": 130.0, "low": 110.0, "close": 125.0, "volume": 1.0},
    ]
    pl.from_dicts(liquid).write_parquet(f"{data_dir}/ZERO_TRADE_LIQUID.parquet")
    pl.from_dicts(illiquid).write_parquet(f"{data_dir}/ZERO_TRADE_ILLIQUID.parquet")

    engine = BacktestEngine(data_dir=data_dir)

    req = {
        "symbols": ["ZERO_TRADE_LIQUID", "ZERO_TRADE_ILLIQUID"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 1000, "operator": ">"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 10}
    }

    result = engine.run_backtest(req)

    no_trade_warnings = [w for w in result["warnings"] if "매매 기록이 생성되지 않았습니다" in w]
    assert len(no_trade_warnings) == 1
    assert "유동성 기준 미달로 제외된 종목 1개" in no_trade_warnings[0]
    assert "ZERO_TRADE_ILLIQUID" in no_trade_warnings[0]
    print("\n[SUCCESS] Liquidity-excluded summary warning verified successfully.")

if __name__ == "__main__":
    test_zero_trades_warning()
    test_zero_trades_warning_includes_liquidity_excluded()
