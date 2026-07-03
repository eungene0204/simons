"""백테스트 엔진 감사(2026-07) 수정 회귀 테스트.

시뮬레이터 레벨 수정(C1/C2/C5/C6/H3)은 test_engine_simulator.py에 있고,
여기는 엔진·통계 레벨 수정을 고정한다:

  - C3: Profit Factor 클램프/재정의 제거 — 계산값 그대로 보고
  - C4: 모멘텀 랭킹(진입조건 없음)이 유동성 게이트를 무효화하지 않음
  - H4: Sortino 표준 하방편차(전체 기간 target-below RMS)
  - H6: 지표 기간 기반 동적 warm-up 산정
  - 신규 통계: exposure / maxDrawdownDuration / expectancy / recoveryFactor
  - 공시 경고: 매도 거래세, 소표본(<30건)
"""
import os

import numpy as np
import pandas as pd
import polars as pl
import pytest

from backtest_engine import BacktestEngine, _max_indicator_period
from engine.simulator import Simulator
from engine.result_handler import ResultHandler

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

ZERO_COST = {"fee_rate": 0.0, "slippage_rate": 0.0, "sell_tax_rate": 0.0,
             "execution_type": "same_close"}


def _format_two_trade_result():
    """+100% 승리 1건, -1% 손실 1건 → PF ≈ 50 (>10)인 결과 dict 생성."""
    idx = pd.date_range("2024-01-01", periods=5)
    close = pd.DataFrame({"A": [100.0, 200.0, 100.0, 99.0, 99.0]}, index=idx)
    entries = pd.DataFrame({"A": [True, False, True, False, False]}, index=idx)
    exits = pd.DataFrame({"A": [False, True, False, True, False]}, index=idx)
    risk = {"init_cash": 10_000_000.0, "position_size_pct": 100.0,
            "skip_position_setting": True, "skip_risk_management": True}
    pf = Simulator().run(close, close, entries, exits, risk, dict(ZERO_COST))

    empty_reasons = {"A": pd.Series([None] * 5, index=idx)}
    return ResultHandler.format_results(
        pf, ["A"], {}, {}, empty_reasons, empty_reasons, idx,
        risk, "same_close", 10_000_000.0,
    )


def test_profit_factor_not_clamped():
    """C3: 소표본이라도 PF를 10으로 자르지 않고 계산값을 그대로 보고한다."""
    result = _format_two_trade_result()
    assert result["trades"] == 2
    assert result["profitFactor"] > 10.0


def test_new_statistics_present_and_sane():
    """Exposure/DD Duration/Expectancy/Recovery Factor가 계산되어야 한다."""
    result = _format_two_trade_result()

    assert 0.0 < result["exposure"] <= 100.0
    # d3(-1%)부터 마지막까지 수중(underwater) → 최소 1일 이상
    assert result["maxDrawdownDuration"] >= 1
    # (+100%, -1%)의 평균 거래 수익률 ≈ +49.5%
    assert result["expectancy"] == pytest.approx(49.5, abs=1.0)
    assert result["recoveryFactor"] > 0.0


def test_sortino_uses_full_period_downside_deviation():
    """H4: 하방편차는 전체 기간 min(r,0)의 RMS — 음수만의 std가 아니다."""
    result = _format_two_trade_result()
    # 수익 시계열이 전반적으로 양(+)이므로 Sortino > Sharpe (하방 변동이 작음)
    assert np.isfinite(result["sortino"])
    assert result["sortino"] > 0.0
    assert result["sortino"] > result["sharpe"]


def test_max_indicator_period_scans_conditions():
    """H6: 조건 트리에서 최대 지표 기간을 찾아 warm-up을 동적으로 늘린다."""
    entry = {"conditions": [
        {"id": "ma_crossover", "params": {"shortMA": 50, "longMA": 300}},
        {"id": "rsi", "params": {"period": 14}},
    ]}
    exit_ = {"conditions": [
        {"id": "breakout", "params": {"lookbackPeriod": 252}, "type": "filter"},
    ]}
    assert _max_indicator_period(entry, exit_) == 300
    assert _max_indicator_period(exit_) == 252
    assert _max_indicator_period(None, {}) == 0


