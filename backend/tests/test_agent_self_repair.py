"""완전한 에이전트 루프 회귀(2026-11-16) — 실패 자가 복구 · 원인별 실패 안내 · 값 확인 질문.

- 자가 복구: 하류(패치 적용·검증·컴파일)가 거부한 출력은 사유와 함께 인터프리터에 한 번 돌려준다.
  가상 사용자 실측(2026-11-16 SU07): 재진술 발화의 패치 묶음 중 하나가 틀려 수정 전체가
  "해석하지 못했어요"로 끝났다.
- 원인별 안내: 그래도 실패하면 사유 라벨로 정해진 문구를 고른다(일반 문구 한 줄로 뭉개지 않는다).
- 값 확인: 자기 검증 에이전트가 틀렸다고 본 숫자 한 칸은 고치지 않고 사용자에게 묻는다.
"""

import pytest

import main
from engine.nl_parser import ParsedStrategy, TechnicalSignal
from main import NLParseRequest, _run_nl_parse
from strategy_conversation import primary
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.tools import call as call_tool


@pytest.fixture(autouse=True)
def _clean():
    main._nl_parse_cache.clear()
    primary.take_failure()
    yield
    main._nl_parse_cache.clear()
    primary.take_failure()


def _previous(**overrides) -> dict:
    base = dict(
        description="골든크로스 매수, 데드크로스 매도",
        entry_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="buy")],
        exit_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="sell")],
        target_symbols=["005930", "000660"], stop_loss_pct=15.0, take_profit_pct=30.0,
    )
    base.update(overrides)
    return ParsedStrategy(**base).model_dump()


def _scripted_interpreter(monkeypatch, *intents):
    """호출마다 다음 출력을 내는 인터프리터 — 받은 repair_from을 기록한다."""
    seen = []
    queue = [StrategyIntent.model_validate(intent) for intent in intents]

    class _Interpreter:
        def interpret(self, *_a, repair_from=None, **_k):
            seen.append(repair_from)
            intent = queue.pop(0)
            return type("R", (), {
                "intent": intent, "raw_output": intent.model_dump_json(), "model_name": "test",
                "prompt_version": "test", "repair_attempts": 0, "latency_ms": 0.0,
                "unreflected_numbers": []})()

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())
    return seen


_BAD_PATCH = {"intent": "MODIFY_STRATEGY", "confidence": 1.0, "patches": [
    {"op": "replace", "path": "/entry_conditions/7/value", "value": 40, "source_text": "손절을 7%로 바꿔줘"}]}
_GOOD_PATCH = {"intent": "MODIFY_STRATEGY", "confidence": 1.0, "patches": [
    {"op": "replace", "path": "/risk_management/stop_loss", "value": 7, "source_text": "손절을 7%로"}]}


# ── 자가 복구 ────────────────────────────────────────────────────────────────

def test_rejected_patch_is_sent_back_with_the_reason_and_the_retry_is_applied(monkeypatch):
    seen = _scripted_interpreter(monkeypatch, _BAD_PATCH, _GOOD_PATCH)
    result = primary.run_primary_modification("손절을 7%로 바꿔줘", _previous())

    assert result is not None and result["parsed"].stop_loss_pct == 7
    # 두 번째 호출은 거부된 원출력과 사유를 함께 받는다.
    assert seen[0] is None
    bad_output, reason = seen[1]
    assert "/entry_conditions/7/value" in bad_output and "적용하지 못했습니다" in reason
    assert primary.take_failure() is None


def test_self_repair_runs_once_and_leaves_the_reason_for_the_caller(monkeypatch):
    seen = _scripted_interpreter(monkeypatch, _BAD_PATCH, _BAD_PATCH)
    assert primary.run_primary_modification("손절을 7%로 바꿔줘", _previous()) is None
    assert len(seen) == 2  # 무한 재시도 금지
    assert primary.take_failure()["code"] == "PATCH_INVALID"
    assert primary.take_failure() is None  # 꺼내면 비운다


def test_failure_without_a_model_output_is_not_retried():
    calls = []

    def run_once(repair_from=None):
        calls.append(repair_from)
        primary._note_failure("NOT_STRATEGY", "OFF_TOPIC")
        return None

    assert primary._self_repairing(run_once) is None
    assert calls == [None]


def test_no_patches_verdict_is_not_second_guessed(monkeypatch):
    """'바꿀 것 없음'도 LLM의 판정이다 — 패치를 내라고 다시 밀지 않고 안내 문구만 고른다."""
    seen = _scripted_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "confidence": 1.0, "patches": []})
    result = _run_nl_parse(NLParseRequest(prompt="음 그대로 좋네", previous_parsed=_previous()))
    assert len(seen) == 1
    assert result["clarification_question"] == main._FAILURE_REASON_MODIFY_MESSAGES["NO_PATCHES"]


