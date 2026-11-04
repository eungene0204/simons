"""변동성 돌파 체결(엔진 v16.46) — 시가 + 전일 고저폭 × k에 고가가 닿은 날 그 가격에 사고, 다음 거래일 시가에 판다.

설정이 없는 전략은 종전 경로 그대로다(기존 시뮬레이터 회귀 테스트가 그 계약을 지킨다).
"""

from __future__ import annotations

import pandas as pd
import pytest

from engine import trade_reason as tr
from engine.nl_parser import ParsedStrategy
from engine.simulator import Simulator
from engine.strategy_converter import to_backtest_request

_NEXT = {"execution_type": "next_open", "fee_rate": 0, "slippage_rate": 0, "sell_tax_rate": 0}
_CASH = 10_000_000.0


def _bars():
    idx = pd.bdate_range("2024-01-01", periods=5)
    frame = lambda v: pd.DataFrame({"A": v}, index=idx)  # noqa: E731
    open_ = frame([100.0, 100.0, 100.0, 105.0, 100.0])
    high = frame([102.0, 104.0, 112.0, 110.0, 101.0])
    low = frame([98.0, 96.0, 99.0, 100.0, 99.0])
    close = frame([101.0, 101.0, 108.0, 106.0, 100.0])
    ents = frame([True] * 5)
    exts = frame([False] * 5)
    return idx, open_, high, low, close, ents, exts


def _orders(pf):
    return pf.orders.records_readable


def test_breakout_buys_at_target_and_sells_next_open():
    _, open_, high, low, close, ents, exts = _bars()
    risk = {"max_positions": 1, "init_cash": _CASH, "volatility_breakout_k": 0.5}
    sim = Simulator()
    pf = sim.run(close, open_, ents, exts, risk, _NEXT, high_df=high, low_df=low)
    orders = _orders(pf)
    # 1일: 전일 고저폭 4 × 0.5 → 돌파가 102, 고가 104가 닿아 102에 매수. 2일 시가 100에 매도.
    # 3일: 돌파가 105 + 13 × 0.5 = 111.5 > 고가 110, 4일: 100 + 5 = 105 > 고가 101 — 매수 없음.
    assert list(orders["Side"]) == ["Buy", "Sell"]
    assert float(orders.iloc[0]["Price"]) == pytest.approx(102.0)
    assert float(orders.iloc[1]["Price"]) == pytest.approx(100.0)
    assert orders.iloc[0]["Timestamp"] == close.index[1]
    assert orders.iloc[1]["Timestamp"] == close.index[2]
    reasons = [r for by in sim.entry_reason_overrides.values() for r in by.values()]
    assert any(tr.VOLATILITY_BREAKOUT_BUY in r for r in reasons)
    exit_reasons = [r for by in sim.exit_reason_overrides.values() for r in by.values()]
    assert any(tr.VOLATILITY_BREAKOUT_EXIT in r for r in exit_reasons)


def test_breakout_waits_when_prior_day_was_not_tradable():
    _, open_, high, low, close, ents, exts = _bars()
    avail = pd.DataFrame({"A": [False, True, True, True, True]}, index=close.index)
    risk = {"max_positions": 1, "init_cash": _CASH, "volatility_breakout_k": 0.5}
    pf = Simulator().run(close, open_, ents, exts, risk, _NEXT, high_df=high, low_df=low, available_df=avail)
    # 전일(0일)이 거래 불가라 1일엔 사지 않는다. 2일: 100 + 8 × 0.5 = 104 ≤ 고가 112 → 104에 매수, 3일 시가 105에 매도.
    orders = _orders(pf)
    assert list(orders["Side"]) == ["Buy", "Sell"]
    assert orders.iloc[0]["Timestamp"] == close.index[2]
    assert float(orders.iloc[0]["Price"]) == pytest.approx(104.0)


def test_without_breakout_setting_entry_fills_at_open():
    _, open_, high, low, close, ents, exts = _bars()
    risk = {"max_positions": 1, "init_cash": _CASH}
    orders = _orders(Simulator().run(close, open_, ents, exts, risk, _NEXT, high_df=high, low_df=low))
    assert float(orders.iloc[0]["Price"]) == pytest.approx(100.0)
    assert orders.iloc[0]["Timestamp"] == close.index[0]


def test_converter_carries_breakout_k_into_request():
    req = to_backtest_request(ParsedStrategy(universe=["KOSPI"], volatility_breakout_k=0.5))
    assert req["risk"]["volatility_breakout_k"] == 0.5
    plain = to_backtest_request(ParsedStrategy(universe=["KOSPI"]))
    assert plain["risk"]["volatility_breakout_k"] is None
    # 설정이 없으면 정본 DSL에서 빠져 기존 전략의 식별값이 바뀌지 않는다.
    assert "volatility_breakout_k" not in plain["canonical_strategy_dsl"]
    assert plain["strategy_id"] == to_backtest_request(ParsedStrategy(universe=["KOSPI"]))["strategy_id"]
