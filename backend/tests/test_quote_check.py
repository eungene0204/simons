import json

import pytest

import cancellation
from strategy_conversation import primary
from strategy_conversation.interpreter import check_batch, quote_check
from strategy_conversation.interpreter.models import StrategyIntent


TEXT = (
    "KOSPI와 KOSDAQ 공통 유니버스에서 PBR 1.5배 이하, ROE 12% 이상이면서 "
    "최근 60거래일 수익률이 상위권이고 거래대금이 50억 원 이상인 종목만 "
    "12종목 동일 비중으로 담고 싶어요. 주간 리밸런싱, 20일선 이탈 시 청산, 손절 -8%로 구성해 주세요."
)


def intent_for(quote):
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI", "KOSDAQ"]},
        "exit_conditions": [{"factor": "technical.ma_crossover", "operator": "crosses_below",
                             "parameters": {"short_period": 1, "long_period": 20},
                             "source_text": quote}],
    }})


def response(expresses, describes):
    return json.dumps({"items": [{"expresses": expresses, "describes": describes}]})


@pytest.mark.parametrize("batched", [False, True])
@pytest.mark.parametrize("confirmation,removed", [
    (response("yes", "moving_average"), False),
    (response("no", "moving_average"), False),
    (response("unclear", "other"), False),
    (response("no", "other"), True),
    ('{"items": []}', False),
    (RuntimeError("checker unavailable"), False),
])
def test_ma_exit_removal_requires_independent_confirmation(batched, confirmation, removed):
    intent = intent_for("20일선 이탈 시 청산")
    if batched:
        intent.strategy.backtest.contribution_amount = 1000000
        intent.strategy.backtest.contribution_period = "monthly"
    calls = []

    def chat(system, user, **kwargs):
        calls.append((system, user))
        if len(calls) == 1:
            rejected = json.loads(response("no", "other"))
            if system == check_batch._SYSTEM:
                return json.dumps({"checks": {"quote": rejected}})
            return json.dumps(rejected)
        if isinstance(confirmation, Exception):
            raise confirmation
        return confirmation

    checked_chat = check_batch.prepare_chat(intent, TEXT, chat) if batched else chat
    verdicts = primary._check_condition_quotes(intent, TEXT, checked_chat)
    notices = primary._drop_fabricated_conditions(intent, TEXT, verdicts)
    assert bool(notices) is removed
    assert bool(intent.strategy.exit_conditions) is not removed
    assert len(calls) == 2
    assert "종가가 20일 이동평균선을 아래로 교차하면" in calls[-1][1]
    assert calls[0][0] != calls[1][0]


def test_fixed_stop_loss_fabricated_as_ma_is_still_removed():
    intent = intent_for("손절 -8%")
    verdicts = primary._check_condition_quotes(
        intent, TEXT, lambda *a, **k: response("no", "other"))
    assert primary._drop_fabricated_conditions(intent, TEXT, verdicts)
    assert intent.strategy.exit_conditions == []


def test_valid_ma_needs_no_confirmation():
    calls = []
    def chat(*args, **kwargs):
        calls.append(args)
        return response("yes", "moving_average")
    intent = intent_for("20일선 이탈 시 청산")
    verdicts = primary._check_condition_quotes(intent, TEXT, chat)
    assert primary._drop_fabricated_conditions(intent, TEXT, verdicts) == []
    assert len(calls) == 1


@pytest.mark.parametrize("batched", [False, True])
@pytest.mark.parametrize("confirmation,removed", [("no", True), ("yes", False)])
def test_fabricated_ma_entry_from_exit_needs_independent_role_confirmation(
    batched, confirmation, removed,
):
    intent = intent_for("20일선 이탈 시 청산")
    intent.strategy.entry_conditions.append(intent.strategy.exit_conditions[0].model_copy(
        update={"operator": ">", "source_text": "20일선 위에 있는 동안"}))
    if batched:
        intent.strategy.backtest.contribution_amount = 1000000
        intent.strategy.backtest.contribution_period = "monthly"
    calls = []

    def chat(system, user, **kwargs):
        calls.append((system, user))
        if len(calls) == 1:
            quote_response = {"items": [
                {"expresses": "yes", "describes": "moving_average"},
                {"expresses": "yes", "describes": "moving_average"},
            ]}
            if system == check_batch._SYSTEM:
                for index, item in enumerate(quote_response["items"], 1):
                    item["id"] = f"quote:{index}"
                quote_response = {"checks": {"quote": quote_response}}
            return json.dumps(quote_response)
        return response(confirmation, "other" if confirmation == "no" else "moving_average")

    checked_chat = check_batch.prepare_chat(intent, TEXT, chat) if batched else chat
    verdicts = primary._check_condition_quotes(intent, TEXT, checked_chat)
    primary._drop_fabricated_conditions(intent, TEXT, verdicts)
    assert bool(intent.strategy.entry_conditions) is not removed
    assert len(intent.strategy.exit_conditions) == 1
    assert len(calls) == 3
    assert all("20일선 위에 있는 동안" not in user for _, user in calls[1:])


def test_literal_entry_and_exit_quotes_need_no_role_confirmation():
    text = "종가가 20일선 위에 있으면 매수하고 20일선 이탈 시 청산해 주세요."
    intent = intent_for("20일선 이탈 시 청산")
    intent.strategy.entry_conditions.append(intent.strategy.exit_conditions[0].model_copy(
        update={"operator": ">", "source_text": "20일선 위에 있으면 매수"}))
    calls = []

    def chat(system, user, **kwargs):
        calls.append(system)
        return json.dumps({"items": [
            {"expresses": "yes", "describes": "moving_average"},
            {"expresses": "yes", "describes": "moving_average"},
        ]})

    verdicts = primary._check_condition_quotes(intent, text, chat)
    assert primary._drop_fabricated_conditions(intent, text, verdicts) == []
    assert len(intent.strategy.entry_conditions) == len(intent.strategy.exit_conditions) == 1
    assert len(calls) == 1


def test_confirmation_propagates_cancellation():
    calls = []
    def chat(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return response("no", "other")
        raise cancellation.OperationCancelled()
    with pytest.raises(cancellation.OperationCancelled):
        primary._check_condition_quotes(intent_for("20일선 이탈 시 청산"), TEXT, chat)
