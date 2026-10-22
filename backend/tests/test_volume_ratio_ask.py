"""배수 없는 '거래량 급증'은 거래량 배수의 값 대기 → 1.5·2·3배 칩으로 되묻는다(2026-10-22 사용자 결정).

사고: "20일 신고가를 돌파하면서 거래량이 급증한 종목"이 OBV 20일 평균 상향 돌파(volume_spike)로
백테스트됐다 — 프롬프트 5-2와 registry가 배수 없는 급증을 OBV로 정의하고 있었다(속설 #21·#17 후보 보류).
"""
from __future__ import annotations

from engine import strategy_slots
from engine.nl_parser import ParsedStrategy
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.prompts import build_system_prompt
from strategy_conversation.registry.indicator_registry import resolve
from strategy_conversation.response.output_guard import guard_text
from strategy_conversation.validation.pipeline import run_validation

_FIELD = "strategy.entry_conditions[1].value"


def _breakout_volume_intent(**volume_params):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 1.0,
        "strategy": {
            "universe": {"markets": ["KOSDAQ"], "sectors": []},
            "entry_conditions": [
                {"factor": "technical.breakout", "operator": "crosses_above", "value": None,
                 "parameters": {"lookback_period": 20}, "source_text": "20일 신고가를 돌파하면서"},
                {"factor": "technical.volume_ratio", "operator": ">=", "value": None,
                 "parameters": volume_params, "source_text": "거래량이 급증한"},
            ],
        },
    })


def test_valueless_volume_ratio_is_asked_and_held_back():
    validated, report = run_validation(_breakout_volume_intent())
    assert _FIELD in report.missing_fields
    question = next(q for q in report.clarification_questions if q.field == _FIELD)
    assert guard_text(question.question) == question.question
    parsed, _, pending = compile_partial(validated, report, None)
    # 배수 확정 전에는 엔진에 보내지 않는다(엔진 기본 2배로 조용히 돌지 않게).
    assert not any(s.indicator == "volume_ratio" for s in parsed.entry_signals)
    assert any(s.indicator == "breakout" for s in parsed.entry_signals)
    assert pending


def test_volume_ratio_question_offers_three_bound_chips():
    from strategy_conversation.primary import _bind_chips, _clarification_items

    validated, report = run_validation(_breakout_volume_intent())
    item = next(i for i in _clarification_items(report, validated)
                if any("20일 평균" in c for c in i["chips"]))
    expected = [strategy_slots.volume_ratio_chip("entry", m) for m in (1.5, 2, 3)]
    assert item["chips"] == expected
    parsed, _, _ = compile_partial(validated, report, None)
    # 결속기를 통과해야 화면에 보인다 — 거래량 배수 칩 가드(_CHIP_VOLUME_MULTIPLE_RE)에 걸리지 않는다.
    shown, bindings, _, _ = _bind_chips(item["chips"], parsed, None)
    assert shown == expected
    sig = bindings[expected[0]]["entry_signals"][-1]
    assert (sig["indicator"], sig["operator"], sig["value"], sig["period"]) == ("volume_ratio", ">=", 1.5, 20)


def test_volume_ratio_chips_skipped_for_custom_period():
    from strategy_conversation.primary import _clarification_items

    validated, report = run_validation(_breakout_volume_intent(period=60))
    items = _clarification_items(report, validated)
    assert not any("20일 평균" in c for i in items for c in i["chips"])


def test_volume_ratio_chip_binding_appends_signal_once():
    base = ParsedStrategy(description="거래량").model_dump()
    chip = strategy_slots.volume_ratio_chip("exit", 3)
    patch = strategy_slots.volume_ratio_chip_patch(chip, base)
    assert patch is not None
    sig = patch["exit_signals"][-1]
    assert (sig["signal_type"], sig["value"]) == ("sell", 3.0)
    ParsedStrategy.model_validate({**base, **patch})
    assert strategy_slots.volume_ratio_chip_patch(chip, {**base, **patch}) is None
    assert strategy_slots.volume_ratio_chip_patch("손절 -10%", base) is None


def test_prompt_routes_valueless_volume_surge_to_volume_ratio():
    prompt = build_system_prompt()
    assert "거래량 배수 조건(technical.volume_ratio, operator \">=\", value=null)" in prompt
    assert "OBV를 직접 말했을 때만" in prompt
    assert resolve("거래량급증").id == "technical.volume_ratio"


def test_entry_slot_chips_use_bound_volume_ratio_chips():
    """매수 칩 정본에서 OBV '거래량 급증 시 매수'가 빠지고, 거래량 칩은 결속 표와 같은 글자다."""
    chips = strategy_slots._QUESTIONS[strategy_slots.ENTRY][1]
    assert "거래량 급증 시 매수" not in chips
    volume = [c for c in chips if c.startswith("거래량이")]
    assert volume == [strategy_slots.volume_ratio_chip("entry", m) for m in (1.5, 2, 3)]
