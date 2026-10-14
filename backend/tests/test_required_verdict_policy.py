"""Required evidence holds only the affected new or replacement group."""
import json

import pytest

from strategy_conversation import primary
from strategy_conversation.interpreter.models import StrategyIntent
from test_strategy_conversation import _full_intent_dict, _rich_parsed, _stub_modify_interpreter, _StubPrimaryInterpreter


@pytest.mark.parametrize("reply", [None, "unclear", "bad json"])
def test_failed_create_return_check_does_not_commit_zero(monkeypatch, reply):
    data = _full_intent_dict(entry_conditions=[{
        "factor": "technical.relative_return", "operator": ">", "value": 0,
        "source_text": "수익률이 좋은"}])
    stub = _StubPrimaryInterpreter(data)
    stub._chat = lambda *a, **k: (json.dumps({"kind": reply, "quote": "수익률이 좋은"})
                                 if reply != "bad json" else reply)
    monkeypatch.setattr(primary, "_interpreter_singleton", stub)
    result = primary.run_primary_parse("수익률이 좋은 종목으로 전략 만들어줘")
    assert result["parsed"].entry_signals == []
    assert "수익률" in result["clarification_question"]
    assert "지원" not in " ".join(result["notices"])


def test_unresolved_quote_replacement_keeps_old_condition_and_count(monkeypatch):
    quote = "한 달 지나면 정리"
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/exit_conditions/0", "source_text": quote,
         "value": {"factor": "technical.ma_crossover", "operator": "crosses_below",
                   "parameters": {"short_period": 1, "long_period": 21}, "source_text": quote}},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    monkeypatch.setattr(primary, "_check_condition_quotes", lambda *a, **k: None)
    previous = _rich_parsed()
    result = primary.run_primary_modification(f"{quote}, 종목은 12개", previous.model_dump())
    assert result["parsed"].exit_signals == previous.exit_signals
    assert result["parsed"].max_positions == 12
    assert result["parsed"].fundamental_filters == previous.fundamental_filters
    assert "보류" in " ".join(result["notices"]) or "청산" in result["clarification_question"]


def test_unresolved_market_patch_keeps_market_and_independent_count(monkeypatch):
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/universe/markets", "value": ["KOSDAQ"], "source_text": "코스닥"},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    previous = _rich_parsed()
    result = primary.run_primary_modification("코스닥 종목은 12개", previous.model_dump())
    assert result["parsed"].universe == previous.universe
    assert result["parsed"].max_positions == 12
    assert "시장" in result["clarification_question"]


@pytest.mark.parametrize("number,unit,count,expected", [
    ("10", "day", None, 10), ("1", "month", None, 21),
    ("1", "year", None, 252), ("한", "month", 1, 21),
    ("한", "month", None, 21), ("두", "month", None, 42), ("삼", "year", None, 756)])
def test_holding_unit_evidence_is_confirmed_without_new_call(number, unit, count, expected):
    from strategy_conversation.interpreter.holding_period_check import reconcile_holding_days
    quote = "한 달 보유" if number == "한" else f"{number} {unit} 보유"
    intent = StrategyIntent.model_validate({"intent": "MODIFY_STRATEGY", "patches": [{
        "op": "replace", "path": "/portfolio/hold_period_days", "value": 999,
        "source_text": quote}]})
    calls = []
    def chat(*args, **kwargs):
        calls.append(args)
        return json.dumps({"items": [{"id": "1", "quote": quote, "number_text": number,
            "unit": unit, **({"count": count} if count is not None else {})}]})
    checked = reconcile_holding_days(intent, quote, chat)
    assert checked.patches[0].value == expected
    assert len(calls) == 1


def test_trading_failure_holds_pair_and_keeps_independent_count(monkeypatch):
    quote = "거래량이 늘면"
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "remove", "path": "/entry_conditions/0"},
        {"op": "add", "path": "/entry_conditions/-", "source_text": quote,
         "value": {"factor": "technical.trading_value", "operator": ">", "value": None, "source_text": quote}},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    calls = []
    def chat(*a, **k):
        calls.append(a)
        return json.dumps({"items": [{"id": "1", "action": "replace", "quote": quote}]}) if len(calls) == 1 else "bad json"
    primary._interpreter_singleton._chat = chat
    previous = _rich_parsed()
    result = primary.run_primary_modification(f"{quote}, 종목은 12개", previous.model_dump())
    assert result["parsed"].fundamental_filters == previous.fundamental_filters
    assert result["parsed"].entry_signals == previous.entry_signals
    assert result["parsed"].max_positions == 12
    assert "거래대금" in result["clarification_question"]
    assert len(calls) == 2


