"""Partial approvals preserve identity, units, cancellation, and old state."""
import json

import pytest

from strategy_conversation import primary
from strategy_conversation.conversation.patch_approval import PatchApproval
from strategy_conversation.conversation.patch_applier import apply_patches
from strategy_conversation.interpreter.decisions import current_log
from strategy_conversation.interpreter.holding_period_check import reconcile_holding_days
from strategy_conversation.interpreter.models import PatchOp, StrategySpec
from test_strategy_conversation import _full_intent_dict, _rich_parsed, _stub_modify_interpreter, _StubPrimaryInterpreter


def test_unresolved_whole_list_rewrite_cannot_clear_the_other_old_list():
    condition = {"factor": "fundamental.per", "operator": "<=", "value": 10}
    original = StrategySpec(entry_conditions=[condition], exit_conditions=[{
        "factor": "technical.ma_crossover", "operator": "crosses_below",
        "parameters": {"short_period": 5, "long_period": 20}}])
    patches = [PatchOp(op="replace", path="/entry_conditions", value=[dict(condition, value=99)]),
               PatchOp(op="replace", path="/exit_conditions", value=[]),
               PatchOp(op="replace", path="/portfolio/selection_count", value=12)]
    plan = PatchApproval(original, patches)
    current = apply_patches(original, patches)
    origins = plan.condition_origins(current)
    cell = origins[id(current.entry_conditions.pop())]
    restored, selected, _ = plan.restore_rejected(original, current, origins, {cell}, apply_patches,
        decisions=[{"change_group_id": plan.owners[cell], "status": "UNRESOLVED"}])
    assert restored.entry_conditions == original.entry_conditions
    assert restored.exit_conditions == original.exit_conditions
    assert restored.portfolio.selection_count == 12
    assert [p.path for p in selected] == ["/portfolio/selection_count"]


@pytest.mark.parametrize("unit,expected", [("day", 1), ("month", 21), ("year", 252)])
def test_confirmed_holding_unit_reaches_final_state_with_one_call(monkeypatch, unit, expected):
    quote = f"1 {unit} 보유"
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/portfolio/hold_period_days", "value": 999, "source_text": quote},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    stub = primary._interpreter_singleton
    calls = []
    def chat(*a, **k):
        calls.append(a)
        return json.dumps({"items": [{"id": "1", "quote": quote, "number_text": "1", "unit": unit}]})
    def interpret(user_input, **kwargs):
        stub._result.intent = reconcile_holding_days(stub._result.intent, user_input, chat)
        return stub._result
    stub.interpret, stub._chat = interpret, chat
    result = primary.run_primary_modification(f"{quote}, 종목은 12개", _rich_parsed().model_dump())
    assert result["parsed"].hold_period_days == expected
    assert result["parsed"].max_positions == 12
    assert len(calls) == 1


def test_cancellation_does_not_become_an_unresolved_response(monkeypatch):
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/portfolio/hold_period_days", "value": 10, "source_text": "10일 보유"}]})
    stub = primary._interpreter_singleton
    def chat(*a, **k):
        raise KeyboardInterrupt("cancelled")
    def interpret(user_input, **kwargs):
        reconcile_holding_days(stub._result.intent, user_input, chat)
    stub.interpret = interpret
    with pytest.raises(KeyboardInterrupt):
        primary.run_primary_modification("10일 보유", _rich_parsed().model_dump())
    assert current_log() is None


def test_create_unknown_region_preserves_an_independent_per_condition(monkeypatch):
    data = _full_intent_dict(universe={"markets": ["KOSPI"], "symbols": ["미확인회사"]})
    stub = _StubPrimaryInterpreter(data)
    stub._chat = lambda *a, **k: "bad json"
    monkeypatch.setattr(primary, "_interpreter_singleton", stub)
    result = primary.run_primary_parse("미확인회사 PER 10 이하")
    assert result["parsed"].target_symbols == []
    assert result["parsed"].fundamental_filters[0].value == 10
    assert "시장" in result["clarification_question"]


