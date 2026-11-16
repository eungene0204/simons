"""해석 에이전트(실험 레인) 계약 — LLM이 고르는 편집의 결정론 관문과 배선.

고정 파이프라인의 보조 판정 자리에서 LLM이 조회·추가·교체·삭제를 스스로 고른다. 관문: 인용은
요청 문장에 실재, 숫자는 인용에 적힌 것만, 유니버스 경로 거절, 검증을 깨는 편집 거절.
"""

import json

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.planner import interpretation_agent as agent
from strategy_conversation.tools import call as call_tool

_UTTERANCE = "코스피에서 RSI 30 이하면 매수하고 손절은 7%로, RSI 70 이상이면 매도"
_RSI_BUY = {"factor": "technical.rsi", "operator": "<=", "value": 30, "source_text": "RSI 30 이하면 매수"}
_FINISH = json.dumps({"action": "finish"})


class _Chat:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.states = []

    def __call__(self, system_prompt, user_message, **_kwargs):
        self.states.append(json.loads(user_message))
        return self.responses.pop(0) if self.responses else ""


def _draft(**strategy):
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI"]}, "entry_conditions": [_RSI_BUY], **strategy}})
    out = call_tool("validate_intent", intent=intent)
    return out.intent, out.report


def _edit(quote, *patches):
    return json.dumps({"action": "edit", "quote": quote, "patches": list(patches)}, ensure_ascii=False)


def _run(*responses, **strategy):
    intent, report = _draft(**strategy)
    chat = _Chat(*responses)
    out, _report, summary = agent.run_interpretation_agent(intent, report, _UTTERANCE, chat)
    return out.strategy, summary, chat


def test_agent_adds_replaces_and_removes_on_its_own_draft():
    strategy, summary, _ = _run(
        _edit("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 7}),
        _edit("RSI 70 이상이면 매도", {"op": "add", "path": "/exit_conditions/-", "value": {
            "factor": "technical.rsi", "operator": ">=", "value": 70}}),
        json.dumps({"action": "edit", "patches": [{"op": "remove", "path": "/entry_conditions/1"}]}),
        _FINISH,
        risk_management={"stop_loss": 5},
        entry_conditions=[_RSI_BUY, {"factor": "fundamental.per", "operator": "<=", "value": 10,
                                     "source_text": "지어낸 조건"}],
    )
    assert strategy.risk_management.stop_loss == 7  # 채우기 전용이 아니다 — 값 있는 칸도 고친다
    assert [c.factor for c in strategy.entry_conditions] == ["technical.rsi"]
    assert strategy.exit_conditions[0].source_text == "RSI 70 이상이면 매도"
    assert summary == {"outcome": "finish", "edits": 3, "steps": 3}


def test_ungrounded_edits_are_rejected_with_a_reason():
    strategy, summary, chat = _run(
        _edit("손절은 9%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 9}),
        _edit("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 8}),
        _edit("코스피에서", {"op": "replace", "path": "/universe/markets", "value": ["KOSDAQ"]}),
        _FINISH,
    )
    assert strategy.risk_management.stop_loss is None and summary["edits"] == 0
    reasons = [step["observation"]["rejected"] for step in chat.states[3]["steps"]]
    assert "요청 문장" in reasons[0] and "quote에 없습니다" in reasons[1] and "경로" in reasons[2]


def test_repeat_gets_feedback_once_then_stops():
    lookup = json.dumps({"action": "lookup", "terms": ["RSI"]})
    _, summary, chat = _run(lookup, lookup, lookup)
    assert summary["outcome"] == "stalled" and len(chat.states) == 3


def test_malformed_output_keeps_the_draft():
    strategy, summary, _ = _run("JSON 아님")
    assert summary["outcome"] == "contract_violation" and strategy.entry_conditions[0].value == 30


def test_agent_lane_is_wired_behind_the_flag(monkeypatch):
    from strategy_conversation import primary

    class _Result:
        intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
            "universe": {"markets": ["KOSPI"]}, "entry_conditions": [_RSI_BUY]}})
        model_name = prompt_version = "test"
        repair_attempts = 0
        latency_ms = 0.0
        unreflected_numbers = []

    chat = _Chat(_edit("손절은 7%로", {"op": "replace", "path": "/risk_management/stop_loss", "value": 7}), _FINISH)

    class _Interpreter:
        _chat = staticmethod(chat)

        def interpret(self, *_a, **_k):
            return _Result()

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())
    assert primary.run_primary_parse(_UTTERANCE)["interpreter"]["mode"] == "primary"  # 기본은 고정 파이프라인
    monkeypatch.setenv("STRATEGY_INTERPRETATION_AGENT_MODE", "primary")
    result = primary.run_primary_parse(_UTTERANCE)
    assert result["interpreter"]["mode"] == "agent" and result["parsed"].stop_loss_pct == 7
    assert result["interpreter"]["agent"] == {"outcome": "finish", "edits": 1, "steps": 1}
