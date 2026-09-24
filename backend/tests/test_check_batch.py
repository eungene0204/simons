import json

import pytest

import cancellation
from strategy_conversation import primary
from strategy_conversation.interpreter import check_batch, quote_check, trading_value_check, contribution_plan_check
from strategy_conversation.interpreter.models import StrategyIntent

TEXT = "매월 100만 원씩 코스피에서 20일선 위에 있으면 200만원 매수, 거래대금이 30일 평균보다 높은 종목"


def make_intent():
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI"]},
        "backtest": {"contribution_amount": 1000000, "contribution_period": "monthly"},
        "entry_conditions": [
            {"factor": "technical.ema", "operator": ">", "parameters": {"long_period": 20},
             "source_text": "20일선 위에 있으면"},
            {"factor": "fundamental.trading_value", "source_text": "거래대금이 30일 평균보다 높은"},
        ]}})


def sections():
    return {
        "quote": {"items": [{"id": "quote:1", "expresses": "yes", "describes": "moving_average"}]},
        "trading": {"items": [{"id": "trading:1", "compares": "own_average", "average_days": 30,
                               "multiple": 1, "operator": ">"}]},
        "contribution": {"plan": None, "rules": [{"quote": "20일선 위에 있으면", "amount": "200만원",
                                                    "mode": "set", "state": "above"}],
                         "cash_reserve": {"stated": False}, "max_buy": {"percent": None}},
    }


def run_checks(intent, chat):
    verdicts = primary._check_condition_quotes(intent, TEXT, chat)
    primary._resolve_trading_value_comparisons(intent, TEXT, chat)
    primary._resolve_contribution_plan(intent, TEXT, chat)
    return verdicts


def test_three_checks_become_one_with_identical_verdict_application():
    counts = []
    results = []
    for batching in (False, True):
        calls = []
        def chat(system, user, **kwargs):
            calls.append(system)
            if system == check_batch._SYSTEM:
                return json.dumps({"checks": sections()})
            key = {quote_check.build_system_prompt(): "quote",
                   trading_value_check.build_system_prompt(): "trading",
                   contribution_plan_check.build_system_prompt(): "contribution"}[system]
            return json.dumps(sections()[key])
        intent = make_intent()
        verdicts = run_checks(intent, check_batch.prepare_chat(intent, TEXT, chat) if batching else chat)
        assert verdicts.get(intent.strategy.entry_conditions[0]).expresses == "yes"
        results.append(intent.model_dump())
        counts.append(len(calls))
    assert counts == [3, 1]
    assert results[0] == results[1]
    assert results[1]["strategy"]["entry_conditions"][0]["buy_amount"] == 2000000
    assert results[1]["strategy"]["entry_conditions"][1]["factor"] == "technical.trading_value_ratio"


def test_invalid_section_alone_retries_original_checker():
    calls = []
    def chat(system, user, **kwargs):
        calls.append(system)
        if system == check_batch._SYSTEM:
            data = sections()
            data["quote"]["items"][0]["id"] = "quote:99"
            return json.dumps({"checks": data})
        assert system == quote_check.build_system_prompt()
        return json.dumps(sections()["quote"])
    intent = make_intent()
    run_checks(intent, check_batch.prepare_chat(intent, TEXT, chat))
    assert len(calls) == 2


def test_verdicts_reorder_by_ids_and_reject_duplicate_ids():
    rows = [{"id": f"quote:{i}", "expresses": "yes", "describes": "moving_average"} for i in (2, 1)]
    result = check_batch._validated_section("quote", {"items": rows}, 2)
    assert [r["id"] for r in result["items"]] == ["quote:1", "quote:2"]
    assert check_batch._validated_section("quote", {"items": [rows[0], rows[0]]}, 2) is None


def test_cancel_is_not_swallowed_as_batch_fallback():
    def chat(*a, **k):
        raise cancellation.OperationCancelled()
    with pytest.raises(cancellation.OperationCancelled):
        check_batch.prepare_chat(make_intent(), TEXT, chat)


def test_missing_id_is_safe_only_for_a_single_item():
    item = {"expresses": "yes", "describes": "moving_average"}
    assert check_batch._validated_section("quote", {"items": [item]}, 1)["items"][0]["id"] == "quote:1"
    assert check_batch._validated_section("quote", {"items": [item, item]}, 2) is None
    assert check_batch._validated_section("quote", {"items": [{**item, "id": "quote:99"}]}, 1) is None
