"""VWAP 조건(엔진 v16.48) 회귀 테스트.

배경: VWAP은 미지원 개념이었다(프롬프트 미지원 목록·레거시 원문 패턴). 분봉이 없어 일봉 N거래일 누적
VWAP(전형가격 기준)으로 지원한다 — 2026-11-06 사용자 결정: 전형가격, 기간 없으면 되묻기(5·20·60일 칩),
장중 VWAP 요청은 근사 반영+안내. 이 파일은 ① 지표 열 계산 ② 벡터/행별 평가 일치(상태·교차, 방향은 역할과
독립) ③ 변환기·매매 사유 ④ 컴파일·디컴파일 왕복 ⑤ 기간 되묻기·칩 결속 ⑥ 인터프리터 어휘 노출을 고정한다.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from engine import strategy_slots, trade_reason
from engine.indicators import IndicatorEngine
from engine.nl_parser import ParsedStrategy, TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import _decompile_technical
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.response.output_guard import guard_text
from strategy_conversation.validation.pipeline import run_validation


def _ohlcv(high, low, close, volume) -> pl.DataFrame:
    n = len(close)
    dates = pl.date_range(pl.date(2024, 1, 1), pl.date(2024, 1, 1) + pl.duration(days=n - 1),
                          interval="1d", eager=True)
    return pl.DataFrame({"date": dates, "open": np.array(close, dtype=float),
                         "high": np.array(high, dtype=float), "low": np.array(low, dtype=float),
                         "close": np.array(close, dtype=float), "volume": np.array(volume, dtype=float)})


def _cond(**params):
    return {"type": "indicator", "id": "vwap", "params": {"period": 3, **params}}


def test_indicator_engine_computes_volume_weighted_typical_price():
    high, low, close = [12, 22, 32, 42], [8, 18, 28, 38], [10, 20, 30, 40]
    volume = [1, 2, 1, 0]
    out = IndicatorEngine.calculate(_ohlcv(high, low, close, volume), [_cond()])
    vwap = out["vwap_3"].to_list()
    # 창이 차기 전(앞 2개)은 값이 없다.
    assert all(v is None or np.isnan(v) for v in vwap[:2])
    # 전형가격 = (고+저+종)/3 = 10, 20, 30, 40 → (10·1 + 20·2 + 30·1) / 4 = 20
    assert vwap[2] == pytest.approx(20.0)
    # (20·2 + 30·1 + 40·0) / 3
    assert vwap[3] == pytest.approx(70.0 / 3.0)


def test_zero_volume_window_has_no_value():
    out = IndicatorEngine.calculate(_ohlcv([1, 1, 1], [1, 1, 1], [1, 1, 1], [0, 0, 0]), [_cond()])
    v = out["vwap_3"].to_list()[2]
    assert v is None or np.isnan(v)


def _frame(close, vwap):
    return pl.DataFrame({"close": [float(c) for c in close], "vwap_3": [float(v) for v in vwap]})


@pytest.mark.parametrize("params, expected", [
    ({"cross": "above"}, [False, False, True, False, True]),
    ({"cross": "below"}, [False, False, False, True, False]),
    ({"mode": "above"}, [False, True, True, False, True]),
    ({"mode": "below"}, [True, True, False, True, False]),
])
def test_vector_and_row_evaluators_agree(params, expected):
    df = _frame([9, 10, 11, 9, 12], [10, 10, 10, 10, 10])
    engine = SignalEngine()
    cond = _cond(signalType="buy", **params)
    vec = engine._eval_vec(cond, df).tolist()
    assert vec == expected
    assert [engine.evaluate_condition(cond, i, df) for i in range(len(df))] == vec


def test_cross_direction_defaults_to_role_and_is_independent_of_it():
    df = _frame([9, 11, 9], [10, 10, 10])
    engine = SignalEngine()
    assert engine._eval_vec(_cond(signalType="buy"), df).tolist() == [False, True, False]
    assert engine._eval_vec(_cond(signalType="sell"), df).tolist() == [False, False, True]
    # '매도 칸의 상향 돌파'도 그대로 표현된다(방향을 역할로 뒤집지 않는다).
    assert engine._eval_vec(_cond(signalType="sell", cross="above"), df).tolist() == [False, True, False]
    assert engine._eval_vec(_cond(signalType="buy"), pl.DataFrame({"close": [1.0, 2.0]})).tolist() == [False, False]


@pytest.mark.parametrize("signal, params, reason", [
    (dict(signal_type="buy"), {"cross": "above"}, "종가 20일 VWAP 상향 돌파"),
    (dict(signal_type="sell"), {"cross": "below"}, "종가 20일 VWAP 하향 이탈"),
    (dict(signal_type="sell", cross="above"), {"cross": "above"}, "종가 20일 VWAP 상향 돌파"),
    (dict(signal_type="buy", mode="above"), {"mode": "above"}, "종가가 20일 VWAP 위 유지"),
    (dict(signal_type="sell", mode="below"), {"mode": "below"}, "종가가 20일 VWAP 아래 유지"),
])
def test_converter_and_trade_reason(signal, params, reason):
    cond = _tech_signal_to_condition(TechnicalSignal(indicator="vwap", period=20, **signal))
    assert cond["id"] == "vwap"
    assert cond["params"]["period"] == 20
    for key in ("mode", "cross"):
        assert cond["params"].get(key) == params.get(key)
    parts = SignalEngine()._base_condition_segments(cond)
    assert trade_reason.render_kr(parts) == reason


def _intent(operator, role="entry", **params):
    other = "exit" if role == "entry" else "entry"
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 1.0,
        "strategy": {
            "universe": {"markets": ["KOSPI"], "sectors": []},
            f"{role}_conditions": [{
                "factor": "technical.vwap", "operator": operator, "value": None,
                "parameters": params, "source_text": "VWAP 위로 돌파하면"}],
            f"{other}_conditions": [{
                "factor": "technical.rsi", "operator": "<=" if other == "entry" else ">=",
                "value": 30 if other == "entry" else 70,
                "parameters": {"period": 14}, "source_text": "RSI"}],
        },
    })


@pytest.mark.parametrize("operator, role, engine_kwargs", [
    ("crosses_above", "entry", {"cross": "above", "mode": None}),
    ("crosses_below", "exit", {"cross": "below", "mode": None}),
    ("crosses_above", "exit", {"cross": "above", "mode": None}),
    (">", "entry", {"mode": "above", "cross": None}),
    ("<", "exit", {"mode": "below", "cross": None}),
])
def test_compile_and_decompile_round_trip(operator, role, engine_kwargs):
    validated, report = run_validation(_intent(operator, role, period=20))
    assert not any("vwap" in f or "value" in f for f in report.missing_fields), report.missing_fields
    parsed, _, pending = compile_partial(validated, report, None)
    signals = parsed.entry_signals if role == "entry" else parsed.exit_signals
    sig = next(s for s in signals if s.indicator == "vwap")
    assert sig.period == 20
    assert (sig.cross, sig.mode) == (engine_kwargs["cross"], engine_kwargs["mode"])
    back = _decompile_technical(sig)
    assert (back.factor, back.operator, back.parameters.get("period")) == ("technical.vwap", operator, 20.0)


def test_missing_period_is_asked_with_shape_preserving_chips_and_held_back():
    from strategy_conversation.primary import _clarification_items

    validated, report = run_validation(_intent(">"))
    field = "strategy.entry_conditions[0].parameters.period"
    assert field in report.missing_fields
    assert not any(f.endswith(".value") for f in report.missing_fields)  # 기준값은 묻지 않는다
    question = next(q for q in report.clarification_questions if q.field == field)
    assert question.recommended_value is None                  # 기본값을 정하지 않는다(사용자 결정)
    assert guard_text(question.question) == question.question
    parsed, _, pending = compile_partial(validated, report, None)
    assert not any(s.indicator == "vwap" for s in parsed.entry_signals)  # 값 확정 전 엔진에 보내지 않음
    assert pending
    item = next(i for i in _clarification_items(report, validated) if any("VWAP" in c for c in i["chips"]))
    assert item["chips"] == [strategy_slots.vwap_period_chip("entry", ">", n) for n in (5, 20, 60)]
    assert item["chips"][1] == "종가가 20일 VWAP 위에 있을 때 매수"


def test_period_chip_binding_appends_signal_once():
    base = ParsedStrategy(description="VWAP").model_dump()
    chip = strategy_slots.vwap_period_chip("exit", "crosses_below", 60)
    patch = strategy_slots.vwap_period_chip_patch(chip, base)
    assert patch is not None
    sig = patch["exit_signals"][-1]
    assert (sig["indicator"], sig["signal_type"], sig["period"], sig["cross"]) == ("vwap", "sell", 60, "below")
    ParsedStrategy.model_validate({**base, **patch})
    assert strategy_slots.vwap_period_chip_patch(chip, {**base, **patch}) is None
    assert strategy_slots.vwap_period_chip_patch("손절 -10%", base) is None


def test_vwap_is_exposed_to_the_interpreter_vocabulary_and_not_listed_unsupported():
    from strategy_conversation.interpreter.prompts import build_system_prompt

    prompt = build_system_prompt()
    assert "technical.vwap" in prompt
    assert "우선주, VWAP" not in prompt


def test_pending_approximated_vwap_is_announced_on_the_ask_turn():
    """'장중 VWAP'(근사 신고)이 기간 대기로 보류되면 되묻는 턴에 근사 안내가 나가야 한다 — 기간을 정하는
    칩 턴은 근사 신고를 싣지 않아, 종전엔 안내가 한 번도 나가지 않았다(2026-11-06 실서버 2/2)."""
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.interpreter.models import StrategySpec, ValidationReport
    from strategy_conversation.response.notice_assembly import assemble_response_notices, notice_context

    quote = "장중 VWAP 아래로 떨어지면 매도"
    strategy = StrategySpec(exit_conditions=[{
        "factor": "technical.vwap", "operator": "crosses_below", "value": None, "parameters": {},
        "source_text": quote, "approximated": True}])
    pending = [{"role": "exit", "label": "VWAP(거래량가중 평균가)", "source_text": quote}]
    result = {"parsed": ParsedStrategy(description="x"), "notices": [],
              "clarification_question": "VWAP(거래량가중 평균가)의 기간을(를) 몇으로 할까요?",
              "_notice_context": notice_context(ValidationReport(), strategy, "코스닥 " + quote,
                                                pending=pending)}
    assemble_response_notices(result)
    notice = next(n for n in result["notices"] if "가깝게" in n)
    assert quote in notice and "반영할 예정" in notice and "반영했어요" not in notice
    assert guard_text(notice) == notice


def test_cross_direction_is_part_of_the_strategy_id():
    """저장 기록은 전략 ID로 업서트된다 — 교차 방향만 다른 VWAP 전략이 같은 ID를 받으면 서로의 기록을 덮어쓴다."""
    from engine.strategy_converter import to_canonical_strategy_dsl

    def dsl(cross):
        return to_canonical_strategy_dsl(ParsedStrategy(
            universe=["KOSPI"],
            entry_signals=[TechnicalSignal(indicator="rsi", signal_type="buy", period=14, operator="<=", value=30)],
            exit_signals=[TechnicalSignal(indicator="vwap", signal_type="sell", period=20, cross=cross)]))

    assert dsl("above") != dsl("below")
