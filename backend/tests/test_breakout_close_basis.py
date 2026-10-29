"""종가 기준 돌파(엔진 v16.44) 회귀.

2026-10-29 발견: 뉴스 전략 테스트에서 '종가가 20일 신고가를 돌파하면 매수'가 고가 기준 돌파
(오늘 고가 > 직전 20일 최고 고가)로 백테스트됐다. 인터프리터는 technical.breakout(lookback_period=20)을
옳게 냈지만 형태에 가격 기준 자리가 없었다. 사용자 결정: 종가 기준 = 오늘 종가 > 직전 N일 최고 종가
(신저가는 최저 종가), 기준을 말하지 않으면 종전대로 고가·저가 기준.
"""

from __future__ import annotations

import json

import numpy as np
import polars as pl
import pytest

from engine.nl_parser import TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition
from strategy_conversation.compiler.strategy_compiler import _compile_condition
from strategy_conversation.compiler.strategy_decompiler import _decompile_technical
from strategy_conversation.interpreter import breakout_basis_check as basis_check
from strategy_conversation.interpreter.models import StrategyCondition, StrategyIntent


def _cond(factor, operator=None, source_text="인용", **params):
    return StrategyCondition(factor=factor, operator=operator, value=None,
                             parameters=params, source_text=source_text)


def _frame(n=300, period=20, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 2, n))
    high, low = close + rng.uniform(0.5, 2, n), close - rng.uniform(0.5, 2, n)
    s_high, s_low, s_close = pl.Series(high), pl.Series(low), pl.Series(close)
    return pl.DataFrame({
        "close": close, "high": high, "low": low,
        f"high_{period}_max": s_high.rolling_max(window_size=period, min_samples=1),
        f"low_{period}_min": s_low.rolling_min(window_size=period, min_samples=1),
        f"close_{period}_max": s_close.rolling_max(window_size=period, min_samples=1),
        f"close_{period}_min": s_close.rolling_min(window_size=period, min_samples=1),
    })


def _engine_cond(**params):
    return {"type": "indicator", "id": "breakout", "params": {"lookbackPeriod": 20, **params}}


# ── 엔진 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", [
    {"signalType": "buy", "priceBasis": "close"}, {"signalType": "sell", "priceBasis": "close"},
    {"signalType": "buy", "side": "low", "priceBasis": "close"},
])
def test_vector_and_row_evaluators_agree(params):
    df = _frame()
    engine = SignalEngine()
    cond = _engine_cond(**params)
    vec = engine._eval_vec(cond, df)
    row = np.array([engine.evaluate_condition(cond, i, df) for i in range(len(df))])
    assert (vec[20:] == row[20:]).all()


def test_close_basis_buy_compares_close_with_prior_highest_close():
    df = _frame()
    engine = SignalEngine()
    close_buy = engine._eval_vec(_engine_cond(signalType="buy", priceBasis="close"), df)
    high_buy = engine._eval_vec(_engine_cond(signalType="buy"), df)
    close, prev_max = df["close"].to_numpy(), df["close_20_max"].to_numpy()
    expected = np.zeros(len(df), dtype=bool)
    expected[1:] = close[1:] > prev_max[:-1]
    assert close_buy.any() and (close_buy == expected).all()
    assert not (close_buy == high_buy).all()        # 고가 기준과 다른 신호다


def test_close_basis_low_side_compares_close_with_prior_lowest_close():
    df = _frame()
    res = SignalEngine()._eval_vec(_engine_cond(signalType="sell", priceBasis="close"), df)
    close, prev_min = df["close"].to_numpy(), df["close_20_min"].to_numpy()
    expected = np.zeros(len(df), dtype=bool)
    expected[1:] = close[1:] < prev_min[:-1]
    assert res.any() and (res == expected).all()


def test_indicator_engine_builds_close_extreme_columns():
    from engine.indicators import IndicatorEngine

    df = _frame().select("close", "high", "low").with_columns(
        pl.lit(1.0).alias("open"), pl.lit(1000.0).alias("volume"))
    out = IndicatorEngine.calculate(df, [_engine_cond(signalType="buy", priceBasis="close")])
    assert {"close_20_max", "close_20_min"} <= set(out.columns)
    plain = IndicatorEngine.calculate(df, [_engine_cond(signalType="buy")])
    assert "close_20_max" not in plain.columns     # 기준 없는 전략은 열도 요청도 그대로


def test_trade_reason_wraps_breakout_with_close_basis():
    from engine import trade_reason as tr

    engine = SignalEngine()
    segs = engine._base_condition_segments(_engine_cond(signalType="buy", priceBasis="close"))
    assert segs == [{"t": tr.CLOSE_BASIS, "a": [{"t": tr.BREAKOUT_HIGH, "a": [20]}]}]
    assert engine._base_condition_segments(_engine_cond(signalType="buy")) == [{"t": tr.BREAKOUT_HIGH, "a": [20]}]