def _write_parquet(name: str, rows: list[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    pl.from_dicts(rows).write_parquet(os.path.join(DATA_DIR, f"{name}.parquet"))


def _ohlcv_row(date, price, volume):
    return {"date": date.strftime("%Y-%m-%d"), "open": float(price),
            "high": float(price * 1.01), "low": float(price * 0.99),
            "close": float(price), "volume": float(volume)}


def test_momentum_ranking_respects_liquidity_gate():
    """C4: 진입조건 없는 모멘텀 랭킹이 유동성 게이트를 덮어쓰지 않는다.

    ILLIQ는 모멘텀 1위이지만 초반 유동성 미달 → 유동성이 확보되는 날짜 이전에는
    절대 매수되면 안 된다. (수정 전에는 available&valid로 덮어써 즉시 매수됨.)
    """
    dates = pd.date_range("2024-01-02", periods=40, freq="B")
    liquid_from = 30  # ILLIQ의 유동성 확보 시점 (인덱스)

    # LIQ: 완만한 상승 + 풍부한 거래대금 (10,000원 × 1e9주 규모)
    _write_parquet("AUDIT_LIQ", [
        _ohlcv_row(d, 10_000 * (1.001 ** i), 1_000_000) for i, d in enumerate(dates)
    ])
    # ILLIQ: 급등(모멘텀 1위)이지만 초반 거래대금이 거의 없음
    _write_parquet("AUDIT_ILLIQ", [
        _ohlcv_row(d, 10_000 * (1.05 ** i), 10 if i < liquid_from else 1_000_000)
        for i, d in enumerate(dates)
    ])

    engine = BacktestEngine(data_dir=DATA_DIR)
    req = {
        "symbols": ["AUDIT_LIQ", "AUDIT_ILLIQ"],
        "entry": {"logic": "OR", "conditions": []},
        "exit": {"logic": "OR", "conditions": []},
        "risk": {
            "init_cash": 10_000_000.0,
            "position_size_pct": 100,
            "max_positions": 1,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "liquidity_limit_pct": 10.0,
        },
        "options": {"execution_type": "same_close"},
        "period": "FULL",
    }
    result = engine.run_backtest(req)

    illiq_buys = [s for s in result["signals"]
                  if s["symbol"] == "AUDIT_ILLIQ" and s["type"] == "buy"]
    first_liquid_date = dates[liquid_from + 1].strftime("%Y-%m-%d")
    for sig in illiq_buys:
        assert sig["date"] >= first_liquid_date, (
            f"유동성 미달 기간에 ILLIQ 매수 발생: {sig['date']}"
        )


def test_engine_discloses_sell_tax_and_small_sample():
    """공시 경고: 기본 매도 거래세 반영·소표본 통계 경고가 결과에 포함된다."""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    prices = [100.0] + [110.0] * 29
    _write_parquet("AUDIT_WARN", [
        _ohlcv_row(d, p, 1_000_000) for d, p in zip(dates, prices)
    ])

    engine = BacktestEngine(data_dir=DATA_DIR)
    req = {
        "symbols": ["AUDIT_WARN"],
        "entry": {"logic": "AND",
                  "conditions": [{"id": "price", "params": {"value": 105, "operator": "<"}}]},
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100, "max_holding_days": 5,
                 "liquidity_multiplier": 0},
        "options": {"execution_type": "same_close"},
        "period": "FULL",
    }
    result = engine.run_backtest(req)

    warnings_text = " ".join(result.get("warnings", []))
    assert "증권거래세" in warnings_text
    assert "30건 미만" in warnings_text
