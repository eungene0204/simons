"""의도 분류 계약 레인 — 원문 → LLM → 구조화 출력 → 형식 정규화 → 도메인 정책.

검증 대상은 '정규식이 원문을 해석하지 않는다'는 계약과, LLM 라벨이 정해진 정책
응답으로 이어지는지다. 의미 판정 자체(어떤 문장이 어떤 라벨인가)는 LLM 소관이라
여기서 단정하지 않는다 — 그건 QA 하니스(scripts/qa_*)의 영역이다.
"""

from __future__ import annotations

import json

import pytest

from intent import interpreter
from intent.classifier import classify
from intent.schemas import ChatTurn, QueryIntent


def stub_llm(intent: str, **extra):
    """구조화 출력을 그대로 돌려주는 LLM 스텁."""
    payload = json.dumps({"intent": intent, **extra}, ensure_ascii=False)
    return lambda system, user: payload


def capturing_llm(intent: str = "STRATEGY_ADVICE"):
    """LLM에 실제로 전달된 user 메시지를 잡아두는 스텁."""
    seen: dict[str, str] = {}

    def _llm(system, user):
        seen["system"] = system
        seen["user"] = user
        return json.dumps({"intent": intent})

    return _llm, seen


# ── 형식 정규화(입력이 LLM 출력) ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw",
    [
        '{"intent": "OFF_TOPIC"}',
        '```json\n{"intent": "OFF_TOPIC"}\n```',
        '<think>음 이건 잡담인가</think>{"intent":"OFF_TOPIC"}',
        '설명을 붙이면 {"intent": "OFF_TOPIC"} 입니다',
    ],
)
def test_json_boundary_extraction_handles_wrappers(raw):
    assert interpreter.extract_json_object(raw) == {"intent": "OFF_TOPIC"}


def test_json_extraction_returns_none_instead_of_guessing():
    """JSON이 없으면 임의 보정하지 않고 실패로 끝난다(계약: 후처리 보정 금지)."""
    assert interpreter.extract_json_object("잘 모르겠어요") is None
    assert interpreter.extract_json_object("") is None


@pytest.mark.parametrize(
    "value, expected",
    [
        ("OFF_TOPIC", "OFF_TOPIC"),
        ("off_topic", "OFF_TOPIC"),
        ("off-topic", "OFF_TOPIC"),
        ("  Off Topic  ", "OFF_TOPIC"),
        ("STRATEGY_ADVICE", "STRATEGY_ADVICE"),
    ],
)
def test_label_normalization(value, expected):
    assert interpreter.normalize_intent_label(value) == expected


@pytest.mark.parametrize("value", ["NOT_A_LABEL", "", None, 42, {"a": 1}])
def test_unknown_label_is_rejected(value):
    assert interpreter.normalize_intent_label(value) is None


@pytest.mark.parametrize("value", ["null", "none", "없음", "", "  ", None, 7])
def test_empty_stock_name_variants_become_none(value):
    interp = interpreter.interpret("아무 말", stub_llm("STRATEGY_ADVICE", stock_name=value))
    assert interp is not None and interp.stock_name is None


# ── 실패 보고(정규식 재해석 폴백 없음) ────────────────────────────────────────

def test_malformed_output_reports_failure_without_regex_reinterpretation():
    result = classify("원자력 업종만 테스트 하고 싶어", llm=lambda s, u: "음... 글쎄요")
    assert result.intent == QueryIntent.UNKNOWN
    assert result.suggested_reply is None
    assert "해석 실패" in result.reason


def test_unavailable_llm_reports_failure_and_does_not_refuse():
    """LLM이 없으면 UNKNOWN 실패 보고 — 정규식으로 판정해 거절 문구를 내지 않는다."""
    result = classify("원자력 업종만 테스트 하고 싶어", llm=None)
    assert result.intent == QueryIntent.UNKNOWN
    assert result.suggested_reply is None


def test_llm_connection_error_propagates():
    """연결 장애는 None으로 위장하지 않고 그대로 올린다(503 경로가 처리)."""
    def boom(system, user):
        raise ConnectionError("modal down")

    with pytest.raises(ConnectionError):
        classify("아무 말", llm=boom)


