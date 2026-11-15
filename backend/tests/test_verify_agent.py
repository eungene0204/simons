"""해석 자기 검증 에이전트 계약 — 도구 루프의 결정론 관문.

핵심: 채우기만 수락(값 있는 칸 교체·삭제 거절), quote는 요청 문장에 실재, 숫자는 quote에
적힌 것만, 유니버스 경로 거절, 가드가 뺀 조건 재삽입 거절, 검증 실패는 사유를 관찰로 돌려주고
다음 턴에 고칠 수 있다. 채운 것이 없으면 None(원래 결과 유지).
"""

import json

import pytest

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.planner.verify_agent import verify_interpretation
from strategy_conversation.tools import call as call_tool

_UTTERANCE = "코스피에서 RSI 30 이하면 매수하고 손절은 7%로, RSI 70 이상이면 매도"
_RSI_BUY = {"factor": "technical.rsi", "operator": "<=", "value": 30,
            "source_text": "RSI 30 이하면 매수"}
_FINISH = json.dumps({"action": "finish"})


class ScriptedChat:
    def __init__(self, responses):
        self.responses = list(responses)
        self.states = []

    def __call__(self, system_prompt, user_message, **kwargs):
        self.states.append(json.loads(user_message))
        return self.responses.pop(0) if self.responses else ""


def _validated(**strategy):
    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY",
        "strategy": {"universe": {"markets": ["KOSPI"]}, "entry_conditions": [_RSI_BUY], **strategy},
    })
    out = call_tool("validate_intent", intent=intent)
    return out.intent, out.report


def _patch(quote, *patches):
    return json.dumps({"action": "patch", "quote": quote, "patches": list(patches)},
                      ensure_ascii=False)


def _run(responses, blocked=frozenset(), **strategy):
    intent, report = _validated(**strategy)
    chat = ScriptedChat(responses)
    return verify_interpretation(intent, report, _UTTERANCE, chat, blocked=blocked), chat, intent


def test_finish_without_changes_returns_none():
    result, chat, _ = _run([_FINISH])
    assert result is None
    assert len(chat.states) == 1