def test_interpreter_resends_the_rejected_output_with_the_reason():
    """실제 인터프리터의 자가 복구 분기 — 첫 호출이 거부된 출력과 사유를 실은 재요청이다."""
    from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter

    prompts = []

    def chat(system, user, **_kwargs):
        prompts.append(user)
        return '{"intent": "MODIFY_STRATEGY", "strategy": null, "patches": [{"op": "replace", ' \
               '"path": "/risk_management/stop_loss", "value": 7, "source_text": "손절을 7%로"}]}'

    draft = {"risk_management": {"stop_loss": 15}}
    result = StrategyInterpreter(chat_fn=chat, model="stub").interpret(
        "손절을 7%로 바꿔줘", draft=draft,
        repair_from=('{"patches": [{"path": "/entry_conditions/7/value"}]}', "Condition pointer has no identity"))

    assert result.intent.patches[0].path == "/risk_management/stop_loss"
    assert "반영되지 못했습니다" in prompts[0] and "Condition pointer has no identity" in prompts[0]
    assert "/entry_conditions/7/value" in prompts[0] and "손절을 7%로 바꿔줘" in prompts[0]


def test_schema_failure_carries_the_last_output_for_self_repair(monkeypatch):
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        InterpreterError, StrategyInterpreter)

    broken = '{"intent": "MODIFY_STRATEGY", "patches": [{"op": "replace"'
    with pytest.raises(InterpreterError) as caught:
        StrategyInterpreter(chat_fn=lambda *_a, **_k: broken, model="stub").interpret(
            "손절을 7%로 바꿔줘", draft={"risk_management": {"stop_loss": 15}})
    assert caught.value.raw_output == broken


# ── 원인별 실패 안내 ─────────────────────────────────────────────────────────

def test_modify_failure_names_what_went_wrong(monkeypatch):
    _scripted_interpreter(monkeypatch, _BAD_PATCH, _BAD_PATCH)
    result = _run_nl_parse(NLParseRequest(prompt="손절을 7%로 바꿔줘", previous_parsed=_previous()))

    assert result["clarification_question"] == main._FAILURE_REASON_MODIFY_MESSAGES["PATCH_INVALID"]
    assert result["clarification_priority"] == "interpretation_failed"
    assert result["parsed"]["stop_loss_pct"] == 15.0  # 전략은 그대로다


def test_unlabelled_failure_keeps_the_general_message(monkeypatch):
    monkeypatch.setattr(primary, "run_primary_modification", lambda *_a, **_k: None)
    result = _run_nl_parse(NLParseRequest(prompt="뭔가 바꿔줘", previous_parsed=_previous()))
    assert result["clarification_question"] == main._INTERPRETATION_FAILURE_MESSAGE


def test_failure_messages_pass_the_output_guard():
    from strategy_conversation.response.output_guard import guard_text

    for message in (*main._FAILURE_REASON_MODIFY_MESSAGES.values(),
                    *main._FAILURE_REASON_CREATE_MESSAGES.values()):
        assert guard_text(message) == message


# ── 값 확인 질문 ─────────────────────────────────────────────────────────────

def _compiled(stop_loss=5):
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [{"factor": "technical.rsi", "operator": "<=", "value": 30,
                              "source_text": "RSI 30 이하면 매수"}],
        "risk_management": {"stop_loss": stop_loss}}})
    checked = call_tool("validate_intent", intent=intent)
    parsed = call_tool("compile_strategy", intent=checked.intent, report=checked.report,
                       user_input="x", partial=not checked.report.is_valid).parsed
    return checked.intent, checked.report, parsed


_CORRECTION = [{"path": "/risk_management/stop_loss", "quote": "손절은 7%로", "current": 5, "proposed": 7}]


def test_value_check_asks_with_chips_bound_to_both_values():
    validated, report, parsed = _compiled()
    question, chips, ask = primary._value_check_ask(
        _CORRECTION, validated, report, parsed, parsed, "x", not report.is_valid)

    assert chips == ["손절 기준 7%", "손절 기준 5% 유지"]
    assert "손절은 7%로" in question and "5%" in question and "7%" in question
    assert ask["chip_bindings"] == {"손절 기준 7%": {"stop_loss_pct": 7.0},
                                    "손절 기준 5% 유지": {"stop_loss_pct": 5.0}}
    # 칩 클릭은 결속값을 그대로 적용한다 — LLM 재해석이 없다.
    changed = primary.run_chip_answer("손절 기준 7%", parsed.model_dump(), ask)
    kept = primary.run_chip_answer("손절 기준 5% 유지", parsed.model_dump(), ask)
    assert changed["parsed"].stop_loss_pct == 7 and kept["parsed"].stop_loss_pct == 5


