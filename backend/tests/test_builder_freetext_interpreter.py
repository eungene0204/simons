"""빌더 자유 서술 LLM 해석기(계약 단계 3 C안, 2026-07-26) 회귀.

경계 계약: 칩·값 답변은 결정적 형식 정규화가 즉답(기존 퍼징 QA 게이트 보존),
결정적 레이어가 아무것도 해석하지 못한 자유 서술만 LLM 레인이 해석한다.
LLM 출력은 결정적 검증(필드 화이트리스트·값 대조·인용 게이트·삭제=채워진 필드만)을
통과한 op만 적용되고, 실패는 기존 미인식 안내를 유지한다(원문 재해석 폴백 없음).
"""

import json

import pytest

from intent import strategy_builder as sb
from intent.builder_interpreter import freetext_llm_enabled, interpret_utterance


def _chat_returning(ops):
    payload = json.dumps({"ops": ops}, ensure_ascii=False)
    return lambda system, user, max_tokens=300: payload


def test_set_risk_value_applies_with_quote_and_number(monkeypatch):
    state = sb.BuilderState(strategy_type="momentum")
    chat = _chat_returning([
        {"op": "set", "field": "stop_loss_pct", "value": 10,
         "source_text": "10프로 빠지면 팔아"},
    ])
    patch, notes = interpret_utterance("10프로 빠지면 팔아줬으면 해", state, chat)
    assert patch["stop_loss_pct"] == 10
    assert patch["risk_done"] is True
    assert notes == []


def test_hallucinated_number_is_rejected():
    state = sb.BuilderState()
    chat = _chat_returning([
        {"op": "set", "field": "stop_loss_pct", "value": 15,
         "source_text": "적당히 잃으면 팔아"},
    ])
    # 입력에 15가 없다 — 수치 대조 게이트가 거부, 전 op 탈락이면 None(미인식 흐름 유지)
    assert interpret_utterance("적당히 잃으면 팔아", state, chat) is None


def test_missing_quote_is_rejected():
    state = sb.BuilderState()
    chat = _chat_returning([
        {"op": "set", "field": "holding_count", "value": 5, "source_text": "다섯 종목 부탁"},
    ])
    # source_text가 입력에 실재하지 않으면 거부(출처 대조)
    assert interpret_utterance("5개 종목으로 부탁해", state, chat) is None


def test_remove_only_filled_fields():
    chat = _chat_returning([
        {"op": "remove", "field": "take_profit_pct", "source_text": "익절은 없던 걸로"},
    ])
    empty = sb.BuilderState()
    assert interpret_utterance("익절은 없던 걸로 하자", empty, chat) is None

    filled = sb.BuilderState(take_profit_pct=20.0, stop_loss_pct=10.0, risk_done=True)
    patch, _ = interpret_utterance("익절은 없던 걸로 하자", filled, chat)
    assert patch == {"take_profit_pct": None}


def test_removing_last_risk_value_reopens_risk_step():
    chat = _chat_returning([
        {"op": "remove", "field": "stop_loss_pct", "source_text": "손절은 없던 걸로"},
    ])
    state = sb.BuilderState(stop_loss_pct=10.0, risk_done=True)
    patch, _ = interpret_utterance("손절은 없던 걸로 하자", state, chat)
    assert patch["stop_loss_pct"] is None
    assert patch["risk_done"] is False


def test_reopen_universe_without_value():
    chat = _chat_returning([
        {"op": "reopen", "field": "universe", "source_text": "시장은 다시 정하고 싶어"},
    ])
    state = sb.BuilderState(universe="KOSDAQ")
    patch, _ = interpret_utterance("시장은 다시 정하고 싶어", state, chat)
    assert patch == {"universe": None}


def test_dropped_ops_reported_in_notes():
    chat = _chat_returning([
        {"op": "set", "field": "holding_count", "value": 7, "source_text": "7종목"},
        {"op": "set", "field": "unknown_field", "value": 1, "source_text": "7종목"},
    ])
    state = sb.BuilderState()
    patch, notes = interpret_utterance("7종목 정도로 굴려보자", state, chat)
    assert patch == {"holding_count": 7}
    assert notes and "반영하지 않았어요" in notes[0]


def test_malformed_llm_output_returns_none():
    state = sb.BuilderState()
    assert interpret_utterance("아무 말", state, lambda *a, **k: "json 아님") is None
    assert interpret_utterance("아무 말", state, lambda *a, **k: '{"ops": "?"}') is None


def test_step_routes_unrecognized_freetext_to_llm_lane():
    """결정적 레이어 전면 미인식 자유 서술 → LLM 레인 patch가 적용된다."""
    state = sb.BuilderState(strategy_type="momentum", universe="KOSPI",
                            lookback_days=63, lookback_label="3개월")
    called = {}

    def interpreter(text, st):
        called["text"] = text
        return {"holding_count": 7}, []

    result = sb.step(state, "일곱 종목쯤으로 널널하게 굴리자 7", freetext_interpreter=interpreter)
    assert called["text"].startswith("일곱 종목쯤")
    assert result.state.holding_count == 7
    assert result.state.miss_streak == 0


def test_step_deterministic_answer_skips_llm_lane():
    """값 답변("10개")은 결정적 형식 정규화가 즉답 — LLM 레인 미호출(경계 계약)."""
    state = sb.BuilderState(strategy_type="momentum", universe="KOSPI",
                            lookback_days=63, lookback_label="3개월")

    def interpreter(text, st):
        raise AssertionError("결정적으로 해석된 답변이 LLM 레인으로 가면 안 된다")

    result = sb.step(state, "10개", freetext_interpreter=interpreter)
    assert result.state.holding_count == 10


def test_step_llm_failure_keeps_unrecognized_flow():
    state = sb.BuilderState(strategy_type="momentum", universe="KOSPI",
                            lookback_days=63, lookback_label="3개월")

    def interpreter(text, st):
        raise RuntimeError("LLM down")

    result = sb.step(state, "뭔가 알 수 없는 말", freetext_interpreter=interpreter)
    # 기존 미인식 흐름 유지: 상태 불변 + miss_streak 증가
    assert result.state.holding_count is None
    assert result.state.miss_streak == 1


def test_freetext_mode_env_gate(monkeypatch):
    monkeypatch.delenv("BUILDER_FREETEXT_MODE", raising=False)
    assert freetext_llm_enabled()
    monkeypatch.setenv("BUILDER_FREETEXT_MODE", "deterministic")
    assert not freetext_llm_enabled()
