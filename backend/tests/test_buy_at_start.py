"""시작일 매수(엔진 v16.45) 회귀.

2026-10-29 사용자 지시: 고정 종목 묶음을 백테스트 시작일에 사서 끝까지 보유하는 규칙이 없어
(신호 없이 보유만 하는 전략) 뉴스 기반 '주요 금융 5곳 보유' 시험이 불가능했다.
규칙: 창 첫 봉에 매수 신호 하나, 청산 없음(마지막 날 강제 정산은 엔진 기존 동작).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from engine import trade_reason as tr
from engine.nl_parser import TechnicalSignal
from engine.phase1 import _has_buy_at_start, _window_start_flags
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition
from engine.strategy_slots import EXIT, _decided, has_buy_at_start
from strategy_conversation.compiler.strategy_compiler import StrategyCompileError, _compile_condition
from strategy_conversation.interpreter.models import StrategyCondition


def _cond(factor="technical.buy_at_start", operator=None, **params):
    return StrategyCondition(factor=factor, operator=operator, value=None,
                             parameters=params, source_text="시작일에 바로 매수")


ENGINE_COND = {"type": "indicator", "id": "buy_at_start", "params": {"signalType": "buy"}}


def test_window_start_flags_marks_first_window_bar():
    flags = _window_start_flags(10, 3)
    assert flags.tolist() == [0, 0, 0, 1, 0, 0, 0, 0, 0, 0]


def test_window_start_flags_without_prebars_uses_second_bar():
    # 유동성 게이트가 전일 거래대금을 보므로 첫 봉은 항상 막힌다 — 둘째 봉
    assert _window_start_flags(5, 0).tolist() == [0, 1, 0, 0, 0]


def test_window_start_flags_tiny_frame_has_no_flag():
    assert not _window_start_flags(1, 0).any()


def test_has_buy_at_start_reads_engine_entry_group():
    assert _has_buy_at_start({"conditions": [ENGINE_COND]})
    assert not _has_buy_at_start({"conditions": [{"id": "rsi"}]})
    assert not _has_buy_at_start(None)


def test_vector_and_row_evaluators_agree_on_window_start_column():
    flags = _window_start_flags(8, 2)
    df = pl.DataFrame({"close": np.arange(8, dtype=float), "__window_start": flags})
    engine = SignalEngine()
    vec = engine._eval_vec(ENGINE_COND, df)
    row = np.array([engine.evaluate_condition(ENGINE_COND, i, df) for i in range(len(df))])
    assert vec.tolist() == row.tolist() == [False, False, True, False, False, False, False, False]


def test_missing_window_start_column_never_fires():
    df = pl.DataFrame({"close": [1.0, 2.0, 3.0]})
    assert not SignalEngine()._eval_vec(ENGINE_COND, df).any()


def test_reason_is_start_day_buy():
    reasons = SignalEngine()._base_condition_segments(ENGINE_COND)
    assert reasons == [tr.part(tr.BUY_AT_START)]


def test_compiles_to_buy_only_signal_without_params():
    _, sig = _compile_condition(_cond(), "entry")
    assert (sig.indicator, sig.signal_type) == ("buy_at_start", "buy")
    assert _tech_signal_to_condition(sig)["id"] == "buy_at_start"


def test_exit_slot_refuses_buy_at_start():
    with pytest.raises(StrategyCompileError):
        _compile_condition(_cond(), "exit")


class _Parsed:
    def __init__(self, indicator):
        self.entry_signals = [TechnicalSignal(indicator=indicator, signal_type="buy")]


def test_exit_slot_not_applicable_for_buy_at_start():
    assert has_buy_at_start(_Parsed("buy_at_start"))
    assert not has_buy_at_start(_Parsed("rsi"))


def test_decided_marks_exit_not_applicable_for_buy_at_start():
    decided = _decided(_Parsed("buy_at_start"), EXIT, frozenset())
    assert decided is not None and decided.not_applicable
