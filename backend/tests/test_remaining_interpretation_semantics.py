"""Only quoted structured verdicts may correct role, EMA, and holding meaning."""
import json

import pytest

from strategy_conversation import primary
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.semantic_reconciliation import reconcile_semantic_fields


def _intent(quote, **fields):
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "entry_conditions": [{"factor": "technical.ma_crossover", "operator": "crosses_above",
                              "parameters": {"short_period": 5, "long_period": 20},
                              "source_text": quote, **fields}]}})


def test_kr_numeric_normalization_does_not_reinterpret_quote_words():
    intent = _intent("20일 EMA를 이탈하면 청산", operator="crosses_below")
    condition = intent.strategy.entry_conditions[0]
    primary._fill_deterministic_condition_params(intent, semantic_authority=True)
    assert intent.strategy.entry_conditions == [condition]
    assert intent.strategy.exit_conditions == []
    assert condition.factor == "technical.ma_crossover"


def test_confirmed_ema_and_role_are_applied_in_one_batch():
    quote = "20일 EMA를 이탈하면 청산"
    intent = _intent(quote, operator="crosses_below")
    calls = []
    def chat(*args, **kwargs):
        calls.append(args)
        return json.dumps({"items": [{"id": "c:0", "quote": quote, "status": "corrected",
            "requested_role": "exit", "factor": "technical.ema", "parameters": {
                "short_period": None, "long_period": {"number_text": "20", "count": 20, "unit": "day"}}}]})
    reconcile_semantic_fields(intent, quote, chat)
    assert intent.strategy.entry_conditions == []
    assert intent.strategy.exit_conditions[0].factor == "technical.ema"
    assert intent.strategy.exit_conditions[0].parameters == {"short_period": None, "long_period": 20}
    assert len(calls) == 1


@pytest.mark.parametrize("reply", ["bad json", '{"items":[]}', '{"items":[{"id":"wrong"}]}'])
def test_missing_verdict_never_invokes_lexical_ema_or_role_fallback(reply):
    quote = "20일 EMA를 이탈하면 청산"
    intent = _intent(quote, operator="crosses_below")
    before = intent.model_dump()
    reconcile_semantic_fields(intent, quote, lambda *a, **k: reply)
    primary._fill_deterministic_condition_params(intent, semantic_authority=True)
    assert intent.model_dump() == before


def test_unquoted_period_is_not_written_into_the_condition():
    quote = "20일 이동평균선 위면 매수"
    intent = _intent(quote)
    before = intent.model_dump()
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "c:0", "quote": quote, "status": "corrected", "parameters": {
            "long_period": {"number_text": "60", "count": 60, "unit": "day"}}}]}))
    assert intent.model_dump() == before


def test_unsupported_holding_label_requires_llm_kind_and_quantity():
    quote = "한 달 보유"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {},
                                          "unsupported_features": [quote]})
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "f:0", "quote": quote, "status": "corrected", "kind": "max_hold",
        "number_text": "한", "count": 1, "unit": "month"}]}))
    assert intent.strategy.portfolio.hold_period_days == 21
    assert intent.unsupported_features == []


def test_existing_holding_value_is_not_overwritten_by_reported_label():
    quote = "한 달 보유"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "portfolio": {"hold_period_days": 10}}, "unsupported_features": [quote]})
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "f:0", "quote": quote, "status": "corrected", "kind": "max_hold",
        "number_text": "한", "count": 1, "unit": "month"}]}))
    assert intent.strategy.portfolio.hold_period_days == 10
    assert intent.unsupported_features == [quote]


def test_risk_report_is_reconciled_only_with_a_quoted_percent_verdict():
    quote = "손절 -7%"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {},
                                          "unsupported_features": [quote]})
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "f:0", "quote": quote, "status": "corrected", "kind": "stop_loss",
        "number_text": "-7", "count": 7, "unit": "percent"}]}))
    assert intent.strategy.risk_management.stop_loss == 7
    assert intent.unsupported_features == []
