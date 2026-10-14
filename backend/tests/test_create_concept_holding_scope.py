"""A declared sell concept is not an unknown holding-period condition."""
import json

import pytest

from strategy_conversation import primary
from strategy_conversation.interpreter import holding_period_check, quote_check, semantic_reconciliation
from strategy_conversation.interpreter.decisions import decision_session, current_log
from strategy_conversation.interpreter.models import StrategyIntent
from test_strategy_conversation import _full_intent_dict, _StubPrimaryInterpreter


PROMPT = (
    "차트를 보니까 단기 이동평균선이 장기 이동평균선을 위로 뚫을 때 많이들 들어간다고 하더라고요. "
    "KOSPI 종목 중 골든크로스가 나오면 매수하고, 반대로 데드크로스가 나오면 매도하는 식으로 "
    "간단하게 만들어 주세요. 종목은 최대 10개, 손절은 -8%로 부탁드립니다."
)


PROMPT_47 = (
    "KOSPI에서 5일 이동평균선이 20일 이동평균선을 위로 뚫는 골든크로스에 매수하고, "
    "데드크로스가 나오면 매도하고 싶어요. 종목은 8개, 손절은 -7%로 설정해 주세요."
)


@pytest.mark.parametrize("prompt,entry_quote,exit_quote,count,stop", [
    (PROMPT, "골든크로스가 나오면 매수", "데드크로스가 나오면 매도", 10, 8),
    # Trace e9d7bbbe6afa: same extracted dead cross, held by required_holding.
    (PROMPT_47, "골든크로스에 매수", "데드크로스가 나오면 매도", 8, 7),
])
def test_first_live_failure_preserves_extracted_dead_cross(
        monkeypatch, prompt, entry_quote, exit_quote, count, stop):
    # Minimal observed Interpreter fields from trace e5b83b9624d8; the
    # original quote verdicts accepted both conditions as moving averages.
    data = _full_intent_dict(
        entry_conditions=[{"factor": "concept.golden_cross", "source_text": entry_quote}],
        exit_conditions=[{"factor": "concept.dead_cross", "source_text": exit_quote}],
        portfolio={"selection_count": count},
        risk_management={"stop_loss": stop},
    )
    calls = []
    replies = {
        quote_check._SYSTEM: '{"items":[{"expresses":"yes","describes":"moving_average"},'
                             '{"expresses":"yes","describes":"moving_average"}]}',
        holding_period_check._MISFILED_SYSTEM:
            '{"kind":"none","quote":null,"number_text":null,"count":null,"unit":null}',
        semantic_reconciliation._SYSTEM:
            '{"items":[{"id":"c:0","quote":"%s","status":"unchanged"}]}' % entry_quote,
    }
    def chat(system, user, **kwargs):
        calls.append(system)
        assert system in replies
        return replies[system]
    stub = _StubPrimaryInterpreter(data)
    stub._chat = chat
    monkeypatch.setattr(primary, "_interpreter_singleton", stub)
    monkeypatch.setattr(primary.config, "condition_recall_enabled", lambda: False)
    monkeypatch.setattr(primary.config, "call_reduction_enabled", lambda: False)
    monkeypatch.setattr(primary.config, "dag_planner_mode", lambda: "off")
    monkeypatch.setattr(primary.config, "parallel_parse_enabled", lambda: False)

    result = primary.run_primary_parse(prompt)
    parsed = result["parsed"]
    assert len(parsed.exit_signals) == 1
    assert parsed.exit_signals[0].indicator == "ma_crossover"
    assert parsed.exit_signals[0].signal_type == "sell"
    assert (parsed.exit_signals[0].short_period, parsed.exit_signals[0].long_period) == (5, 20)
    assert len(parsed.entry_signals) == 1
    assert parsed.entry_signals[0].signal_type == "buy"
    assert parsed.max_positions == count
    assert parsed.stop_loss_pct == stop
    assert parsed.hold_period_days is None
    assert "보유 기간" not in (result.get("clarification_question") or "")
    assert holding_period_check._MISFILED_SYSTEM not in calls
    from interpretation_api_replay import finalize_api
    api = finalize_api({"user_input": prompt, "previous_parsed": None,
        "question": None, "pending_ask": None, "explicit_fields": []}, result)
    assert api["parsed"]["exit_signals"][0]["signal_type"] == "sell"
    assert api["parsed"]["max_positions"] == count
    assert api["parsed"]["stop_loss_pct"] == stop
    assert api["parsed"]["hold_period_days"] is None
    assert "보유 기간" not in (api.get("clarification_question") or "")


