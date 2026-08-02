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


# ── 백테스트 창 경계(2026-08-02) ────────────────────────────────────────────

def test_date_key_boundaries_are_inclusive_on_both_ends():
    """[회귀] 명시 종료일 당일 봉이 통째로 빠지던 비대칭 off-by-one.

    타임스탬프를 통째로 문자열화해 비교하면 `"2024-12-30 00:00:00.000000" <= "2024-12-30"`
    이 거짓이다(접두가 같고 더 긴 쪽이 크다). 시작 경계는 같은 규칙이 우연히 맞는
    방향이라 **끝에서만** 하루가 사라졌고, 종료일이 휴장일이면 증상이 가려졌다.
    date 컬럼 타입은 파일마다 갈리므로(실측 us/ns/String) 세 타입 모두 고정한다.
    """
    from backtest_engine import _date_key

    rows = ["2024-01-01", "2024-01-02", "2024-01-03"]
    frames = {
        "us": pl.DataFrame({"date": pl.Series(rows).str.to_datetime(time_unit="us")}),
        "ns": pl.DataFrame({"date": pl.Series(rows).str.to_datetime(time_unit="ns")}),
        "str": pl.DataFrame({"date": rows}),
    }
    for label, df in frames.items():
        kept = df.filter(_date_key() >= "2024-01-01").filter(_date_key() <= "2024-01-03")
        got = kept.select(_date_key()).to_series().to_list()
        assert got == rows, f"{label}: 양끝 포함이어야 하는데 {got}"


def test_backtest_includes_the_requested_end_date_bar():
    """요청한 종료일의 봉이 실제 실행 창에 들어간다(엔드투엔드)."""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    ohlcv = [
        {"date": "2024-01-02", "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 1_000_000_000.0},
        {"date": "2024-01-03", "open": 105.0, "high": 120.0, "low": 100.0, "close": 115.0, "volume": 1_000_000_000.0},
        {"date": "2024-01-04", "open": 115.0, "high": 130.0, "low": 110.0, "close": 125.0, "volume": 1_000_000_000.0},
    ]
    pl.from_dicts(ohlcv).with_columns(
        pl.col("date").str.to_datetime(time_unit="us")
    ).write_parquet(f"{data_dir}/END_BOUNDARY_TEST.parquet")

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest({
        "symbols": ["END_BOUNDARY_TEST"],
        "entry": {"logic": "AND",
                  "conditions": [{"id": "price", "params": {"value": 1000, "operator": ">"}}]},
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0},
        "startDate": "2024-01-02",
        "endDate": "2024-01-04",     # 마지막 봉과 같은 날 — 예전에는 이 봉이 잘렸다
    })
    assert result["dates"][-1].startswith("2024-01-04"), result["dates"]
