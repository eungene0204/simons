import pytest
import pandas as pd
import numpy as np
import json
import os
import polars as pl
from backtest_engine import BacktestEngine

_TESTS_DIR = os.path.dirname(__file__)
_DATA_DIR = os.path.join(_TESTS_DIR, "data")

@pytest.fixture
def engine():
    return BacktestEngine(data_dir=_DATA_DIR)

@pytest.fixture
def reference_data():
    path = os.path.join(_TESTS_DIR, "tradingview_reference.json")
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
    os.makedirs(_DATA_DIR, exist_ok=True)
    df_pl = pl.from_dicts(reference_data['ohlcv'])
    df_pl.write_parquet(os.path.join(_DATA_DIR, "VALIDATION_STOCK.parquet"))
    
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
    os.makedirs(_DATA_DIR, exist_ok=True)
    df_pl = pl.from_dicts(reference_data['ohlcv'])
    df_pl.write_parquet(os.path.join(_DATA_DIR, "VALIDATION_STOCK.parquet"))
    
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
    os.makedirs(_DATA_DIR, exist_ok=True)
    df_pl = pl.from_dicts(ohlcv)
    df_pl.write_parquet(os.path.join(_DATA_DIR, "CONFIG_TEST.parquet"))
    
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
    os.makedirs(_DATA_DIR, exist_ok=True)
    df_pl = pl.from_dicts(ohlcv)
    df_pl.write_parquet(os.path.join(_DATA_DIR, "LIQUIDITY_TEST.parquet"))
    
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


def _write_priced_ohlcv(path, start_date: str, periods: int, base: float):
    rows = []
    for index, date in enumerate(pd.date_range(start=start_date, periods=periods, freq="D")):
        price = base + index
        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": price, "high": price + 1.0, "low": price - 1.0,
            "close": price, "volume": 1000000.0,
        })
    pl.from_dicts(rows).write_parquet(str(path))


def _write_master(path, stocks):
    path.write_text(json.dumps({"stocks": stocks}), encoding="utf-8")


def test_delisted_stock_held_position_is_force_closed_at_last_price(tmp_path, monkeypatch):
    # Survivorship fix: a name that delists mid-backtest must be tradeable while alive
    # and the held position liquidated at its final available price (정리매매), not left
    # dangling. This is what lets delisting losses actually hit the equity curve.
    from engine import universe_pit
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    _write_priced_ohlcv(data_dir / "ACTIVE.parquet", "2024-01-01", 20, 100.0)
    _write_priced_ohlcv(data_dir / "DEADCO.parquet", "2024-01-01", 8, 100.0)  # stops 2024-01-08

    master_path = tmp_path / "stock-master.json"
    _write_master(master_path, [
        {"symbol": "ACTIVE", "market": "KOSPI", "delistingDate": None,
         "shares": 1000, "dataStart": "2024-01-01", "dataEnd": "2024-01-20", "hasOhlcv": True},
        {"symbol": "DEADCO", "market": "KOSPI", "delistingDate": "2024-01-08",
         "shares": 1000, "dataStart": "2024-01-01", "dataEnd": "2024-01-08", "hasOhlcv": True},
    ])
    monkeypatch.setattr(universe_pit, "_MASTER_PATH", master_path)
    universe_pit.reload_master()

    engine = BacktestEngine(data_dir=str(data_dir))
    result = engine.run_backtest({
        "symbols": ["IGNORED"],
        "universe_id": "kospi",
        "entry": {"logic": "AND", "conditions": [{"id": "price", "params": {"value": 1, "operator": ">"}}]},
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 50, "liquidity_multiplier": 0, "max_positions": 10},
        "options": {"execution_type": "same_close"},
        "period": "FULL", "startDate": "2024-01-02", "endDate": "2024-01-20",
    })
    universe_pit.reload_master()

    dead = [s for s in result["signals"] if s["symbol"] == "DEADCO"]
    assert any(s["type"] == "buy" for s in dead), "delisted name must be tradeable while alive"
    sells = [s for s in dead if s["type"] == "sell"]
    assert sells, "held position in a delisted name must be force-closed"
    # the forced exit happens at/just before the stock's last trading day, not the period end
    assert max(s["date"] for s in sells) <= "2024-01-08"
    # and it is labelled as a delisting, not a generic data cutoff
    assert any(s.get("condition", "").startswith("상장폐지") for s in sells)


def test_large_cap_universe_keeps_only_top_n_by_market_cap(tmp_path, monkeypatch):
    from engine import universe_pit
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    # equal shares → market cap ordering follows price: BIG1 > BIG2 > SMALL
    _write_priced_ohlcv(data_dir / "BIG1.parquet", "2024-01-01", 20, 400.0)
    _write_priced_ohlcv(data_dir / "BIG2.parquet", "2024-01-01", 20, 300.0)
    _write_priced_ohlcv(data_dir / "SMALL.parquet", "2024-01-01", 20, 100.0)

    master_path = tmp_path / "stock-master.json"
    _write_master(master_path, [
        {"symbol": s, "market": "KOSPI", "delistingDate": None, "shares": 1000,
         "dataStart": "2024-01-01", "dataEnd": "2024-01-20", "hasOhlcv": True}
        for s in ("BIG1", "BIG2", "SMALL")
    ])
    monkeypatch.setattr(universe_pit, "_MASTER_PATH", master_path)
    monkeypatch.setattr(universe_pit, "LARGE_CAP_TOP_N", 2)
    universe_pit.reload_master()

    engine = BacktestEngine(data_dir=str(data_dir))
    result = engine.run_backtest({
        "symbols": ["IGNORED"],
        "universe_id": "kospi200",
        "entry": {"logic": "AND", "conditions": [{"id": "price", "params": {"value": 1, "operator": ">"}}]},
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 25, "liquidity_multiplier": 0, "max_positions": 10},
        "options": {"execution_type": "same_close"},
        "period": "FULL", "startDate": "2024-01-02", "endDate": "2024-01-20",
    })
    universe_pit.reload_master()

    traded = {s["symbol"] for s in result["signals"]}
    assert "BIG1" in traded and "BIG2" in traded
    assert "SMALL" not in traded, "below the top-N market-cap cutoff must be excluded"


