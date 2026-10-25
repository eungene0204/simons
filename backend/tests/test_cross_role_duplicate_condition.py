"""매수·매도 두 칸에 복사된 같은 조건 — 형식 위반 재생성 회귀.

2026-10-20 사고: "KOSDAQ 종목 중 RSI가 30 이하로 떨어졌다가 다시 반등하는 종목을 매수하고, RSI가 70
이상으로 올라오면 매도하는 단순한 전략 …"에서 120B가 매도 조각 'RSI가 70 이상으로 올라오면'을
매수 칸에도 복사했다(entry rsi >= 70 + exit rsi >= 70). 화면에는 "진입과 청산에 동일한 조건
(technical.rsi >= 70.0)이 있어 매수 직후 매도될 수 있습니다"가 떴다 — 안내는 출력대로였고, 틀린 것은
LLM 출력의 칸 배정이다.
"""

from __future__ import annotations

import json

from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.output_repair import (
    cross_role_duplicate_error,
    cross_role_duplicate_fields,
)

USER = ("KOSDAQ 종목 중 RSI가 30 이하로 떨어졌다가 다시 반등하는 종목을 매수하고, RSI가 70 이상으로 "
        "올라오면 매도하는 단순한 전략으로 만들어 주세요. 7종목, 손절 -8%로 부탁드립니다.")

REBOUND = {"factor": "technical.rsi", "operator": "crosses_above", "value": 30, "unit": "point",
           "source_text": "RSI가 30 이하로 떨어졌다가 다시 반등하는"}
SELL = {"factor": "technical.rsi", "operator": ">=", "value": 70, "unit": "point",
        "source_text": "RSI가 70 이상으로 올라오면"}


def _body(entry, exit_):
    return json.dumps({"intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": {
        "universe": {"markets": ["KOSDAQ"], "sectors": []},
        "entry_conditions": entry, "exit_conditions": exit_, "entry_logic": "AND",
        "portfolio": {"selection_count": 7}, "risk_management": {"stop_loss": 8}}},
        ensure_ascii=False)


def _intent(entry, exit_):
    return StrategyIntent.model_validate(json.loads(_body(entry, exit_)))


def test_sell_quote_copied_into_entry_is_flagged():
    paths = cross_role_duplicate_fields(_intent([REBOUND, SELL], [SELL]))
    assert paths == ["strategy.entry_conditions[1]", "strategy.exit_conditions[0]"]
    assert "매수를 말하는지 매도를 말하는지" in cross_role_duplicate_error(paths)


def test_distinct_entry_and_exit_are_not_flagged():
    assert cross_role_duplicate_fields(_intent([REBOUND], [SELL])) == []


def test_same_condition_with_different_quotes_is_not_flagged():
    """인용이 다르면 출력끼리 대조로는 복사라고 말할 수 없다 — 기존 충돌 안내가 맡는다."""
    other = dict(SELL, source_text="RSI 70 이상이면 매수")
    assert cross_role_duplicate_fields(_intent([REBOUND, other], [SELL])) == []


def test_cross_role_duplicate_regenerates_once():
    replies = iter([_body([REBOUND, SELL], [SELL]), _body([REBOUND], [SELL])])
    calls = []

    def fake_chat(system, user, **_):
        calls.append(user)
        return next(replies)

    result = StrategyInterpreter(chat_fn=fake_chat, model="stub-model").interpret(USER)
    strategy = result.intent.strategy
    assert len(calls) == 2
    assert result.repair_attempts == 1
    assert [(c.operator, c.value) for c in strategy.entry_conditions] == [("crosses_above", 30)]
    assert [(c.operator, c.value) for c in strategy.exit_conditions] == [(">=", 70)]


def test_cross_role_duplicate_left_in_place_when_regeneration_keeps_it():
    """재생성본도 같으면 그대로 진행한다(판정 없음 — 어느 칸이 맞는지 결정론이 정하지 않는다)."""
    bad = _body([REBOUND, SELL], [SELL])
    replies = iter([bad, bad])
    result = StrategyInterpreter(chat_fn=lambda s, u, **_: next(replies), model="stub-model").interpret(USER)
    assert len(result.intent.strategy.entry_conditions) == 2


# ── 2026-10-25 사고: 스키마 복구본이 새로 만든 중복 ─────────────────────────────────────────
# 원출력은 '이격도 90 이하 매수 / 100 이상 매도'를 맞게 나눴지만 매수 목록에 떠돌이 문자열
# "approximated"가 섞여 스키마 오류 → 복구 요청(한도 1회 소진) → 복구본이 매도 조건을 매수 칸에도
# 복사했다. 중복 재생성은 한도가 없어 못 돌았고, 화면엔 "진입 조건 모순" 안내 + 칩 없는 되묻기가 떴다.

