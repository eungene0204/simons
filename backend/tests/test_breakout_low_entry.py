"""신저가 돌파 조건(엔진 v16.41) 회귀.

2026-10-18 발견: 속설 검증 #15('52주 신저가 종목 매수')를 돌리자 신고가 돌파(breakout)가 매수=상향·
매도=하향으로 방향이 역할에 묶여 있어 신저가 진입이 '진입 신호로 표현할 수 없습니다'로 거절됐고,
레지스트리도 신저가를 미지원 개념으로 두었다. 방향을 개념 ID(technical.breakout_low)에 담아 지원한다.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from engine.nl_parser import TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition
from strategy_conversation.compiler.strategy_compiler import StrategyCompileError, _compile_condition
from strategy_conversation.compiler.strategy_decompiler import _decompile_technical
from strategy_conversation.interpreter.models import StrategyCondition
from strategy_conversation.registry.indicator_registry import REGISTRY, resolve


def _cond(factor, operator=None, **params):
    return StrategyCondition(factor=factor, operator=operator, value=None,
                             parameters=params, source_text="인용")


def _frame(n=300, period=20, seed=11):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 2, n))
    high, low = close + rng.uniform(0.5, 2, n), close - rng.uniform(0.5, 2, n)
    s_high, s_low = pl.Series(high), pl.Series(low)
    return pl.DataFrame({
        "close": close, "high": high, "low": low,
        f"high_{period}_max": s_high.rolling_max(window_size=period, min_samples=1),
        f"low_{period}_min": s_low.rolling_min(window_size=period, min_samples=1),
    })


def _engine_cond(**params):
    return {"type": "indicator", "id": "breakout", "params": {"lookbackPeriod": 20, **params}}


# ── 엔진 ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", [
    {"signalType": "buy"}, {"signalType": "sell"},
    {"signalType": "buy", "side": "low"}, {"signalType": "sell", "side": "low"},
])
def test_vector_and_row_evaluators_agree(params):
    df = _frame()
    engine = SignalEngine()
    cond = _engine_cond(**params)
    vec = engine._eval_vec(cond, df)
    row = np.array([engine.evaluate_condition(cond, i, df) for i in range(len(df))])
    # 행 평가기는 워밍업(idx < period)을 거르고 벡터 평가기는 거르지 않는다 — 기존 동작이라 이후 구간만 대조한다.
    assert (vec[20:] == row[20:]).all()


def test_buy_with_side_low_fires_on_new_low_not_new_high():
    df = _frame()
    engine = SignalEngine()
    low_buy = engine._eval_vec(_engine_cond(signalType="buy", side="low"), df)
    high_buy = engine._eval_vec(_engine_cond(signalType="buy"), df)
    sell = engine._eval_vec(_engine_cond(signalType="sell"), df)
    assert low_buy.any() and high_buy.any()
    assert (low_buy == sell).all()                  # 신저가 사건은 역할과 무관하게 같다
    assert not (low_buy & high_buy).any()           # 신고가 돌파와 같은 날이 아니다
    low, prev_min = df["low"].to_numpy(), df["low_20_min"].to_numpy()
    assert (low[1:][low_buy[1:]] < prev_min[:-1][low_buy[1:]]).all()


# ── 컴파일·되짚기 ─────────────────────────────────────────────────────────────

def test_registry_supports_breakout_low_and_alias():
    spec = REGISTRY.get("technical.breakout_low")
    assert spec is not None and spec.supported == "SUPPORTED"
    assert spec.engine_binding == ("technical_signal", "breakout")
    assert resolve("신저가").id == "technical.breakout_low"
    assert REGISTRY.get("unsupported.new_low") is None


def test_entry_compiles_to_buy_signal_with_side_low():
    target, sig = _compile_condition(_cond("technical.breakout_low", lookback_period=252), "entry")
    assert target == "entry_signals"
    assert (sig.indicator, sig.signal_type, sig.side, sig.lookback_period) == ("breakout", "buy", "low", 252)
    params = _tech_signal_to_condition(sig)["params"]
    assert params["side"] == "low" and params["lookbackPeriod"] == 252 and params["signalType"] == "buy"


def test_high_breakout_request_is_unchanged_without_side():
    sig = TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=20)
    assert "side" not in _tech_signal_to_condition(sig)["params"]


def test_exit_compiles_to_sell_signal_with_side_low():
    target, sig = _compile_condition(_cond("technical.breakout_low", lookback_period=20), "exit")
    assert target == "exit_signals" and (sig.signal_type, sig.side) == ("sell", "low")


def test_new_high_breakout_with_crosses_below_entry_still_rejected():
    with pytest.raises(StrategyCompileError):
        _compile_condition(_cond("technical.breakout", "crosses_below", lookback_period=20), "entry")


def test_decompile_roundtrip_keeps_low_side():
    sig = TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=252, side="low")
    cond = _decompile_technical(sig)
    assert (cond.factor, cond.operator) == ("technical.breakout_low", None)
    assert cond.parameters["lookback_period"] == 252
    _, again = _compile_condition(cond, "entry")
    assert again.side == "low" and again.lookback_period == 252


# ── 프롬프트 계약 ──────────────────────────────────────────────────────────────

def test_prompt_lists_breakout_low_and_no_longer_calls_new_low_unsupported():
    from strategy_conversation.interpreter.prompts import build_system_prompt

    prompt = build_system_prompt()
    assert "technical.breakout_low" in prompt
    assert "고정 현금 비중, 신저가" not in prompt          # 미지원 목록에서 빠졌다
    assert "unsupported.new_low" not in prompt


def test_prompt_maps_after_n_days_sell_to_hold_period_not_min_hold():
    """2026-10-18: '매수 후 20거래일이 지나면 매도'가 min_hold_period_days(최소 보유)로 읽혀 청산이 비었다."""
    from strategy_conversation.interpreter.prompts import build_system_prompt

    prompt = build_system_prompt()
    assert "지나면 매도/정리" in prompt and "min_hold_period_days 아님" in prompt
