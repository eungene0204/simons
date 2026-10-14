"""KR domain failures and unresolved universe must not discard independent edits."""
from types import SimpleNamespace

from strategy_conversation import primary
from strategy_conversation.conversation.patch_applier import apply_patches
from strategy_conversation.conversation.patch_approval import PatchApproval
from strategy_conversation.interpreter.domain_approval import approve_domains, create_domain_candidates
from strategy_conversation.interpreter.models import PatchOp, StrategySpec
from strategy_conversation.validation.pipeline import run_validation
from test_strategy_conversation import _full_intent_dict, _rich_parsed, _stub_modify_interpreter


def _validate(intent):
    normalized, report = run_validation(intent)
    return SimpleNamespace(intent=normalized, report=report)


def _approve(original, patches):
    approval = PatchApproval(original, patches)
    current = apply_patches(original, patches)
    return approve_domains(approval, original, current, approval.condition_origins(current),
                           set(), _validate, apply_patches)


def test_invalid_risk_preserves_valid_count_and_original_conditions():
    original = StrategySpec.model_validate(_full_intent_dict()["strategy"])
    _, patches, blocked, result, diagnostics, _ = _approve(original, [
        PatchOp(op="replace", path="/risk_management/stop_loss", value=200),
        PatchOp(op="replace", path="/portfolio/selection_count", value=12)])
    assert blocked and diagnostics
    assert result.intent.strategy.risk_management.stop_loss == original.risk_management.stop_loss
    assert result.intent.strategy.portfolio.selection_count == 12
    assert result.intent.strategy.entry_conditions == original.entry_conditions
    assert [p.path for p in patches] == ["/portfolio/selection_count"]


def test_invalid_replacement_restores_old_condition_and_valid_scalar():
    original = StrategySpec.model_validate(_full_intent_dict()["strategy"])
    spec, patches, blocked, result, _, _ = _approve(original, [
        PatchOp(op="replace", path="/entry_conditions/0", value={"factor": "technical.rsi",
            "operator": "<", "value": 30, "parameters": {"period": -1}}),
        PatchOp(op="replace", path="/portfolio/selection_count", value=12)])
    assert blocked and not result.report.errors
    assert spec.entry_conditions == original.entry_conditions
    assert spec.portfolio.selection_count == 12
    assert [p.path for p in patches] == ["/portfolio/selection_count"]


def test_two_domain_failures_are_held_without_losing_third_change():
    original = StrategySpec.model_validate(_full_intent_dict()["strategy"])
    spec, patches, blocked, _, _, _ = _approve(original, [
        PatchOp(op="replace", path="/risk_management/stop_loss", value=200),
        PatchOp(op="replace", path="/backtest/fee_rate", value=50),
        PatchOp(op="replace", path="/portfolio/selection_count", value=12)])
    assert len(blocked) == 2
    assert spec.risk_management == original.risk_management
    assert spec.backtest == original.backtest
    assert [p.path for p in patches] == ["/portfolio/selection_count"]


def test_create_invalid_condition_does_not_remove_supported_per():
    spec = StrategySpec.model_validate(_full_intent_dict()["strategy"])
    from strategy_conversation.interpreter.models import StrategyCondition
    valid = StrategyCondition(factor="fundamental.per", operator="<=", value=10)
    invalid = StrategyCondition(factor="technical.rsi", operator="<", value=30, parameters={"period": -1})
    spec.entry_conditions = [valid, invalid]
    baseline, approval = create_domain_candidates(spec)
    held, _, blocked, _, _, _ = approve_domains(approval, baseline, spec,
        approval.condition_origins(spec), set(), _validate, apply_patches)
    assert blocked
    assert any(c.factor == "fundamental.per" and c.value == 10 for c in held.entry_conditions)
    assert not any(c.factor == "technical.rsi" for c in held.entry_conditions)


def test_primary_domain_hold_keeps_independent_count(monkeypatch):
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/risk_management/stop_loss", "value": 200, "source_text": "손절 200%"},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목 12개"}]})
    previous = _rich_parsed()
    result = primary.run_primary_modification("손절 200%, 종목 12개", previous.model_dump())
    assert result["parsed"].max_positions == 12
    assert result["parsed"].stop_loss_pct == previous.stop_loss_pct
    assert result["parsed"].exit_signals == previous.exit_signals
    assert any("200" in notice for notice in result["notices"])


def test_theme_scope_question_keeps_independent_count(monkeypatch):
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/universe/sectors", "value": ["새 테마"], "source_text": "새 테마"},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목 12개"}]})
    monkeypatch.setattr(primary, "_resolve_theme_change", lambda *a, **k: ("어느 범위인가요?", ["범위 A", "범위 B"]))
    previous = _rich_parsed()
    result = primary.run_primary_modification("새 테마로 변경하고 종목 12개", previous.model_dump())
    assert result["parsed"].max_positions == 12
    assert result["parsed"].sector == previous.sector
    assert result["parsed"].target_symbols == previous.target_symbols
    assert result["clarification_priority"] == "sector_unresolved"
    assert result["pending_ask"]["question"] == result["clarification_question"]


def test_missing_new_value_keeps_independent_count(monkeypatch):
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "add", "path": "/entry_conditions/-", "source_text": "PER 조건 추가",
         "value": {"factor": "fundamental.per", "operator": "<=", "value": None, "source_text": "PER 조건 추가"}},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목 12개"}]})
    previous = _rich_parsed()
    result = primary.run_primary_modification("PER 조건 추가, 종목 12개", previous.model_dump())
    assert result["parsed"].max_positions == 12
    assert result["parsed"].fundamental_filters == previous.fundamental_filters
    assert result["clarification_question"]
