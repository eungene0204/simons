"""칩 답변 결정론 귀속(run_chip_answer, Phase 4 후속 ①) 계약 테스트.

핵심 계약:
- 입력이 직전 planner ask(pending_ask 에코)의 칩과 정확히 일치할 때만 발동한다 —
  자유 서술은 §4(답변 강제 귀속 금지)에 따라 인터프리터가 State 변경을 판정한다.
- 발동 시 수정 인터프리터 LLM을 호출하지 않고 결정적 추출로 State에 반영한다.
- 결정적으로 적용되지 않는 칩은 None으로 기존 경로 폴백(자기완결 계약 안전망).
- pending_ask는 사용자가 실제로 본 질문·칩과 항상 일치한다(finalize 동기화).
"""

from __future__ import annotations

import pytest

from engine.nl_parser import ParsedStrategy
from strategy_conversation import primary as primary_mod
from strategy_conversation.primary import (
    _pending_ask_payload,
    run_chip_answer,
)
from strategy_conversation.response.output_guard import finalize_user_response


def _etf_strategy() -> dict:
    return ParsedStrategy(
        description="반도체 etf 골든크로스 전략",
        universe=["ETF"],
        etf_theme="반도체",
        entry_signals=[{
            "indicator": "ma_crossover", "signal_type": "buy",
            "short_period": 5, "long_period": 20,
        }],
    ).model_dump()


def _pending_ask(chips, topic="리스크관리"):
    return {"topic": topic, "question": "손절·익절 기준을 정할까요?", "chips": chips}


@pytest.fixture(autouse=True)
def _no_interpreter(monkeypatch):
    """칩 레인은 인터프리터를 절대 호출하지 않는다 — 호출되면 즉시 실패."""
    def _fail(*args, **kwargs):
        raise AssertionError("칩 결정론 레인이 인터프리터를 호출했다")

    monkeypatch.setattr(primary_mod, "_get_interpreter", _fail)


def test_exact_chip_click_applies_without_llm():
    prev = _etf_strategy()
    result = run_chip_answer("손절 8%", prev, _pending_ask(["손절 8%", "익절 20%"]))
    assert result is not None
    assert result["parsed"].stop_loss_pct == 8.0
    assert result["interpreter"]["mode"] == "primary_chip_answer"
    assert result["interpreter"]["llm_latency_ms"] == 0
    # 기존 전략 필드는 유지된다(부분 병합 — 전체 초기화 금지)
    assert result["parsed"].universe == ["ETF"]
    assert result["parsed"].etf_theme == "반도체"
    assert len(result["parsed"].entry_signals) == 1


def test_chip_click_with_whitespace_still_matches():
    prev = _etf_strategy()
    result = run_chip_answer("  손절 8%  ", prev, _pending_ask(["손절 8%"]))
    assert result is not None and result["parsed"].stop_loss_pct == 8.0


def test_free_text_answer_falls_through_to_interpreter_path():
    """칩과 다른 자유 서술은 None — 강제 귀속하지 않는다(§4)."""
    prev = _etf_strategy()
    assert run_chip_answer(
        "손절은 10프로 정도로 하고 싶어", prev, _pending_ask(["손절 8%"])
    ) is None


def test_chip_without_deterministic_extraction_falls_through():
    """결정적 추출이 무변경인 칩(서술형)은 None — 인터프리터가 처리한다(안전망)."""
    prev = _etf_strategy()
    assert run_chip_answer(
        "직접 입력할게요", prev, _pending_ask(["직접 입력할게요"])
    ) is None


def test_missing_context_falls_through():
    prev = _etf_strategy()
    assert run_chip_answer("손절 8%", prev, None) is None
    assert run_chip_answer("손절 8%", None, _pending_ask(["손절 8%"])) is None
    assert run_chip_answer("손절 8%", prev, {"topic": "리스크관리"}) is None  # chips 없음


def test_technical_signal_chip_applies_deterministically():
    """자기완결 기술 지표 칩도 결정적 추출로 반영된다(정본 표기 파싱)."""
    prev = _etf_strategy()
    result = run_chip_answer(
        "데드크로스(5일/20일) 발생 시 매도", prev,
        _pending_ask(["데드크로스(5일/20일) 발생 시 매도"], topic="매도조건"),
    )
    assert result is not None
    assert any(s.get("indicator") == "ma_crossover"
               for s in result["parsed"].model_dump()["exit_signals"])


def test_replan_emits_next_pending_ask(monkeypatch):
    """칩 반영 후 남은 골격 공백이 있으면 planner 재계획 질문+다음 pending_ask를 낸다."""
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setattr(
        primary_mod, "_dag_planner_clarification",
        lambda user_input, parsed, explicit_fields=None: (
            "어떤 조건에서 매도할까요?", ["데드크로스(5일/20일) 발생 시 매도"], "매도조건",
        ),
    )
    prev = _etf_strategy()
    result = run_chip_answer("손절 8%", prev, _pending_ask(["손절 8%"]))
    assert result is not None
    assert result["clarification_question"] == "어떤 조건에서 매도할까요?"
    assert result["clarification_priority"] == "dag_planner"
    assert result["pending_ask"]["topic"] == "매도조건"
    assert result["pending_ask"]["question"] == "어떤 조건에서 매도할까요?"
    assert result["pending_ask"]["chips"] == ["데드크로스(5일/20일) 발생 시 매도"]
    # 칩=값 결속 계약 — 다음 턴의 클릭이 재해석 없이 쓸 값이 함께 실린다.
    binding = result["pending_ask"]["chip_bindings"]["데드크로스(5일/20일) 발생 시 매도"]
    assert binding["exit_signals"][0]["indicator"] == "ma_crossover"


