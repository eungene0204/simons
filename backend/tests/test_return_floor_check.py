"""수익률 하한 대조(2026-10-26 속설 #27) — "30% 이상 오른"의 하한이 2회 중 1회 사라지던 사고.

녹화 턴의 1차 해석(nemotron-3.5-super-vl)은 하한 칸을 비우고 원문에 없는 "(시장 대비)"를 붙인 인용으로
relative_return > 0 조건을 냈다. 랭킹 중복 제거가 그 조건을 걷어내며 지어낸 인용으로 안내를 띄웠고,
백테스트는 30% 미만 종목까지 샀다.
"""

import json

from strategy_conversation.interpreter import return_floor_check as rf
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.primary import _dedupe_relative_return_against_ranking

_TEXT = "최근 20일 동안 30% 이상 오른 KOSPI 종목을 매수하고, 20거래일 보유한 뒤 매도하고 싶습니다."

# 녹화 턴(trace 664e6a0436e0)의 LLM 원출력에서 전략 부분
_RECORDED = {
    "universe": {"markets": ["KOSPI"]},
    "entry_conditions": [
        {"factor": "ranking.return", "operator": None, "value": None,
         "parameters": {"lookback_days": 20}, "source_text": "최근 20일 동안 30% 이상 오른"},
        {"factor": "technical.relative_return", "operator": ">", "value": 0,
         "parameters": {"period": 20}, "source_text": "30% 이상 오른 (시장 대비)"},
    ],
    "ranking": [{"metric": "return", "lookback_days": 20}],
    "portfolio": {"hold_period_days": 20},
}


def _intent(strategy=None):
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY",
                                          "strategy": json.loads(json.dumps(strategy or _RECORDED))})


def _chat(payload):
    calls = []

    def chat(system, user, max_tokens=None):
        calls.append(user)
        return payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    chat.calls = calls
    return chat


def test_recorded_turn_recovers_floor_after_dedupe():
    intent = _intent()
    notices = _dedupe_relative_return_against_ranking(intent, _TEXT)
    # 지어낸 인용("(시장 대비)")은 사용자 말처럼 되돌려 주지 않는다
    assert notices == []
    assert all(c.factor != "technical.relative_return" for c in intent.strategy.entry_conditions)
    chat = _chat({"kind": "stated", "value_text": "30%"})
    assert rf.recover_return_floor(intent, _TEXT, chat) == 30.0
    assert intent.strategy.portfolio.absolute_momentum_threshold_percent == 30.0
    assert len(chat.calls) == 1


def test_dedupe_still_notices_a_verbatim_quote():
    strategy = json.loads(json.dumps(_RECORDED))
    strategy["entry_conditions"][1]["source_text"] = "30% 이상 오른"
    notices = _dedupe_relative_return_against_ranking(_intent(strategy), _TEXT)
    assert notices == ["'30% 이상 오른'은(는) 기간 수익률 랭킹으로 반영했어요."]


def test_existing_floor_is_not_asked_again():
    strategy = json.loads(json.dumps(_RECORDED))
    strategy["portfolio"]["absolute_momentum_threshold_percent"] = 30
    chat = _chat({"kind": "stated", "value_text": "30%"})
    assert rf.recover_return_floor(_intent(strategy), _TEXT, chat) is None
    assert chat.calls == []


def test_no_return_ranking_is_not_asked():
    strategy = json.loads(json.dumps(_RECORDED))
    strategy["ranking"] = [{"metric": "per", "direction": "bottom"}]
    chat = _chat({"kind": "stated", "value_text": "30%"})
    assert rf.recover_return_floor(_intent(strategy), _TEXT, chat) is None
    assert chat.calls == []


def test_bottom_direction_is_not_asked():
    strategy = json.loads(json.dumps(_RECORDED))
    strategy["ranking"][0]["direction"] = "bottom"
    chat = _chat({"kind": "stated", "value_text": "30%"})
    assert rf.recover_return_floor(_intent(strategy), _TEXT, chat) is None
    assert chat.calls == []


def test_value_text_absent_from_input_is_rejected():
    intent = _intent()
    assert rf.recover_return_floor(intent, _TEXT, _chat({"kind": "stated", "value_text": "25%"})) is None
    assert intent.strategy.portfolio.absolute_momentum_threshold_percent is None


def test_non_percent_value_text_is_rejected():
    intent = _intent()
    assert rf.recover_return_floor(intent, _TEXT, _chat({"kind": "stated", "value_text": "20거래일"})) is None
    assert intent.strategy.portfolio.absolute_momentum_threshold_percent is None


def test_none_unclear_and_broken_replies_fail_open():
    for reply in ({"kind": "none", "value_text": None}, {"kind": "unclear", "value_text": None},
                  {"kind": "maybe"}, "not json"):
        intent = _intent()
        assert rf.recover_return_floor(intent, _TEXT, _chat(reply)) is None
        assert intent.strategy.portfolio.absolute_momentum_threshold_percent is None


def test_chat_exception_fails_open():
    def boom(system, user, max_tokens=None):
        raise RuntimeError("upstream 502")
    intent = _intent()
    assert rf.recover_return_floor(intent, _TEXT, boom) is None
    assert intent.strategy.portfolio.absolute_momentum_threshold_percent is None
