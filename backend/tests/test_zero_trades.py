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
    
    expected_warning = "매매 조건에 부합하는 종목이 없어 매매 기록이 생성되지 않았습니다. 매수 조건을 확인해 주세요."
    assert "warnings" in result
    assert expected_warning in result["warnings"]
    assert len(result["signals"]) == 0
    print("\n[SUCCESS] Zero trade warning verified successfully.")

if __name__ == "__main__":
    test_zero_trades_warning()
