"""Common verdict normalization does not change legacy auxiliary failure policy."""
import json

import pytest

from strategy_conversation.interpreter.decisions import DecisionLog, _CURRENT
from strategy_conversation.interpreter.models import PatchOp, StrategyCondition


@pytest.mark.parametrize("answer,status", [("yes", "ACCEPT"), ("no", "REJECT"), ("unclear", "UNRESOLVED"), ("broken", "UNRESOLVED")])
def test_scope_verdict_is_recorded_without_reinterpreting_failure(answer, status):
    from strategy_conversation.interpreter.patch_scope_check import market_patch_scope_verdict
    patch = PatchOp(op="replace", path="/universe/markets", value=["KOSPI"], source_text="코스피만")
    log = DecisionLog()
    log.bind(patch, "candidate-1", "group-1")
    token = _CURRENT.set(log)
    try:
        output = market_patch_scope_verdict(patch, "코스피만", lambda *a, **k: json.dumps({
            "verdict": answer, "quote": "코스피만" if answer == "yes" else None}))
    finally:
        _CURRENT.reset(token)
    assert output is (True if answer == "yes" else False if answer == "no" else None)
    row = log.results[0]
    assert row["status"] == status
    assert row["candidate_id"] == "candidate-1" and row["change_group_id"] == "group-1"
    assert row["evidence_ref"] == log.evidence[0]["id"]


def test_conflicting_stages_reject_before_unresolved_before_accept():
    log = DecisionLog()
    for stage, status in [("one", "ACCEPT"), ("two", "UNRESOLVED"), ("three", "REJECT")]:
        log.record(stage, "candidate", status, "synthetic", group_id="group")
    assert log.status("group") == "REJECT"
    log.results.pop()
    assert log.status("group") == "UNRESOLVED"
    assert log.status("unobserved") == "UNRESOLVED"


def test_quote_unavailable_is_not_an_accept_and_return_is_unchanged():
    from strategy_conversation.interpreter.quote_check import check_quotes
    condition = StrategyCondition(factor="technical.ma_crossover", operator="crosses_above",
                                  parameters={"short_period": 5, "long_period": 20}, source_text="골든크로스")
    log = DecisionLog()
    token = _CURRENT.set(log)
    try:
        result = check_quotes("골든크로스", [(condition, "entry_conditions")], lambda *a, **k: "bad json")
    finally:
        _CURRENT.reset(token)
    assert result is None and log.results[0]["status"] == "UNRESOLVED"
