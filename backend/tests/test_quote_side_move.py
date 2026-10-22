"""매수 칸에 들어간 매도 문구는 역할 판정 두 번이 일치하면 매도 칸으로 옮긴다(2026-10-22).

사고: "종가가 60일 이동평균선 위에 있을 때 보유하고, 60일선 아래로 내려오면 정리"에서 인터프리터가
청산 문구를 entry_conditions에 넣었고, 인용 대조가 no/moving_average(이 칸의 조건이 아님)로 답하자
판정 보류로 조건이 빠져 "보류한 조건의 지표와 매수·청산 기준을 다시 알려주시겠어요?"만 남았다
(예시 55·68·69, 트레이스 3718ed54e60b).
"""
from __future__ import annotations

import json

from strategy_conversation.interpreter import quote_check
from strategy_conversation.interpreter.models import StrategyIntent

_INPUT = ("반도체 ETF만 대상으로 종가가 60일 이동평균선 위에 있을 때 보유하고, 60일선 아래로 "
          "내려오면 정리하는 전략을 만들어 주세요.")


def _intent():
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 1.0,
        "strategy": {
            "universe": {"markets": ["ETF"], "sectors": []},
            "entry_conditions": [
                {"factor": "technical.ma_crossover", "operator": ">", "value": None,
                 "parameters": {"short_period": 1, "long_period": 60},
                 "source_text": "종가가 60일 이동평균선 위에 있을 때 보유"},
                {"factor": "technical.ma_crossover", "operator": "crosses_below", "value": None,
                 "parameters": {"short_period": 1, "long_period": 60},
                 "source_text": "60일선 아래로 내려오면 정리"},
            ],
        },
    })


def _chat(sides_first, sides_second):
    calls = []

    def chat(system, user, **_kw):
        calls.append(system)
        if system == quote_check._SIDE_SYSTEM:
            return json.dumps({"items": [{"side": s} for s in sides_first]})
        if system == quote_check._SIDE_CONFIRM_SYSTEM:
            return json.dumps({"items": [{"side": s} for s in sides_second]})
        # 트레이스 실측 판정 그대로
        return json.dumps({"items": [{"expresses": "yes", "describes": "moving_average"},
                                     {"expresses": "no", "describes": "moving_average"}]})
    return chat, calls


def test_exit_quote_in_entry_moves_to_exit_when_both_side_checks_agree():
    from strategy_conversation.primary import _check_condition_quotes

    intent = _intent()
    moved = intent.strategy.entry_conditions[1]
    chat, calls = _chat(["sell"], ["sell"])
    verdicts = _check_condition_quotes(intent, _INPUT, chat)
    assert [c.source_text for c in intent.strategy.entry_conditions] == ["종가가 60일 이동평균선 위에 있을 때 보유"]
    assert intent.strategy.exit_conditions == [moved]
    assert verdicts.get(moved).expresses == "yes"          # 옮긴 조건은 판정 보류로 잡히지 않는다
    assert calls.count(quote_check._SIDE_SYSTEM) == 1 and calls.count(quote_check._SIDE_CONFIRM_SYSTEM) == 1


def test_disagreeing_side_checks_leave_condition_in_place():
    from strategy_conversation.primary import _check_condition_quotes

    intent = _intent()
    chat, _ = _chat(["sell"], ["unclear"])
    verdicts = _check_condition_quotes(intent, _INPUT, chat)
    assert len(intent.strategy.entry_conditions) == 2 and intent.strategy.exit_conditions == []
    assert verdicts.get(intent.strategy.entry_conditions[1]).expresses == "no"


def test_side_check_failure_is_fail_open():
    from strategy_conversation.primary import _check_condition_quotes

    intent = _intent()

    def chat(system, user, **_kw):
        if system in (quote_check._SIDE_SYSTEM, quote_check._SIDE_CONFIRM_SYSTEM):
            raise RuntimeError("upstream 502")
        return json.dumps({"items": [{"expresses": "yes", "describes": "moving_average"},
                                     {"expresses": "no", "describes": "moving_average"}]})
    _check_condition_quotes(intent, _INPUT, chat)
    assert len(intent.strategy.entry_conditions) == 2 and intent.strategy.exit_conditions == []


def test_no_side_check_when_quote_is_other():
    """다른 설정 문구(no/other)는 종전대로 제거 경로다 — 역할을 묻지 않는다."""
    intent = _intent()
    targets = quote_check.targets_for_intent(intent, _INPUT)
    calls = []

    def chat(system, user, **_kw):
        calls.append(system)
        return json.dumps({"items": [{"expresses": "yes", "describes": "moving_average"},
                                     {"expresses": "no", "describes": "other"}]})
    quote_check.check_quotes(_INPUT, targets, chat)
    assert quote_check._SIDE_SYSTEM not in calls
