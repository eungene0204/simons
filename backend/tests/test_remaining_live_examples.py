"""Remaining KR live failures must preserve roles, periods, and diagnostics."""
import pytest
import polars as pl
import json

from strategy_conversation.interpreter.models import StrategyCondition, StrategyIntent
from strategy_conversation.validation.pipeline import run_validation
from strategy_conversation.compiler.strategy_compiler import compile_partial, _compile_condition, StrategyCompileError
from engine.strategy_converter import _tech_signal_to_condition
from engine.signals import SignalEngine


def breakout_intent(entry_op="crosses_above", exit_op="crosses_below", entry_period=20):
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [{"factor": "technical.breakout", "operator": entry_op,
            "parameters": {"lookback_period": entry_period}, "source_text": "20일 고점을 넘기는 날 매수"}],
        "exit_conditions": [{"factor": "technical.breakout", "operator": exit_op,
            "parameters": {"lookback_period": 20}, "source_text": "20일 저가 아래로 내려오면 매도"}],
        "portfolio": {"selection_count": 8}, "risk_management": {"stop_loss": 7}}})


def test_second_fail_compiles_existing_high_buy_low_sell_and_fires_on_low():
    intent, report = run_validation(breakout_intent())
    assert report.errors == []
    parsed, dropped, _ = compile_partial(intent, report, "저가 이탈 예시")
    assert dropped == []
    assert [(s.indicator, s.signal_type, s.lookback_period) for s in parsed.exit_signals] == [
        ("breakout", "sell", 20)]
    assert parsed.max_positions == 8 and parsed.stop_loss_pct == 7
    frame = pl.DataFrame({"high": [10.0] * 21, "low": [5.0] * 20 + [4.0],
        "close": [7.0] * 21, "high_20_max": [10.0] * 21, "low_20_min": [5.0] * 21})
    engine = SignalEngine()
    assert engine.evaluate_condition(_tech_signal_to_condition(parsed.exit_signals[0]), 20, frame)
    assert not engine.evaluate_condition(_tech_signal_to_condition(parsed.entry_signals[0]), 20, frame)


@pytest.mark.parametrize("entry_op,exit_op", [("crosses_below", "crosses_below"),
                                             ("crosses_above", "crosses_above")])
def test_breakout_wrong_role_direction_is_rejected(entry_op, exit_op):
    # Distinct periods avoid the model's preexisting mirrored-condition cleanup.
    intent = breakout_intent(entry_op, exit_op, entry_period=21)
    _, report = run_validation(intent)
    assert report.errors


@pytest.mark.parametrize("role,operator", [("entry", "crosses_below"), ("exit", "crosses_above")])
def test_direct_compiler_cannot_flip_breakout_direction(role, operator):
    condition = StrategyCondition(factor="technical.breakout", operator=operator,
                                  parameters={"lookback_period": 20})
    with pytest.raises(StrategyCompileError):
        _compile_condition(condition, role)


@pytest.mark.parametrize("recovery,kept", [("corrected", True), ("unchanged", False),
    ("unclear", False), ("bad_quantity", False), ("rejected", False)])
def test_ema_exit_disagreement_requires_verified_changed_fields(recovery, kept):
    from strategy_conversation.interpreter import quote_check, semantic_reconciliation
    from strategy_conversation.interpreter.decisions import decision_session, current_log
    utterance = "조선 관련주에서 20일 EMA 이탈 시 청산하고, 최대 6종목으로 설정"
    quote = "20일 EMA 이탈 시 청산하고"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI"]}, "exit_conditions": [{"factor": "technical.ema",
            "operator": "crosses_below", "parameters": {"short_period": 20, "long_period": 60},
            "source_text": quote}], "portfolio": {"selection_count": 6}}})
    condition = intent.strategy.exit_conditions[0]
    calls = []
    def chat(system, user, **kwargs):
        calls.append(system)
        if system == quote_check._SYSTEM:
            return '{"items":[{"expresses":"no","describes":"other"}]}'
        if system == quote_check._CONFIRM_SYSTEM:
            return json.dumps({"items": [{"expresses": "no" if recovery == "rejected" else "yes",
                                          "describes": "other" if recovery == "rejected" else "moving_average"}]})
        assert system == semantic_reconciliation._SYSTEM
        return json.dumps({"items": [{"id": "c:0", "quote": quote,
            "status": "corrected" if recovery == "bad_quantity" else recovery,
            "requested_role": "exit", "factor": "technical.ema", "parameters": {
                "short_period": None, "long_period": {"number_text": "60" if recovery == "bad_quantity" else "20",
                                                         "count": 60 if recovery == "bad_quantity" else 20, "unit": "day"}}}]})
    @decision_session
    def execute():
        checks = current_log().required_checks
        targets = checks.conditions(intent, utterance)
        verdicts = quote_check.check_quotes(utterance, targets[0], chat)
        checks.settle(targets, verdicts)
        assert checks.items[0]["status"] == ("REJECT" if recovery == "rejected" else "UNRESOLVED")
        semantic_reconciliation.reconcile_semantic_fields(intent, utterance, chat)
        checks.filter_conditions(intent.strategy)
        assert bool(intent.strategy.exit_conditions) is kept
        if kept:
            assert condition.parameters == {"short_period": None, "long_period": 20}
            assert checks.recoveries[id(condition)]["candidate_id"] != checks.items[0]["row"]["candidate_id"]
        assert intent.strategy.portfolio.selection_count == 6
    execute()
    assert len(calls) <= 3


def test_parameter_conflict_notice_keeps_error_without_internal_factor():
    from strategy_conversation.validation.conflict_validator import validate_conflicts
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "entry_conditions": [{"factor": "technical.ema", "operator": ">",
                              "parameters": {"short_period": 60, "long_period": 20}}]}})
    result = validate_conflicts(intent)
    errors = result[0]
    assert errors
    assert "technical.ema" not in " ".join(errors)
    assert "60" in " ".join(errors) and "20" in " ".join(errors)