def test_scope_omission_holds_only_questioned_add(monkeypatch):
    utter = "PER 10 이하 종목은 12개"
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "add", "path": "/entry_conditions/-", "source_text": "PER 10 이하",
         "value": {"factor": "fundamental.per", "operator": "<=", "value": 10, "source_text": "PER 10 이하"}},
        {"op": "add", "path": "/entry_conditions/-", "source_text": "종목",
         "value": {"factor": "fundamental.market_cap", "operator": "<=", "value": None, "source_text": "종목"}},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    primary._interpreter_singleton._chat = lambda *a, **k: "bad json"
    previous = _rich_parsed()
    result = primary.run_primary_modification(utter, previous.model_dump())
    assert any(f.metric == "per" and f.value == 10 for f in result["parsed"].fundamental_filters)
    assert not any(f.metric == "market_cap" for f in result["parsed"].fundamental_filters)
    assert result["parsed"].max_positions == 12
    assert result["clarification_question"]


def test_numeric_failure_reports_hold_without_affecting_valid_count(monkeypatch):
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/risk_management/take_profit", "value": 777, "source_text": "두 배"},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    primary._interpreter_singleton._chat = lambda *a, **k: "bad json"
    previous = _rich_parsed()
    result = primary.run_primary_modification("두 배에 정리, 종목은 12개", previous.model_dump())
    assert result["parsed"].take_profit_pct == previous.take_profit_pct
    assert result["parsed"].max_positions == 12
    assert "수량" in result["clarification_question"]


@pytest.mark.parametrize("answer", [None, "KR", "US", "OTHER"])
def test_unknown_region_never_commits_new_universe_and_keeps_count(monkeypatch, answer):
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/universe/symbols", "value": ["미확인회사"], "source_text": "미확인회사"},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    from strategy_conversation.registry import universe_resolver
    monkeypatch.setattr(universe_resolver, "resolve_symbols", lambda refs: ([], list(refs)))
    monkeypatch.setattr(primary, "_unresolvable_symbol_names", lambda *a: [])
    provenance = primary._patch_provenance_supported
    # This test starts at region approval, after the existing provenance gate.
    monkeypatch.setattr(primary, "_patch_provenance_supported", lambda p, *a:
                        True if p.path == "/universe/symbols" else provenance(p, *a))
    primary._interpreter_singleton._chat = lambda *a, **k: json.dumps({
        "items": [{"market": answer}]})
    previous = _rich_parsed()
    result = primary.run_primary_modification("미확인회사, 종목은 12개", previous.model_dump())
    assert result["parsed"].target_symbols == previous.target_symbols
    assert result["parsed"].universe == previous.universe
    assert result["parsed"].max_positions == 12
    assert "시장" in result["clarification_question"]


def test_failed_holding_check_does_not_trigger_an_extra_numeric_call(monkeypatch):
    from strategy_conversation.interpreter.holding_period_check import reconcile_holding_days
    _stub_modify_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "patches": [
        {"op": "replace", "path": "/portfolio/hold_period_days", "value": 10, "source_text": "10일 보유"},
        {"op": "replace", "path": "/portfolio/selection_count", "value": 12, "source_text": "종목은 12개"}]})
    stub = primary._interpreter_singleton
    calls = []
    def chat(*a, **k):
        calls.append(a)
        return "bad json"
    def interpret(user_input, **kwargs):
        stub._result.intent = reconcile_holding_days(stub._result.intent, user_input, chat)
        return stub._result
    stub.interpret = interpret
    stub._chat = chat
    previous = _rich_parsed()
    result = primary.run_primary_modification("10일 보유, 종목은 12개", previous.model_dump())
    assert result["parsed"].hold_period_days == previous.hold_period_days
    assert result["parsed"].max_positions == 12
    assert "보유 기간" in result["clarification_question"]
    assert len(calls) == 1
