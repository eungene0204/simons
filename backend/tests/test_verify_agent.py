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
        json.dumps({"action": "lookup", "text": "RSI"}),
        _patch("RSI 70 이상이면 매도", {"op": "add", "path": "/exit_conditions/-", "value": {
            "factor": "technical.rsi", "operator": ">=", "value": 70}}),
        _FINISH,
    ])
    intent, _ = result
    assert intent.strategy.risk_management.stop_loss == 7
    exit_condition, = intent.strategy.exit_conditions
    assert (exit_condition.factor, exit_condition.value) == ("technical.rsi", 70)
    # 추가된 조건의 인용은 관문을 통과한 quote다.
    assert exit_condition.source_text == "RSI 70 이상이면 매도"
    # 조회 관찰이 다음 턴 상태에 실린다.
    lookup = chat.states[2]["steps"][1]["observation"]["indicators"]
    assert "technical.rsi" in [i["factor"] for i in lookup]
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
    result, chat, _ = _run([json.dumps({"action": "lookup", "text": _UTTERANCE}), _FINISH])
    assert result is None
    assert "rejected" in chat.states[1]["steps"][0]["observation"]


def test_chat_failure_keeps_accepted_fills():
    intent, report = _validated()
    responses = [_patch("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 7})]

    def chat(system, user, **kwargs):
        if not responses:
            raise RuntimeError("upstream")
        return responses.pop(0)

    result = verify_interpretation(intent, report, _UTTERANCE, chat)
    assert result[0].strategy.risk_management.stop_loss == 7


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
    assert result is not None and len(result[0].strategy.exit_conditions) == 1


def test_repeated_action_and_budget_keep_accepted_fills():
    fill = _patch("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 7})
    result, chat, _ = _run([fill, fill, _FINISH])
    assert result[0].strategy.risk_management.stop_loss == 7
    assert len(chat.states) == 2  # 같은 액션 반복은 즉시 종료


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
        return out.intent, out.report

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