# ── 도메인 정책(라벨 → 정형 응답) ────────────────────────────────────────────

@pytest.mark.parametrize(
    "label, marker",
    [
        ("OFF_TOPIC", "투자 전략 및 투자 분석 전용 모델"),
        ("STRATEGY_PICK", "어떤 전략이 더 좋은지 판단하거나 추천해"),
        ("PERSONAL_ADVICE", "개인 상황에 맞춘 전략이나 종목 추천은 제공하지 않아요"),
        ("LIVE_TRADING", "실제 계좌로 매매를 실행하거나"),
        ("UNSUPPORTED_FEATURE", "재료 분석 기능은 현재 제공하고 있지 않아요"),
        ("ONBOARDING", "단계별로 함께 전략을 만들어"),
    ],
)
def test_label_maps_to_policy_reply(label, marker):
    """[규제 안전] 안내 문구는 LLM이 짓지 않고 라벨에서 결정적으로 나온다."""
    result = classify("아무 말", llm=stub_llm(label))
    assert result.intent == QueryIntent(label)
    assert marker in (result.suggested_reply or "")


def test_strategy_advice_carries_no_canned_reply():
    """전략 요청은 정형 응답으로 끝내지 않고 파싱(인터프리터)으로 흘려보낸다."""
    result = classify("원자력 업종만 테스트 하고 싶어", llm=stub_llm("STRATEGY_ADVICE"))
    assert result.intent == QueryIntent.STRATEGY_ADVICE
    assert result.suggested_reply is None


# ── 종목 정본 매핑(원문 스캔이 아니라 LLM 추출 문자열 → registry) ──────────────

def test_stock_name_from_llm_is_resolved_through_registry():
    result = classify(
        "그거 지금 사도 될까?", llm=stub_llm("STOCK_ANALYSIS", stock_name="삼성전자")
    )
    assert [s.symbol for s in result.symbols] == ["005930"]
    assert "삼성전자" in (result.suggested_reply or "")


def test_stock_not_named_by_llm_is_not_scanned_from_raw_text():
    """원문에 종목명이 있어도 LLM이 뽑지 않았으면 registry를 태우지 않는다 —
    원문 스캔(find_in_text(user_input)) 부활 방지."""
    result = classify("삼성전자 지금 사도 될까?", llm=stub_llm("STOCK_ANALYSIS"))
    assert result.symbols == []


def test_anaphora_resolves_from_last_symbol_when_llm_flags_it():
    result = classify(
        "이 종목 팔까?",
        last_symbol="005930",
        llm=stub_llm("STOCK_ANALYSIS", refers_to_last_stock=True),
    )
    assert [s.symbol for s in result.symbols] == ["005930"]


# ── LLM에 전달되는 맥락 ──────────────────────────────────────────────────────

def test_active_strategy_context_is_sent_to_llm():
    """진행 중인 전략 여부가 LLM 입력에 들어가야 짧은 수정 발화를 잡담으로 오판하지 않는다."""
    llm, seen = capturing_llm()
    classify("원자력 업종만 테스트 하고 싶어", llm=llm, active_strategy=True)
    assert "[진행 중인 전략] 있음" in seen["user"]


def test_history_is_sent_to_llm():
    llm, seen = capturing_llm()
    classify(
        "그럼 원자력만",
        llm=llm,
        history=[ChatTurn(role="user", text="원자력 관련주로 모멘텀 전략 만들어줘")],
    )
    assert "원자력 관련주로 모멘텀 전략" in seen["user"]
    assert "[최신 입력]" in seen["user"]


def test_prompt_does_not_receive_regex_derived_hints():
    """프롬프트에는 원문과 맥락만 들어간다 — 정규식이 미리 뽑은 신호를 주입하지 않는다."""
    llm, seen = capturing_llm()
    classify("PBR 1 이하 저평가 종목", llm=llm)
    assert "PBR 1 이하 저평가 종목" in seen["user"]
    for leaked in ("screening=", "finance_cue=", "strategy_kw="):
        assert leaked not in seen["user"]
