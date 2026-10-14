"""Routing axes are grounded structured output, never raw-word fallback."""
import json

import ui_language
from intent import classifier, interpreter


def test_confirmation_axis_is_read_from_llm_output():
    result = interpreter.interpret("그 작업 진행", lambda *args: json.dumps({
        "intent": "STRATEGY_ADVICE", "turn_action": "run_backtest"}))
    assert result.turn_action == "run_backtest"


def test_unknown_axis_does_not_become_a_route():
    result = interpreter.interpret("응", lambda *args: json.dumps({
        "intent": "STRATEGY_ADVICE", "turn_action": "recommend_strategy"}))
    assert result.turn_action is None


def test_period_axis_requires_an_actual_quote():
    result = interpreter.interpret("20일선 조건", lambda *args: json.dumps({
        "intent": "STRATEGY_ADVICE", "backtest_period_years": 0.5,
        "backtest_period_quote": "백테스트 반년"}))
    assert result.backtest_period_years is None


def test_kr_legacy_setting_cannot_invoke_regex_classifier(monkeypatch):
    monkeypatch.setattr(classifier, "classifier_mode", lambda: "legacy")
    monkeypatch.setattr(classifier, "_classify_legacy", lambda *args, **kwargs:
                        (_ for _ in ()).throw(AssertionError("raw route invoked")))
    with ui_language.bind("ko"):
        result = classifier.classify("이 작업 진행", llm=lambda *args: json.dumps({
            "intent": "STRATEGY_ADVICE", "turn_action": "run_backtest"}))
    assert result.turn_action == "run_backtest"