def test_fills_missing_risk_field_and_exit_condition():
    result, chat, original = _run([
        _patch("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 7}),
        json.dumps({"action": "lookup", "terms": ["RSI"]}),
        _patch("RSI 70 이상이면 매도", {"op": "add", "path": "/exit_conditions/-", "value": {
            "factor": "technical.rsi", "operator": ">=", "value": 70}}),
        _FINISH,
    ])
    intent = result.intent
    assert result.filled == 2 and [p.path for p in result.patches] == [
        "/risk_management/stop_loss", "/exit_conditions/-"]
    assert intent.strategy.risk_management.stop_loss == 7
    exit_condition, = intent.strategy.exit_conditions
    assert (exit_condition.factor, exit_condition.value) == ("technical.rsi", 70)
    # 추가된 조건의 인용은 관문을 통과한 quote다.
    assert exit_condition.source_text == "RSI 70 이상이면 매도"
    # 조회 관찰이 다음 턴 상태에 실린다.
    lookup, = chat.states[2]["steps"][1]["observation"]["results"]
    assert lookup["term"] == "RSI"
    assert "technical.rsi" in [i["factor"] for i in lookup["indicators"]]
    # 원본은 그대로다.
    assert original.strategy.risk_management.stop_loss is None


def test_rejects_overwriting_existing_value():
    result, chat, _ = _run([
        _patch("RSI 30 이하면 매수", {"op": "replace", "path": "/entry_conditions/0/value", "value": 30},
               {"op": "replace", "path": "/entry_conditions/0/operator", "value": "<"}),
        _FINISH,
    ])
    assert result is None
    assert "바꿀 수 없습니다" in chat.states[1]["steps"][0]["observation"]["rejected"]


def test_rejects_quote_not_in_utterance():
    result, chat, _ = _run([
        _patch("익절은 20%", {"op": "replace", "path": "/risk_management/take_profit", "value": 20}),
        _FINISH,
    ])
    assert result is None
    assert "quote" in chat.states[1]["steps"][0]["observation"]["rejected"]


def test_rejects_number_not_in_quote():
    result, chat, _ = _run([
        _patch("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 5}),
        _FINISH,
    ])
    assert result is None
    assert "quote에 없습니다" in chat.states[1]["steps"][0]["observation"]["rejected"]


@pytest.mark.parametrize("quote, patch", [
    ("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": "5%"}),
    ("손절은 7%로", {"op": "replace", "path": "/backtest/period", "value": "3y"}),
    ("RSI 70 이상이면 매도", {"op": "add", "path": "/exit_conditions/-", "value": {
        "factor": "technical.rsi", "operator": ">=", "value": "80"}}),
    ("RSI 70 이상이면 매도", {"op": "add", "path": "/exit_conditions/-", "value": {
        "factor": "technical.rsi", "operator": ">=", "value": 70, "parameters": {"period": "9"}}}),
])
def test_rejects_number_written_as_string(quote, patch):
    """숫자를 문자열로 내도 스키마가 수로 바꾼다 — 정규화 뒤 값을 인용과 대조한다."""
    result, chat, _ = _run([_patch(quote, patch), _FINISH])
    assert result is None
    assert "quote에 없습니다" in chat.states[1]["steps"][0]["observation"]["rejected"]


def test_lookup_rejects_sentence_length_input():
    result, chat, _ = _run([json.dumps({"action": "lookup", "terms": [_UTTERANCE]}), _FINISH])
    assert result is None
    assert "rejected" in chat.states[1]["steps"][0]["observation"]["results"][0]


def test_lookup_answers_each_term_separately():
    """여러 지표를 한 표현에 묶으면 등록부 대조가 빈손이었다(2026-11-15 Trace) — 이름마다 따로 답한다."""
    _, chat, _ = _run([
        json.dumps({"action": "lookup", "terms": ["볼린저밴드 하단", "RSI", "소매유통 테마"]}),
        _FINISH,
    ])
    bollinger, rsi, theme = chat.states[1]["steps"][0]["observation"]["results"]
    assert "technical.bollinger_lower_touch" in [i["factor"] for i in bollinger["indicators"]]
    assert [i["factor"] for i in rsi["indicators"]] == ["technical.rsi"]
    # 빈 결과는 사유를 함께 준다 — 빈 목록만 주면 표현만 바꿔 같은 조회를 되풀이한다.
    assert theme["indicators"] == [] and "유니버스" in theme["note"]


def test_lookup_without_term_list_is_rejected_with_shape_hint():
    _, chat, _ = _run([json.dumps({"action": "lookup", "text": "RSI"}), _FINISH])
    assert "terms" in chat.states[1]["steps"][0]["observation"]["rejected"]


def test_chat_failure_keeps_accepted_fills():
    intent, report = _validated()
    responses = [_patch("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 7})]

    def chat(system, user, **kwargs):
        if not responses:
            raise RuntimeError("upstream")
        return responses.pop(0)

    result = verify_interpretation(intent, report, _UTTERANCE, chat)
    assert result.intent.strategy.risk_management.stop_loss == 7


def test_mode_defaults_off_for_unknown_value(monkeypatch):
    from strategy_conversation import config

    monkeypatch.setenv("STRATEGY_VERIFY_AGENT_MODE", "shadow")
    assert config.verify_agent_mode() == "off"
    monkeypatch.setenv("STRATEGY_VERIFY_AGENT_MAX_STEPS", "99")
    assert config.verify_agent_max_steps() == 8


def test_rejects_universe_and_remove():
    result, chat, _ = _run([
        _patch("코스피에서", {"op": "replace", "path": "/universe/markets", "value": ["KOSDAQ"]}),
        _patch("RSI 30 이하면 매수", {"op": "remove", "path": "/entry_conditions/0"}),
        _FINISH,
    ])
    assert result is None
    assert all("rejected" in s["observation"] for s in chat.states[2]["steps"])


def test_rejects_condition_excluded_by_guards():
    result, _, _ = _run([
        _patch("RSI 70 이상이면 매도", {"op": "add", "path": "/exit_conditions/-", "value": {
            "factor": "RSI", "operator": ">=", "value": 70}}),
        _FINISH,
    ], blocked=frozenset({("exit_conditions", "technical.rsi")}))
    assert result is None


def test_validation_failure_is_observed_then_repaired():
    """검증 거절 사유를 관찰로 받고 다음 턴에 고쳐 낸다(도구 루프)."""
    result, chat, _ = _run([
        _patch("RSI 70 이상이면 매도", {"op": "add", "path": "/exit_conditions/-", "value": {
            "factor": "없는지표", "operator": ">=", "value": 70}}),
        _patch("RSI 70 이상이면 매도", {"op": "add", "path": "/exit_conditions/-", "value": {
            "factor": "technical.rsi", "operator": ">=", "value": 70}}),
        _FINISH,
    ])
    assert "rejected" in chat.states[1]["steps"][0]["observation"]
    assert result is not None and len(result.intent.strategy.exit_conditions) == 1


def test_repeated_action_and_budget_keep_accepted_fills():
    fill = _patch("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 7})
    result, chat, _ = _run([fill, fill, fill, _FINISH])
    assert result.intent.strategy.risk_management.stop_loss == 7
    # 같은 행동의 첫 반복은 사유를 돌려주고 잇고, 두 번째 반복에서 끝낸다(무한 반복 금지).
    assert len(chat.states) == 3
    assert "이미 한 행동" in chat.states[2]["steps"][1]["observation"]["rejected"]


def test_repeated_lookup_gets_feedback_and_the_agent_can_still_finish():
    """채울 것이 없는 턴이 같은 조회 반복으로 '규칙 위반' 종료되던 실측(2026-11-16 10턴 중 8턴)."""
    lookup = json.dumps({"action": "lookup", "terms": ["RSI"]})
    result, chat, _ = _run([lookup, lookup, _FINISH])
    assert result is None and len(chat.states) == 3


def test_patch_that_changes_nothing_is_not_a_fill():
    result, chat, _ = _run([
        _patch("RSI 30 이하면 매수", {"op": "add", "path": "/entry_conditions/0/value", "value": 30}),
        _FINISH,
    ])
    assert result is None
    assert "rejected" in chat.states[1]["steps"][0]["observation"]


def test_field_cleared_by_this_turn_is_not_refilled():
    """수정 턴: 사용자가 이번에 비운 칸을 '말했는데 빠진 것'으로 되채우면 삭제를 뒤집는다."""
    intent, report = _validated()
    chat = ScriptedChat([
        _patch("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 7}),
        _FINISH])
    result = verify_interpretation(intent, report, _UTTERANCE, chat,
                                   blocked_paths=frozenset({"/risk_management/stop_loss"}))
    assert result is None
    assert "비운 칸" in chat.states[1]["steps"][0]["observation"]["rejected"]


# ── 값 확인 후보(corrections) ────────────────────────────────────────────────

def _finish_with(*concerns):
    return json.dumps({"action": "finish", "concerns": list(concerns)}, ensure_ascii=False)


def test_wrong_number_becomes_a_correction_candidate_not_an_edit():
    """틀려 보이는 값은 고치지 않는다 — 요청 문장의 값과 나란히 후보로 돌려주고 사용자가 고른다."""
    result, _, _ = _run([_finish_with(
        {"path": "/risk_management/stop_loss", "quote": "손절은 7%로", "value": 7, "reason": "5로 들어감"},
    )], risk_management={"stop_loss": 5})
    assert result.filled == 0
    assert result.intent.strategy.risk_management.stop_loss == 5
    assert result.corrections == [
        {"path": "/risk_management/stop_loss", "quote": "손절은 7%로", "current": 5, "proposed": 7}]


@pytest.mark.parametrize("concern", [
    # 인용이 요청 문장에 없다
    {"path": "/risk_management/stop_loss", "quote": "손절은 9%로", "value": 9},
    # 제안값이 인용에 적힌 숫자가 아니다
    {"path": "/risk_management/stop_loss", "quote": "손절은 7%로", "value": 8},
    # 이름을 붙여 물을 수 없는 칸이다
    {"path": "/universe/markets", "quote": "손절은 7%로", "value": 7},
    # 인용에 지금 값도 함께 적혀 있어 어느 칸의 값인지 가릴 수 없다
    {"path": "/entry_conditions/0/value", "quote": "RSI 30 이하면 매수하고 손절은 7%로", "value": 7},
    # 값이 없는 후보
    {"path": "/risk_management/stop_loss", "quote": "손절은 7%로"},
])
def test_ungrounded_concern_stays_out_of_corrections(concern):
    result, _, _ = _run([_finish_with(concern)], risk_management={"stop_loss": 5})
    assert result is None


def test_condition_value_can_be_a_correction_candidate():
    result, _, _ = _run([_finish_with(
        {"path": "/exit_conditions/0/value", "quote": "RSI 70 이상이면 매도", "value": 70},
    )], exit_conditions=[{"factor": "technical.rsi", "operator": ">=", "value": 60,
                          "source_text": "RSI 70 이상이면 매도"}])
    assert result.corrections[0]["current"] == 60 and result.corrections[0]["proposed"] == 70


def test_pending_question_is_shown_to_the_agent():
    intent, report = _validated()
    chat = ScriptedChat([_FINISH])
    verify_interpretation(intent, report, "7%", chat, pending_question="손절 기준을 몇 %로 할까요?")
    assert chat.states[0]["pending_question"] == "손절 기준을 몇 %로 할까요?"


def test_malformed_output_returns_none():
    result, _, _ = _run(["JSON 아님"])
    assert result is None


# ── run_primary_parse 배선 ────────────────────────────────────────────────────

def _stub_interpreter(monkeypatch, markets=("KOSPI",), exit_conditions=()):
    from strategy_conversation import primary

    class _Result:
        intent = StrategyIntent.model_validate({
            "intent": "CREATE_STRATEGY",
            "strategy": {"universe": {"markets": list(markets)}, "entry_conditions": [_RSI_BUY],
                         "exit_conditions": list(exit_conditions)},
        })
        model_name = prompt_version = "test"
        repair_attempts = 0
        latency_ms = 0.0
        unreflected_numbers = []

    class _Interpreter:
        _chat = staticmethod(lambda *_a, **_k: "")

        def interpret(self, *_a, **_k):
            return _Result()

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())
    return primary


def _fill_stop_loss(monkeypatch, calls):
    from strategy_conversation.planner import verify_agent

    def fake(intent, report, utterance, chat_fn, blocked=frozenset()):
        calls.append(blocked)
        intent = intent.model_copy(deep=True)
        intent.strategy.risk_management.stop_loss = 7
        out = call_tool("validate_intent", intent=intent)
        return verify_agent.VerifyOutcome(intent=out.intent, report=out.report, filled=1)

    monkeypatch.setattr(verify_agent, "verify_interpretation", fake)


def test_primary_parse_adopts_agent_fill_when_enabled(monkeypatch):
    primary = _stub_interpreter(monkeypatch)
    calls = []
    _fill_stop_loss(monkeypatch, calls)
    monkeypatch.setenv("STRATEGY_VERIFY_AGENT_MODE", "primary")
    result = primary.run_primary_parse(_UTTERANCE)
    assert calls == [frozenset()]
    assert result["parsed"].stop_loss_pct == 7


def test_primary_parse_skips_agent_by_default(monkeypatch):
    primary = _stub_interpreter(monkeypatch)
    calls = []
    _fill_stop_loss(monkeypatch, calls)
    result = primary.run_primary_parse(_UTTERANCE)
    assert calls == []
    assert result["parsed"].stop_loss_pct is None


def test_primary_parse_passes_dropped_conditions_as_blocked(monkeypatch):
    """인용이 요청 문장에 없는 조건은 가드가 빼고, 에이전트가 다시 넣지 못하게 넘어간다."""
    primary = _stub_interpreter(monkeypatch, exit_conditions=[{
        "factor": "technical.macd", "operator": "crosses_below", "source_text": "전혀 없는 문구입니다"}])
    calls = []
    _fill_stop_loss(monkeypatch, calls)
    monkeypatch.setenv("STRATEGY_VERIFY_AGENT_MODE", "primary")
    primary.run_primary_parse(_UTTERANCE)
    assert calls == [frozenset({("exit_conditions", "technical.macd")})]


def test_primary_parse_skips_agent_for_us_universe(monkeypatch):
    primary = _stub_interpreter(monkeypatch, markets=("NASDAQ",))
    calls = []
    _fill_stop_loss(monkeypatch, calls)
    monkeypatch.setenv("STRATEGY_VERIFY_AGENT_MODE", "primary")
    primary.run_primary_parse(_UTTERANCE)
    assert calls == []
