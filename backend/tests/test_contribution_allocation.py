"""Initial allocations must not become recurring contribution plans."""
import json

import pytest

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.primary import _resolve_contribution_plan

TEXT = (
    "지난 10년 데이터로, 100만원 투자금으로 시총 1위부터 10위를 10만원씩 투자 해줘. "
    "1년이 지나면 순위권 회사들이 바뀌는데, 그때 순위권에서 나간 회사 주식은 매도, "
    "들어온 회사주식은 매수 해줘."
)
QUOTE = "100만원 투자금으로 시총 1위부터 10위를 10만원씩 투자 해줘"


def intent():
    return StrategyIntent.model_validate({
        "schema_version": "1.0", "intent": "CREATE_STRATEGY",
        "strategy": {
            "backtest": {"initial_capital": 1000000, "contribution_amount": 100000,
                         "contribution_period": "yearly"},
            "portfolio": {"selection_count": 10},
            "ranking": [{"metric": "fundamental.market_cap", "direction": "top"}],
        },
    })


def reply(kind="initial_allocation", quote=QUOTE, plan=None):
    return json.dumps({"allocation": {"kind": kind, "quote": quote},
                       "plan": plan or {"quote": None, "amount": None, "period": None}})


def test_initial_allocation_clears_invented_recurring_plan():
    parsed = intent()
    _resolve_contribution_plan(parsed, TEXT, lambda *a, **k: reply())
    bt = parsed.strategy.backtest
    assert bt.contribution_amount is None
    assert bt.contribution_period is None
    assert bt.initial_capital == 1000000
    assert parsed.strategy.portfolio.selection_count == 10
    from strategy_conversation.validation.capability_validator import validate_capability

    _errors, _warnings, unsupported, _clarifications = validate_capability(parsed)
    assert not any("정액 적립식" in feature for feature in unsupported)


@pytest.mark.parametrize("response", [
    reply(quote="invented quote"), reply(kind="unknown"), "{}", "not json",
    reply(plan={"quote": "10만원씩 투자 해줘", "amount": "10만원", "period": "yearly"}),
])
def test_invalid_missing_or_conflicting_evidence_preserves_plan(response):
    parsed = intent()
    _resolve_contribution_plan(parsed, TEXT, lambda *a, **k: response)
    assert parsed.strategy.backtest.contribution_amount == 100000
    assert parsed.strategy.backtest.contribution_period == "yearly"


def test_recurring_contributions_are_preserved():
    parsed = intent()
    text = "매년 10만원씩 투자 해줘"
    response = reply(kind="recurring", quote=text,
                     plan={"quote": text, "amount": "10만원", "period": "yearly"})
    _resolve_contribution_plan(parsed, text, lambda *a, **k: response)
    assert parsed.strategy.backtest.contribution_amount == 100000
    assert parsed.strategy.backtest.contribution_period == "yearly"