def test_replan_off_mode_returns_no_question(monkeypatch):
    monkeypatch.delenv("STRATEGY_DAG_PLANNER_MODE", raising=False)
    prev = _etf_strategy()
    result = run_chip_answer("손절 8%", prev, _pending_ask(["손절 8%"]))
    assert result is not None
    assert result["clarification_question"] is None
    assert result["pending_ask"] is None


def test_pending_ask_payload_requires_question_and_chips():
    assert _pending_ask_payload(None, ["칩"], "매수조건") is None
    assert _pending_ask_payload("질문?", None, "매수조건") is None
    assert _pending_ask_payload("질문?", ["칩"], "매수조건") == {
        "topic": "매수조건", "question": "질문?", "chips": ["칩"],
    }


def test_finalize_syncs_pending_ask_with_guarded_question():
    """가드가 질문을 제거하면 pending_ask도 함께 지워진다 — 사용자가 본 것과 불일치 금지."""
    result = finalize_user_response({
        "parsed": None,
        "clarification_question": None,
        "clarification_suggestions": ["손절 8%"],
        "pending_ask": {"topic": "리스크관리", "question": "x", "chips": ["손절 8%"]},
        "notices": [],
    })
    assert result["pending_ask"] is None

    result = finalize_user_response({
        "parsed": None,
        "clarification_question": "손절 기준을 정할까요?",
        "clarification_suggestions": ["손절 8%"],
        "pending_ask": {"topic": "리스크관리", "question": "손절 기준을 정할까요?",
                        "chips": ["손절 8%"]},
        "notices": [],
    })
    assert result["pending_ask"] == {
        "topic": "리스크관리", "question": "손절 기준을 정할까요?", "chips": ["손절 8%"],
    }


def test_cache_key_varies_with_pending_ask():
    """같은 프롬프트라도 pending_ask 컨텍스트가 다르면 캐시 키가 달라야 한다."""
    from nl_cache import nl_cache_key

    prev = _etf_strategy()
    base = nl_cache_key("손절 8%", "ollama", None, prev)
    with_ask = nl_cache_key("손절 8%", "ollama", None, prev,
                            _pending_ask(["손절 8%"]))
    assert base != with_ask


# ─── 칩=값 결속 계약(2026-07-29 '거래량 급감' 사고) ──────────────────────────────
# 칩은 우리 agent가 만들어 보여준 열거형 선택지다 — 값은 보여주는 순간 이미 알고
# 있어야 하고, 클릭은 그 값을 꺼내 쓰는 행위여야 한다. 값이 결속되지 않는 칩은
# 엔진이 표현할 수 없는 조건이므로 애초에 노출되지 않는다.


def test_unbindable_chip_is_not_emitted():
    """엔진이 표현할 수 없는 칩(거래량 급감)은 발행 단계에서 탈락한다."""
    prev = ParsedStrategy.model_validate(_etf_strategy())
    payload = _pending_ask_payload(
        "언제 팔까요?",
        ["데드크로스(5일/20일) 발생 시 매도", "거래량 급감(전일 대비 1/2 이하) 시 매도"],
        "매도 조건",
        prev,
    )
    assert payload is not None
    assert payload["chips"] == ["데드크로스(5일/20일) 발생 시 매도"]
    assert "거래량 급감(전일 대비 1/2 이하) 시 매도" not in payload["chip_bindings"]


def test_all_chips_unbindable_drops_the_chip_list():
    """전부 결속 실패면 pending_ask 자체를 내지 않는다(질문만 남고 자유 서술로)."""
    prev = ParsedStrategy.model_validate(_etf_strategy())
    assert _pending_ask_payload(
        "언제 팔까요?", ["거래량 급감(전일 대비 1/2 이하) 시 매도"], "매도 조건", prev,
    ) is None


def test_description_only_change_is_not_an_applied_chip():
    """description만 달라진 칩은 '반영'이 아니다 — 무변경을 확정으로 오보고하지 않는다."""
    prev = _etf_strategy()
    ask = _pending_ask(["거래량 급감(전일 대비 1/2 이하) 시 매도"], topic="매도 조건")
    assert run_chip_answer("거래량 급감(전일 대비 1/2 이하) 시 매도", prev, ask) is None


def test_click_applies_stored_binding_without_reinterpreting_the_label():
    """클릭은 발행 때 결속한 값을 그대로 쓴다 — 칩 문구 재추출을 거치지 않는다."""
    prev = _etf_strategy()
    ask = {
        "topic": "매도 조건", "question": "언제 팔까요?",
        "chips": ["데드크로스(5일/20일) 발생 시 매도"],
        "chip_bindings": {
            "데드크로스(5일/20일) 발생 시 매도": {
                "exit_signals": [{
                    "indicator": "ma_crossover", "signal_type": "sell",
                    "short_period": 5, "long_period": 20,
                }],
            },
        },
    }

    def _fail(*args, **kwargs):
        raise AssertionError("결속된 칩이 문구 재추출을 호출했다")

    import engine.nl_parser as nl_parser_mod
    original = nl_parser_mod._apply_prompt_overrides
    nl_parser_mod._apply_prompt_overrides = _fail
    try:
        result = run_chip_answer("데드크로스(5일/20일) 발생 시 매도", prev, ask)
    finally:
        nl_parser_mod._apply_prompt_overrides = original
    assert result is not None
    assert result["parsed"].exit_signals[0].indicator == "ma_crossover"
    assert result["parsed"].exit_signals[0].long_period == 20