def test_value_check_is_skipped_when_a_later_stage_changed_the_field():
    validated, report, parsed = _compiled()
    later = parsed.model_copy(update={"stop_loss_pct": 6.0})
    assert primary._value_check_ask(
        _CORRECTION, validated, report, parsed, later, "x", not report.is_valid) is None


def test_value_check_goes_first_and_queues_the_planned_question():
    value_ask = ("값이 달라 보여요", ["손절 기준 7%", "손절 기준 5% 유지"],
                 {"question": "값이 달라 보여요", "topic": "값 확인", "chips": ["손절 기준 7%"]})
    planned = {"question": "리밸런싱은요?", "topic": "리밸런싱", "chips": ["매월"], "queue": [{"question": "기간은요?"}]}
    question, chips, priority, ask = primary._with_value_check(
        value_ask, "리밸런싱은요?", ["매월"], "dag_planner", planned)

    assert (question, priority) == ("값이 달라 보여요", "pending_values")
    assert ask["queue"] == [{"question": "리밸런싱은요?", "topic": "리밸런싱", "chips": ["매월"]},
                            {"question": "기간은요?"}]
    # 전략을 바꾸지 못해 되묻는 턴(수정 미반영·업종 미해결)은 그 질문이 먼저다.
    assert primary._with_value_check(value_ask, "다시 알려주세요", None, "modify_unapplied", None)[0] \
        == "다시 알려주세요"


def test_modify_turn_runs_the_verify_agent_and_asks_about_a_wrong_value(monkeypatch):
    from strategy_conversation.planner import verify_agent

    _scripted_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "confidence": 1.0, "patches": [
        {"op": "replace", "path": "/risk_management/take_profit", "value": 20, "source_text": "익절 20%"}]})
    monkeypatch.setattr(primary._get_interpreter(None).__class__, "_chat",
                        staticmethod(lambda *_a, **_k: ""), raising=False)
    monkeypatch.setenv("STRATEGY_VERIFY_AGENT_MODE", "primary")
    calls = []

    def fake(intent, report, utterance, chat_fn, blocked=frozenset(), pending_question=None,
             blocked_paths=frozenset()):
        calls.append((utterance, pending_question))
        return verify_agent.VerifyOutcome(intent=intent, report=report, corrections=[
            {"path": "/risk_management/stop_loss", "quote": "손절 7%", "current": 15.0, "proposed": 7}])

    monkeypatch.setattr(verify_agent, "verify_interpretation", fake)
    result = primary.run_primary_modification("익절 20%, 손절 7%", _previous())

    assert calls == [("익절 20%, 손절 7%", None)]
    assert result["parsed"].take_profit_pct == 20 and result["parsed"].stop_loss_pct == 15  # 고치지 않았다
    assert result["pending_ask"]["topic"] == "값 확인"
    assert result["clarification_suggestions"] == ["손절 기준 7%", "손절 기준 15% 유지"]


def test_modify_turn_tells_the_verify_agent_what_this_turn_removed(monkeypatch):
    """"데드크로스 매도는 빼줘"로 지운 조건을 자기 검증이 '말했는데 빠진 것'으로 되살리지 못하게 넘긴다."""
    from strategy_conversation.planner import verify_agent

    _scripted_interpreter(monkeypatch, {"intent": "MODIFY_STRATEGY", "confidence": 1.0, "patches": [
        {"op": "remove", "path": "/exit_conditions/0", "source_text": "데드크로스 매도는 빼줘"}]})
    monkeypatch.setattr(primary._get_interpreter(None).__class__, "_chat",
                        staticmethod(lambda *_a, **_k: ""), raising=False)
    monkeypatch.setenv("STRATEGY_VERIFY_AGENT_MODE", "primary")
    seen = {}

    def fake(intent, report, utterance, chat_fn, blocked=frozenset(), pending_question=None,
             blocked_paths=frozenset()):
        seen.update(blocked=blocked, blocked_paths=blocked_paths)
        return None

    monkeypatch.setattr(verify_agent, "verify_interpretation", fake)
    result = primary.run_primary_modification("데드크로스 매도는 빼줘", _previous())

    assert not result["parsed"].exit_signals
    assert ("exit_conditions", "technical.ma_crossover") in seen["blocked"]