DISP_USER = ("KOSPI 종목 중 20일선 이격도가 90 이하로 눌린 종목을 매수하고, 20일선 이격도가 100 이상으로 "
             "돌아오면 매도하고 싶습니다.")
DISP_BUY = {"factor": "technical.disparity", "operator": "<=", "value": 90, "unit": "point",
            "parameters": {"period": 20}, "source_text": "20일선 이격도가 90 이하로 눌린"}
DISP_SELL = {"factor": "technical.disparity", "operator": ">=", "value": 100, "unit": "point",
             "parameters": {"period": 20}, "source_text": "20일선 이격도가 100 이상으로 돌아오면 매도"}


def test_duplicate_introduced_by_schema_repair_is_dropped_without_another_call():
    replies = iter([_body([DISP_BUY, "approximated"], [DISP_SELL]),   # 스키마 위반 원출력(트레이스 그대로의 형태)
                    _body([DISP_BUY, DISP_SELL], [DISP_SELL])])        # 복구본이 매도를 매수 칸에 복사
    calls = []

    def fake_chat(system, user, **_):
        calls.append(user)
        return next(replies)

    result = StrategyInterpreter(chat_fn=fake_chat, model="stub-model").interpret(DISP_USER)
    strategy = result.intent.strategy
    assert len(calls) == 2
    assert [(c.operator, c.value) for c in strategy.entry_conditions] == [("<=", 90)]
    assert [(c.operator, c.value) for c in strategy.exit_conditions] == [(">=", 100)]


def test_duplicate_already_in_original_output_is_not_dropped_by_repair_guard():
    """원출력에서도 두 칸에 있던 중복은 복구가 만든 것이 아니다 — 결정론이 칸을 정하지 않는다."""
    replies = iter([_body([DISP_BUY, DISP_SELL, "approximated"], [DISP_SELL]),
                    _body([DISP_BUY, DISP_SELL], [DISP_SELL])])
    result = StrategyInterpreter(chat_fn=lambda s, u, **_: next(replies), model="stub-model").interpret(DISP_USER)
    assert len(result.intent.strategy.entry_conditions) == 2


def test_repair_guard_reads_original_whose_exit_list_slipped_outside_strategy():
    """실측 원출력 형태: 매수 목록 뒤 괄호가 일찍 닫혀 exit_conditions가 strategy 밖(최상위)에 있었다."""
    broken = json.dumps({"intent": "CREATE_STRATEGY", "confidence": 0.9,
                         "strategy": {"universe": {"markets": ["KOSPI"], "sectors": []},
                                      "entry_conditions": [DISP_BUY, "approximated"]},
                         "exit_conditions": [DISP_SELL], "entry_logic": "AND"}, ensure_ascii=False)
    replies = iter([broken, _body([DISP_BUY, DISP_SELL], [DISP_SELL])])
    result = StrategyInterpreter(chat_fn=lambda s, u, **_: next(replies), model="stub-model").interpret(DISP_USER)
    assert [(c.operator, c.value) for c in result.intent.strategy.entry_conditions] == [("<=", 90)]


def test_condition_moved_to_other_role_by_schema_repair_is_moved_back():
    """같은 사고의 다른 표본: 복구본이 매도 조건을 복사가 아니라 **옮겼다**(매도 칸 비움)."""
    replies = iter([_body([DISP_BUY, "approximated"], [DISP_SELL]), _body([DISP_BUY, DISP_SELL], [])])
    result = StrategyInterpreter(chat_fn=lambda s, u, **_: next(replies), model="stub-model").interpret(DISP_USER)
    strategy = result.intent.strategy
    assert [(c.operator, c.value) for c in strategy.entry_conditions] == [("<=", 90)]
    assert [(c.operator, c.value) for c in strategy.exit_conditions] == [(">=", 100)]


def test_condition_absent_from_original_is_left_where_repair_put_it():
    """원출력에 없던 조건은 대조 근거가 없다 — 칸을 결정론이 정하지 않는다."""
    replies = iter([_body([DISP_BUY, "approximated"], []), _body([DISP_BUY, DISP_SELL], [])])
    result = StrategyInterpreter(chat_fn=lambda s, u, **_: next(replies), model="stub-model").interpret(DISP_USER)
    assert len(result.intent.strategy.entry_conditions) == 2