def test_disagreeing_quote_confirmation_holds_without_an_extra_recovery_call(monkeypatch):
    monkeypatch.setattr(primary.config, "condition_recall_enabled", lambda: False)
    quote = "20일선 이탈"
    data = _full_intent_dict(exit_conditions=[{"factor": "technical.ma_crossover",
        "operator": "crosses_below", "parameters": {"short_period": 1, "long_period": 20},
        "source_text": quote}])
    stub = _StubPrimaryInterpreter(data)
    calls = []
    def chat(*a, **k):
        calls.append(a)
        verdict = {"expresses": "no", "describes": "other"} if len(calls) == 1 else {
            "expresses": "yes", "describes": "moving_average"}
        return json.dumps({"items": [verdict]})
    stub._chat = chat
    monkeypatch.setattr(primary, "_interpreter_singleton", stub)
    result = primary.run_primary_parse(f"PER 10 이하, {quote} 시 청산")
    assert result["parsed"].exit_signals == []
    assert result["clarification_question"]
    assert len(calls) == 2


@pytest.mark.parametrize("output,expected,status", [("bad json", 999, "UNRESOLVED"),
    (json.dumps({"items": [{"id": "1", "quote": "1 month 보유", "number_text": "1", "unit": "month"}]}), 21, "ACCEPT")])
def test_completed_interpreter_replay_restores_holding_requirements(output, expected, status):
    from types import SimpleNamespace
    from interpretation_replay import replay_interpreter_requirements
    from strategy_conversation.interpreter.decisions import decision_session
    from strategy_conversation.interpreter.holding_period_check import _SYSTEM
    from strategy_conversation.interpreter.models import StrategyIntent
    intent = StrategyIntent.model_validate({"intent": "MODIFY_STRATEGY", "patches": [{
        "op": "replace", "path": "/portfolio/hold_period_days", "value": 999, "source_text": "1 month 보유"}]})
    request = {"utterance": "1 month 보유", "patches": [{"id": "1", "path": "/portfolio/hold_period_days",
               "source_text": "1 month 보유", "value": 999}]}
    recordings = [{"inputs": {"system": _SYSTEM, "user": json.dumps(request, ensure_ascii=False),
                    "max_tokens": 192}, "output": output}]
    stages = []
    @decision_session
    def execute():
        completed = replay_interpreter_requirements(SimpleNamespace(intent=intent), "1 month 보유", recordings, stages)
        checks = current_log().required_checks
        assert checks.items[-1]["status"] == status
        assert checks.items[-1]["subject"] is completed.intent.patches[0]
        return completed.intent.patches[0].value
    assert execute() == expected
    assert len(stages) == 1


@pytest.mark.parametrize("status,applied", [("UNRESOLVED", True), ("REJECT", False)])
def test_verified_recovery_has_new_identity_and_cannot_revive_a_rejected_candidate(status, applied):
    from strategy_conversation.interpreter.decisions import decision_session
    from strategy_conversation.interpreter.models import StrategyCondition
    from strategy_conversation.interpreter.quote_check import Verdict
    @decision_session
    def execute():
        condition = StrategyCondition(factor="technical.ma_crossover", operator="crosses_below",
                                      parameters={"short_period": 1, "long_period": 200})
        strategy = StrategySpec(entry_conditions=[condition])
        log = current_log()
        checks = log.required_checks
        checks.note("quote", condition, status, "entry_conditions",
                    Verdict("no", "moving_average" if applied else "other"))
        parent, group = log.bindings[id(condition)]
        condition.operator = "<"
        checks.recover(condition, {"confirmed_rule": {"state_operator": "<", "amount": 2000000}})
        checks.filter_conditions(strategy)
        assert bool(strategy.entry_conditions) is applied
        assert (parent in log.superseded) is applied
        assert (log.bindings[id(condition)][0] != parent) is applied
        assert log.status(group) == ("ACCEPT" if applied else "REJECT")
        return None
    execute()
