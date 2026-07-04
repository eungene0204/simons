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
    """전략이 매수하려 했으나 유동성으로 전량 차단된 종목만 제외 종목으로 요약에 포함된다.
    (전략이 애초에 매수하지 않는 종목은 유동성과 무관하게 언급되지 않아야 한다.)"""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    # 유동성 통과 종목 — 매수 조건(price>200) 미발동(가격 낮음) → 거래 0건
    liquid = [
        {"date": "2024-01-01", "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1_000_000_000.0},
        {"date": "2024-01-02", "open": 105.0, "high": 120.0, "low": 100.0, "close": 115.0, "volume": 1_000_000_000.0},
        {"date": "2024-01-03", "open": 115.0, "high": 130.0, "low": 110.0, "close": 125.0, "volume": 1_000_000_000.0},
    ]
    # 유동성 미달 종목 — 매수 조건(price>200) 발동하지만 거래량 1주라 전량 차단
    illiquid = [
        {"date": "2024-01-01", "open": 300.0, "high": 310.0, "low": 290.0, "close": 305.0, "volume": 1.0},
        {"date": "2024-01-02", "open": 305.0, "high": 320.0, "low": 300.0, "close": 315.0, "volume": 1.0},
        {"date": "2024-01-03", "open": 315.0, "high": 330.0, "low": 310.0, "close": 325.0, "volume": 1.0},
    ]
    pl.from_dicts(liquid).write_parquet(f"{data_dir}/ZERO_TRADE_LIQUID.parquet")
    pl.from_dicts(illiquid).write_parquet(f"{data_dir}/ZERO_TRADE_ILLIQUID.parquet")

    engine = BacktestEngine(data_dir=data_dir)

    req = {
        "symbols": ["ZERO_TRADE_LIQUID", "ZERO_TRADE_ILLIQUID"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 200, "operator": ">"}}]
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


def test_illiquid_stock_not_traded_emits_no_liquidity_warning():
    """전략이 매수 신호를 내지 않는 유동성 미달 종목은 유동성 경고를 내지 않는다.
    (상폐 임박 거래정지 종목이 모든 전략 결과에 노이즈로 뜨던 버그 회귀 방지.)"""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    # 유동성 미달 종목 — 매수 조건(price>1000)은 절대 미발동
    illiquid = [
        {"date": "2024-01-01", "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1.0},
        {"date": "2024-01-02", "open": 105.0, "high": 120.0, "low": 100.0, "close": 115.0, "volume": 1.0},
        {"date": "2024-01-03", "open": 115.0, "high": 130.0, "low": 110.0, "close": 125.0, "volume": 1.0},
    ]
    pl.from_dicts(illiquid).write_parquet(f"{data_dir}/UNTRADED_ILLIQUID.parquet")

    engine = BacktestEngine(data_dir=data_dir)

    req = {
        "symbols": ["UNTRADED_ILLIQUID"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "params": {"value": 1000, "operator": ">"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 10}
    }

    result = engine.run_backtest(req)

    liquidity_warnings = [w for w in result["warnings"] if "유동성 기준 미달" in w]
    assert liquidity_warnings == [], f"전략이 매수하지 않는 종목에 유동성 경고가 발생함: {liquidity_warnings}"
    print("\n[SUCCESS] Untraded illiquid stock emits no liquidity warning.")

if __name__ == "__main__":
    test_zero_trades_warning()
    test_zero_trades_warning_includes_liquidity_excluded()
    test_illiquid_stock_not_traded_emits_no_liquidity_warning()