@pytest.mark.parametrize("factor,phrase", [
    ("concept.dead_cross", "데드크로스에서 매도"),
    ("concept.macd_dead_cross", "데드크로스에서 매도"),
    # Example gate fails #49/#52 (MACD) and #61/#74 (plain) held on required_holding.
    ("concept.macd_dead_cross", "MACD 데드크로스가 나오면 매도"),
    ("concept.macd_dead_cross", "MACD 데드크로스에서 매도"),
    ("concept.dead_cross", "데드크로스가 나오면 매도"),
])
def test_declared_exit_concepts_do_not_create_holding_requirements(factor, phrase):
    intent = StrategyIntent.model_validate(_full_intent_dict(exit_conditions=[{
        "factor": factor, "source_text": phrase}]))
    def unexpected_chat(*args, **kwargs):
        pytest.fail("A declared ontology expansion must not require holding recovery")
    @decision_session
    def execute():
        notices = holding_period_check.recover_create_misfiled_holding_period(
            intent, phrase, unexpected_chat)
        assert notices == []
        assert current_log().required_checks.items == []
        assert intent.strategy.exit_conditions[0].factor == factor
    execute()


@pytest.mark.parametrize("recovered", [True, False])
def test_unknown_time_exit_retains_existing_recovery_or_hold_policy(recovered):
    phrase = "진입 후 10거래일 경과"
    intent = StrategyIntent.model_validate(_full_intent_dict(exit_conditions=[{
        "factor": "concept.time_based_exit", "source_text": phrase}]))
    @decision_session
    def execute():
        answer = ({"kind": "max_hold", "quote": phrase, "number_text": "10", "count": 10,
                   "unit": "day"} if recovered else {"kind": "none"})
        holding_period_check.recover_create_misfiled_holding_period(
            intent, phrase, lambda *a, **k: json.dumps(answer))
        if recovered:
            assert intent.strategy.portfolio.hold_period_days == 10
            assert intent.strategy.exit_conditions == []
        else:
            assert intent.strategy.portfolio.hold_period_days is None
            assert current_log().required_checks.items[-1]["status"] == "UNRESOLVED"
    execute()


def test_condition_recall_does_not_duplicate_declared_golden_cross():
    # Trace 20000f88d0c4 (example 74): the independent phrase '골든크로스가 나오면 매수하고'
    # missed the existing quote's boundary, so concept.golden_cross was revived as a
    # second, period-less technical.ma_crossover and a 20/60 period question went out.
    from strategy_conversation.interpreter.condition_recall import recover_missing_conditions
    intent = StrategyIntent.model_validate(_full_intent_dict(
        entry_conditions=[{"factor": "concept.golden_cross",
                           "source_text": "반도체 업종 종목 중 골든크로스가 나오면 매수"}],
        exit_conditions=[{"factor": "concept.dead_cross",
                          "source_text": "데드크로스가 나오면 매도해 주세요"}]))
    user = ("반도체 업종 종목 중 골든크로스가 나오면 매수하고 데드크로스가 나오면 매도해 주세요.")
    recovered = recover_missing_conditions(
        intent, user, chat=None, phrases=["골든크로스가 나오면 매수하고"])
    assert recovered == []
    assert [c.factor for c in intent.strategy.entry_conditions] == ["concept.golden_cross"]
