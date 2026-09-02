"""2026-09-02 편향 감사(생존편향·룩어헤드·비용·과최적화) 수리 회귀.

각 테스트는 감사에서 실측된 결함 하나를 재현한다 — 수리 전에는 실패해야 하는 케이스다.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest

from backtest_engine import BacktestEngine, _ai_model_val_end
from engine import universe_pit
from engine.loader import DataLoader


def _write(path: Path, dates, closes, volumes=None, market_cap=None):
    n = len(dates)
    closes = list(map(float, closes))
    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": closes, "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": volumes if volumes is not None else [1_000_000] * n,
        "roe_or_gpa": [0.1] * n, "pbr": [1.0] * n, "per": [10.0] * n,
    })
    if market_cap is not None:
        df["market_cap"] = market_cap
    df.to_parquet(path)


def _buy_and_hold_req(symbols, **extra):
    req = {
        "symbols": symbols, "universe_id": None, "period": "FULL",
        "entry": {"logic": "OR", "conditions": [
            {"id": "price", "type": "signal", "params": {"operator": ">", "value": 1}},
        ]},
        "exit": {"logic": "OR", "conditions": []},
        "risk_params": {"init_cash": 10_000_000.0, "max_positions": 2,
                        "skip_risk_management": True},
        "options": {"execution_type": "next_open"},
    }
    req.update(extra)
    return req


# ── 1. 정지 꼬리로 끝나는 상폐 종목의 강제청산 ─────────────────────────────────

def test_frozen_tail_forced_exit_is_not_masked_by_halt_guard(tmp_path):
    """마지막 5봉이 거래량 0(정지)으로 끝나는 종목: 강제청산이 정지 마스크에 지워져
    백테스트 끝까지 동결가로 남던 결함 — 마지막 실봉에서 정산돼야 한다."""
    active = pd.bdate_range("2024-01-02", periods=30)
    dead = pd.bdate_range("2024-01-02", periods=15)     # 2024-01-22에 데이터 종료
    dead_vol = [1_000_000] * 10 + [0] * 5               # 마지막 5봉 정지
    _write(tmp_path / "ACTIVE.parquet", active, [100 + i for i in range(30)])
    _write(tmp_path / "DEADCO.parquet", dead, [100] * 10 + [100] * 5, dead_vol)

    result = BacktestEngine(data_dir=str(tmp_path)).run_backtest(
        _buy_and_hold_req(["ACTIVE", "DEADCO"]))

    dead_sells = [s for s in result["signals"] if s["symbol"] == "DEADCO" and s["type"] == "sell"]
    assert [s for s in result["signals"] if s["symbol"] == "DEADCO" and s["type"] == "buy"], \
        "정지 전에 매수가 있어야 테스트가 유효하다"
    assert dead_sells, "정지 꼬리 종목도 강제청산돼야 한다"
    assert max(s["date"] for s in dead_sells) == dead[-1].strftime("%Y-%m-%d"), \
        "강제청산은 그 종목의 마지막 봉에 집행돼야 한다(백테스트 종료일이 아니다)"
    assert not any(s.get("condition", "").startswith("백테스트 종료") for s in dead_sells)


# ── 2. 미국 종목엔 한국 가격제한 기반 역보정을 적용하지 않는다 ────────────────

def test_loader_flag_disables_corporate_action_sanitizer():
    closes = [100.0] * 20 + [50.0] * 20      # 지속되는 -50% 갭
    df = pl.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-02", periods=40)],
        "open": closes, "high": closes, "low": closes, "close": closes, "volume": [1e6] * 40,
    })
    loader = DataLoader(data_dir="/nonexistent")
    kept = loader.preprocess_data(df, sanitize_corporate_actions=False)
    erased = loader.preprocess_data(df, sanitize_corporate_actions=True)
    assert kept["close"].iloc[0] == pytest.approx(100.0) and kept["close"].iloc[-1] == pytest.approx(50.0)
    assert erased["close"].iloc[0] == pytest.approx(50.0), "한국 경로는 종전대로 과거를 역보정한다"


def test_us_symbol_keeps_real_gap_kr_symbol_still_sanitized(tmp_path):
    """같은 -50% 지속 갭: 미국 티커는 손실로 남고, 한국 종목은 역보정으로 지워진다(종전 동작)."""
    dates = pd.bdate_range("2024-01-02", periods=40)
    closes = [100.0] * 20 + [50.0] * 20
    _write(tmp_path / "GAPCO.parquet", dates, closes)     # 미국 티커 형태
    _write(tmp_path / "000001.parquet", dates, closes)    # 한국 코드 형태
    engine = BacktestEngine(data_dir=str(tmp_path))

    us_req, kr_req = _buy_and_hold_req(["GAPCO"]), _buy_and_hold_req(["000001"])
    us_req["risk_params"]["max_positions"] = kr_req["risk_params"]["max_positions"] = 1
    us = engine.run_backtest(us_req)
    kr = engine.run_backtest(kr_req)

    assert us["totalReturn"] < -40, "미국 종목의 실제 갭 손실이 결과에 남아야 한다"
    assert kr["totalReturn"] > -10, "한국 종목은 가격제한 초과 점프를 코퍼레이트 액션으로 역보정한다"
    assert any("상장폐지 종목의 가격 이력이 없습니다" in w for w in us["warnings"]), \
        "미국 지정 종목 경로에도 생존 편향 고지가 붙어야 한다"


# ── 3. 거래 비용 옵션 ────────────────────────────────────────────────────────

def test_negative_cost_is_rejected(tmp_path):
    _write(tmp_path / "000100.parquet", pd.bdate_range("2024-01-02", periods=20), [100 + i for i in range(20)])
    req = _buy_and_hold_req(["000100"], options={"execution_type": "next_open", "fee_rate": -0.001})
    with pytest.raises(ValueError, match="음수"):
        BacktestEngine(data_dir=str(tmp_path)).run_backtest(req)


def test_zero_cost_is_disclosed(tmp_path):
    _write(tmp_path / "000100.parquet", pd.bdate_range("2024-01-02", periods=20), [100 + i for i in range(20)])
    req = _buy_and_hold_req(["000100"], options={"execution_type": "next_open",
                                                  "fee_rate": 0.0, "slippage_rate": 0.0})
    result = BacktestEngine(data_dir=str(tmp_path)).run_backtest(req)
    assert any("수수료와 슬리피지가 모두 0" in w for w in result["warnings"])


def test_sell_tax_schedule_is_disclosed(tmp_path):
    """sell_tax_rate 미명시 → 시행일 스케줄 적용 사실을 고지한다(구간이 세율 경계를 걸치면 범위)."""
    dates = pd.bdate_range("2018-12-03", "2019-06-28")
    _write(tmp_path / "000100.parquet", dates, [100 + i * 0.1 for i in range(len(dates))])
    result = BacktestEngine(data_dir=str(tmp_path)).run_backtest(_buy_and_hold_req(["000100"]))
    assert any("시행일 기준 세율(0.30%→0.25%" in w for w in result["warnings"]), result["warnings"]


# ── 4. 지수 유니버스 상위 N = 일별 실측 시가총액 ─────────────────────────────

def test_index_top_n_ranks_by_pit_market_cap_not_static_shares(tmp_path, monkeypatch):
    dates = pd.bdate_range("2024-01-02", periods=30)
    n = len(dates)
    # 정적 주식수로는 A가 크지만(1e9주 vs 1주), 실측 시총은 B가 크다.
    _write(tmp_path / "000100.parquet", dates, [100] * n, market_cap=[10.0] * n)
    _write(tmp_path / "000200.parquet", dates, [100] * n, market_cap=[1000.0] * n)
    monkeypatch.setattr(universe_pit, "get_shares", lambda syms: {"000100": 1e9, "000200": 1.0})
    monkeypatch.setattr(universe_pit, "parse_universe_markets", lambda uid: (["KOSPI"], 1))
    monkeypatch.setattr(universe_pit, "resolve_symbols", lambda uid, s, e: [])

    req = _buy_and_hold_req(["000100", "000200"], universe_id="kospi200")
    req["risk_params"]["max_positions"] = 2
    result = BacktestEngine(data_dir=str(tmp_path)).run_backtest(req)

    bought = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    assert bought == {"000200"}, f"실측 시총 상위 1 = BBBBBB 만 편입돼야 한다: {bought}"
    assert any("일별 실측 시가총액 순위" in w for w in result["warnings"])


def test_index_top_n_falls_back_to_static_shares_without_market_cap(tmp_path, monkeypatch):
    dates = pd.bdate_range("2024-01-02", periods=30)
    n = len(dates)
    _write(tmp_path / "000100.parquet", dates, [100] * n)
    _write(tmp_path / "000200.parquet", dates, [100] * n)
    monkeypatch.setattr(universe_pit, "get_shares", lambda syms: {"000100": 1e9, "000200": 1.0})
    monkeypatch.setattr(universe_pit, "parse_universe_markets", lambda uid: (["KOSPI"], 1))
    monkeypatch.setattr(universe_pit, "resolve_symbols", lambda uid, s, e: [])

    result = BacktestEngine(data_dir=str(tmp_path)).run_backtest(
        _buy_and_hold_req(["000100", "000200"], universe_id="kospi200"))
    bought = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    assert bought == {"000100"}
    assert any("현재 상장주식수 × 과거 주가의 근사" in w for w in result["warnings"])


# ── 5. 상폐 이력 하한 이전 구간 고지 ─────────────────────────────────────────

def test_kr_market_universe_warns_before_delisting_floor(tmp_path, monkeypatch):
    data_dir = tmp_path / "ohlcv"; data_dir.mkdir()
    dates = pd.bdate_range("2014-01-02", periods=40)
    _write(data_dir / "000100.parquet", dates, [100 + i for i in range(40)])
    master = tmp_path / "stock-master.json"
    master.write_text(json.dumps({"delistingFloor": "2015-01-01", "stocks": [
        {"symbol": "000100", "market": "KOSPI", "delistingDate": None, "shares": 1000,
         "dataStart": "2014-01-02", "dataEnd": "2026-01-01", "hasOhlcv": True},
    ]}), encoding="utf-8")
    monkeypatch.setattr(universe_pit, "_MASTER_PATH", master)
    universe_pit.reload_master()
    try:
        req = _buy_and_hold_req(["IGNORED"], universe_id="kospi",
                                startDate="2014-01-02", endDate="2014-02-28")
        result = BacktestEngine(data_dir=str(data_dir)).run_backtest(req)
    finally:
        universe_pit.reload_master()
    assert any("상장폐지 종목 이력은 2015-01-01부터" in w for w in result["warnings"]), result["warnings"]


# ── 6. AI 검증 구간 종료일 파싱 ──────────────────────────────────────────────

def test_ai_model_val_end_parses_range():
    assert _ai_model_val_end({"val_range": "2023-01-21 ~ 2024-07-01"}) == "2024-07-01"
    assert _ai_model_val_end({"val_range": ""}) is None
    assert _ai_model_val_end({}) is None