def _write_fundamental_ohlcv(path, start_date: str, periods: int, base: float, pbr: float):
    rows = []
    for index, date in enumerate(pd.date_range(start=start_date, periods=periods, freq="D")):
        price = base + index
        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": price, "high": price + 1.0, "low": price - 1.0,
            "close": price, "volume": 1000000.0,
            "pbr": pbr, "roe_or_gpa": 10.0,  # roe present so the loader skips network enrichment
        })
    pl.from_dicts(rows).write_parquet(str(path))


def test_delisted_value_stock_passes_pbr_filter_and_is_captured(tmp_path, monkeypatch):
    # Part B end-to-end: a value name (PBR <= 1) that has since delisted must be selectable
    # by a fundamental screen during its alive window — the case the old engine hid entirely.
    from engine import universe_pit
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    _write_fundamental_ohlcv(data_dir / "DEADVALUE.parquet", "2024-01-01", 8, 100.0, pbr=0.8)
    _write_fundamental_ohlcv(data_dir / "PRICEY.parquet", "2024-01-01", 20, 100.0, pbr=2.5)

    master_path = tmp_path / "stock-master.json"
    _write_master(master_path, [
        {"symbol": "DEADVALUE", "market": "KOSPI", "delistingDate": "2024-01-08",
         "shares": 1000, "dataStart": "2024-01-01", "dataEnd": "2024-01-08", "hasOhlcv": True},
        {"symbol": "PRICEY", "market": "KOSPI", "delistingDate": None,
         "shares": 1000, "dataStart": "2024-01-01", "dataEnd": "2024-01-20", "hasOhlcv": True},
    ])
    monkeypatch.setattr(universe_pit, "_MASTER_PATH", master_path)
    universe_pit.reload_master()

    engine = BacktestEngine(data_dir=str(data_dir))
    result = engine.run_backtest({
        "symbols": ["IGNORED"],
        "universe_id": "kospi",
        "entry": {"logic": "AND", "conditions": [{"id": "pbr", "params": {"operator": "<=", "value": 1.0}}]},
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 50, "liquidity_multiplier": 0, "max_positions": 10},
        "options": {"execution_type": "same_close"},
        "period": "FULL", "startDate": "2024-01-02", "endDate": "2024-01-20",
    })
    universe_pit.reload_master()

    traded = {s["symbol"] for s in result["signals"]}
    assert "DEADVALUE" in traded, "delisted value stock must be selectable by the PBR screen"
    assert "PRICEY" not in traded, "PBR>1 name must be filtered out"
    # and the delisted holding is liquidated at its delisting day
    sells = [s for s in result["signals"] if s["symbol"] == "DEADVALUE" and s["type"] == "sell"]
    assert sells and any(s.get("condition", "").startswith("상장폐지") for s in sells)


def test_unadjusted_split_does_not_trigger_fake_stop_loss(tmp_path):
    # 수정주가 가드: 소스가 미조정 정방향분할(÷10)을 주면 분할일이 -90%로 보여 손절이
    # 가짜로 발동한다. preprocess_data의 역조정 가드가 이를 연속 시계열로 만들어,
    # -12% 손절 전략이 분할에 걸려 가짜 손실을 내지 않아야 한다.
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    rows = []
    for i, date in enumerate(pd.date_range("2024-01-01", periods=40, freq="D")):
        raw = 1000 + i * 5          # 완만한 상승
        if i >= 20:
            raw = (1100 + (i - 20) * 5) / 10.0   # bar 20에서 ÷10 정방향분할(미조정)
        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": raw, "high": raw, "low": raw, "close": float(raw), "volume": 1000000.0,
        })
    pl.from_dicts(rows).write_parquet(str(data_dir / "SPLITCO.parquet"))

    engine = BacktestEngine(data_dir=str(data_dir))
    result = engine.run_backtest({
        "symbols": ["SPLITCO"],
        "entry": {"logic": "AND", "conditions": [{"id": "price", "params": {"value": 1, "operator": ">"}}]},
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "liquidity_multiplier": 0, "stop_loss_pct": 12},
        "options": {"execution_type": "same_close"},
        "period": "FULL", "startDate": "2024-01-02", "endDate": "2024-02-09",
    })

    sells = [s for s in result["signals"] if s["symbol"] == "SPLITCO" and s["type"] == "sell"]
    # 분할(미조정 -90%)이 손절을 발동시키면 안 된다
    assert not any("손절" in (s.get("condition") or "") for s in sells), \
        "back-adjustment should prevent the unadjusted split from faking a stop-loss"
