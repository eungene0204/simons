"""Rejected condition groups preserve independent edits and sequential targets."""
import pytest

from strategy_conversation.conversation.patch_approval import PatchApproval
from strategy_conversation.conversation.patch_applier import apply_patches, PatchError
from strategy_conversation.interpreter.models import PatchOp, StrategySpec


def condition(value):
    return {"factor": "fundamental.per", "operator": "<=", "value": value}


def spec():
    return StrategySpec.model_validate({"entry_conditions": [condition(v) for v in (10, 20, 30)]})


def test_excluded_removal_rebases_later_replacement_to_its_original_target():
    original = spec()
    patches = [PatchOp(op="remove", path="/entry_conditions/0"),
               PatchOp(op="replace", path="/entry_conditions/1", value=condition(40))]
    plan = PatchApproval(original, patches)
    selected, _ = plan.select({plan.operations[0]["group"]})
    assert selected[0].path == "/entry_conditions/2"
    assert [c.value for c in apply_patches(original, selected).entry_conditions] == [10, 20, 40]
    assert [c.value for c in original.entry_conditions] == [10, 20, 30]


def test_rejected_add_holds_unknown_paired_remove_but_keeps_another_replacement():
    original = spec()
    patches = [PatchOp(op="remove", path="/entry_conditions/0"),
               PatchOp(op="replace", path="/entry_conditions/1", value=condition(40)),
               PatchOp(op="add", path="/entry_conditions/-", value=condition(99))]
    plan = PatchApproval(original, patches)
    current = apply_patches(original, patches)
    origins = plan.condition_origins(current)
    rejected = origins[id(current.entry_conditions.pop())]
    restored, selected, _ = plan.restore_rejected(original, current, origins, {rejected}, apply_patches)
    assert [c.value for c in restored.entry_conditions] == [10, 20, 40]
    assert [p.path for p in selected] == ["/entry_conditions/2"]


def test_stale_base_is_not_applied():
    original = spec()
    plan = PatchApproval(original, [PatchOp(op="replace", path="/entry_conditions/0", value=condition(40))])
    current = apply_patches(original, plan.original)
    origins = plan.condition_origins(current)
    original.portfolio.selection_count = 17
    with pytest.raises(PatchError, match="Stale"):
        plan.restore_rejected(original, current, origins, {origins[id(current.entry_conditions[0])]}, apply_patches)


def test_committed_delta_reproduces_the_actual_approved_spec():
    from strategy_conversation.conversation.patch_approval import committed_delta
    original = spec()
    current = apply_patches(original, [PatchOp(op="replace", path="/portfolio/selection_count", value=12)])
    assert apply_patches(original, committed_delta(original, current)) == current


def test_duplicate_promotions_keep_distinct_candidate_groups():
    from strategy_conversation.interpreter.decisions import DecisionLog
    original = StrategySpec()
    patches = [PatchOp(op="replace", path=f"/entry_conditions/{index}/{key}", value=value)
               for index in (0, 1) for key, value in condition(10).items()]
    log = DecisionLog()
    for index, patch in enumerate(patches):
        log.bind(patch, f"candidate:{index}", f"proposal:{index}")
        log.record("scope", patch, "ACCEPT", "CONFIRMED")
    plan = PatchApproval(original, patches)
    plan.bind_log(log)
    first, second = plan.operations
    assert first["group"] != second["group"]
    assert {r["change_group_id"] for r in log.results[:3]} == {first["group"]}
    assert {r["change_group_id"] for r in log.results[3:]} == {second["group"]}
    selected, _ = plan.select({first["group"]})
    assert [c.value for c in apply_patches(original, selected).entry_conditions] == [10]


def test_condition_sibling_changes_are_held_together():
    original = spec()
    patches = [PatchOp(op="replace", path="/entry_conditions/0/operator", value=">="),
               PatchOp(op="replace", path="/entry_conditions/0/value", value=99),
               PatchOp(op="replace", path="/portfolio/selection_count", value=12)]
    plan = PatchApproval(original, patches)
    selected, _ = plan.select({plan.operations[0]["group"]})
    current = apply_patches(original, selected)
    assert current.entry_conditions == original.entry_conditions
    assert current.portfolio.selection_count == 12


def test_confirmed_replacement_pair_is_held_together():
    original = spec()
    remove = PatchOp(op="remove", path="/entry_conditions/0")
    add = PatchOp(op="add", path="/entry_conditions/-", value=condition(99))
    plan = PatchApproval(original, [remove, add], linked_pairs=[(remove, add)])
    selected, _ = plan.select({plan.operations[1]["group"]})
    assert selected == []
    assert apply_patches(original, selected) == original


def test_quote_rejected_replacement_keeps_independent_position_change(monkeypatch):
    from test_strategy_conversation import _stub_modify_interpreter, _rich_parsed
    from strategy_conversation import primary
    from strategy_conversation.interpreter.quote_check import QuoteVerdicts, Verdict
    quote = "한 달 지나면 정리"
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/exit_conditions/0", "source_text": quote,
         "value": {"factor": "technical.ma_crossover", "operator": "crosses_below",
                   "parameters": {"short_period": 1, "long_period": 21}, "source_text": quote}},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    monkeypatch.setattr(primary, "_check_condition_quotes", lambda intent, *a, **k: QuoteVerdicts([
        (c, Verdict("no", "other")) for c in intent.strategy.exit_conditions]))
    previous = _rich_parsed()
    result = primary.run_primary_modification(f"{quote}, 종목은 12개로 바꿔줘", previous.model_dump())
    assert result["parsed"].exit_signals == previous.exit_signals
    assert result["parsed"].max_positions == 12
    assert result["parsed"].fundamental_filters == previous.fundamental_filters


def test_unclear_pair_holds_conditions_and_applies_independent_count(monkeypatch):
    import json
    from test_strategy_conversation import _stub_modify_interpreter, _rich_parsed
    from strategy_conversation import primary
    quote = "60일 신고가 뚫을때"
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "add", "path": "/entry_conditions/-", "source_text": quote,
         "value": {"factor": "technical.breakout", "operator": "crosses_above",
                   "parameters": {"lookback_period": 60}, "source_text": quote}},
        {"op": "remove", "path": "/entry_conditions/0"},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    primary._interpreter_singleton._chat = lambda *a, **k: json.dumps({"items": [{"id": "1", "action": "unclear", "quote": None}]})
    previous = _rich_parsed()
    result = primary.run_primary_modification(f"{quote}, 종목은 12개로 바꿔줘", previous.model_dump())
    assert result["parsed"].max_positions == 12
    assert result["parsed"].fundamental_filters == previous.fundamental_filters
    assert result["parsed"].entry_signals == previous.entry_signals
    assert "바꿀까요" in result["clarification_question"]


def test_model_question_holds_its_field_without_discarding_an_independent_count(monkeypatch):
    from test_strategy_conversation import _stub_modify_interpreter, _rich_parsed
    from strategy_conversation import primary
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/universe/markets", "value": ["ETF"], "source_text": "ETF"},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}],
        "clarification_questions": [{"field": "strategy.universe.markets", "question": "어떤 ETF 범위인가요?"}]})
    previous = _rich_parsed()
    result = primary.run_primary_modification("ETF로 바꾸고 종목은 12개", previous.model_dump())
    assert result["parsed"].max_positions == 12
    assert result["parsed"].universe == previous.universe
    assert result["parsed"].fundamental_filters == previous.fundamental_filters
    assert result["clarification_question"] == "어떤 ETF 범위인가요?"