# ── 컴파일·되짚기·검증 ────────────────────────────────────────────────────────

def test_close_basis_compiles_to_engine_param():
    _, sig = _compile_condition(_cond("technical.breakout", "crosses_above",
                                      lookback_period=20, price_basis="close"), "entry")
    assert (sig.indicator, sig.signal_type, sig.price_basis) == ("breakout", "buy", "close")
    params = _tech_signal_to_condition(sig)["params"]
    assert params["priceBasis"] == "close" and params["lookbackPeriod"] == 20


def test_breakout_without_basis_request_is_unchanged():
    sig = TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=20)
    assert "priceBasis" not in _tech_signal_to_condition(sig)["params"]


def test_decompile_roundtrip_keeps_close_basis():
    sig = TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=20, price_basis="close")
    cond = _decompile_technical(sig)
    assert cond.parameters["price_basis"] == "close"
    _, again = _compile_condition(cond, "entry")
    assert again.price_basis == "close"


def test_low_breakout_compiles_with_close_basis():
    _, sig = _compile_condition(_cond("technical.breakout_low", lookback_period=20,
                                      price_basis="close"), "entry")
    assert (sig.side, sig.price_basis) == ("low", "close")


def _validate(cond):
    from strategy_conversation.validation.capability_validator import validate_capability

    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY",
        "strategy": {"universe": {"markets": ["KOSPI"]}, "entry_conditions": [cond.model_dump()]},
    })
    validate_capability(intent)
    return intent.strategy.entry_conditions[0]


def test_capability_validator_keeps_close_basis_on_breakout_only():
    kept = _validate(_cond("technical.breakout", "crosses_above", lookback_period=20, price_basis="close"))
    assert kept.parameters.get("price_basis") == "close"
    dropped = _validate(_cond("technical.rsi", "<", period=14, price_basis="close"))
    assert "price_basis" not in dropped.parameters
    odd = _validate(_cond("technical.breakout", "crosses_above", lookback_period=20, price_basis="high"))
    assert "price_basis" not in odd.parameters


# ── 전용 판정 ─────────────────────────────────────────────────────────────────

class _Strategy:
    def __init__(self, entry, exit_=()):
        self.entry_conditions, self.exit_conditions = list(entry), list(exit_)


def test_targets_are_breakout_conditions_without_basis():
    breakout = _cond("technical.breakout", "crosses_above", lookback_period=20)
    already = _cond("technical.breakout", "crosses_above", lookback_period=60, price_basis="close")
    rsi = _cond("technical.rsi", "<", period=14)
    low = _cond("technical.breakout_low", lookback_period=20)
    targets = basis_check.conditions_to_check(_Strategy([breakout, already, rsi], [low]))
    assert targets == [breakout, low]


def test_close_verdict_marks_condition_and_others_leave_it():
    a = _cond("technical.breakout", "crosses_above", lookback_period=20, source_text="종가가 20일 신고가를 돌파")
    b = _cond("technical.breakout", "crosses_below", lookback_period=20, source_text="20일 저점 이탈")
    chat = lambda system, user, **kw: json.dumps({"items": [{"basis": "close"}, {"basis": "unspecified"}]})
    pairs = basis_check.check_breakout_basis("문장", [a, b], chat)
    assert basis_check.apply_verdicts(pairs) == [a]
    assert a.parameters["price_basis"] == "close" and "price_basis" not in b.parameters


@pytest.mark.parametrize("raw", [
    "not json", json.dumps({"items": []}), json.dumps({"items": [{"basis": "maybe"}]}),
])
def test_failures_and_unknown_enum_leave_condition_untouched(raw):
    cond = _cond("technical.breakout", "crosses_above", lookback_period=20)
    pairs = basis_check.check_breakout_basis("문장", [cond], lambda *a, **k: raw)
    basis_check.apply_verdicts(pairs)
    assert "price_basis" not in cond.parameters


def test_primary_resolver_skips_without_targets_and_marks_with_close():
    from strategy_conversation.primary import _resolve_breakout_price_basis

    calls = []

    def chat(system, user, **kw):
        calls.append(user)
        return json.dumps({"items": [{"basis": "close"}]})

    class _Intent:
        strategy = _Strategy([_cond("technical.rsi", "<", period=14)])
    _resolve_breakout_price_basis(_Intent(), "문장", chat)
    assert calls == []

    cond = _cond("technical.breakout", "crosses_above", lookback_period=20)

    class _Intent2:
        strategy = _Strategy([cond])
    _resolve_breakout_price_basis(_Intent2(), "문장", chat)
    assert len(calls) == 1 and cond.parameters["price_basis"] == "close"
