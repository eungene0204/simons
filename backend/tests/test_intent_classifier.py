"""Query Intent 분류기 — [레거시 레인] 원문 정규식 규칙 + LLM 폴백 회귀.

이 파일이 검증하는 `_classify_deterministic`/`_classify_with_llm`은 원문을 패턴 매칭해
의도를 판정하는 계약 위반 레인이며, 현재 기본 경로가 아니다(INTENT_CLASSIFIER_MODE=legacy
롤백 전용). 롤백해도 동작이 보장되도록 커버리지를 유지한다.

계약 레인(기본)의 테스트는 tests/test_intent_interpreter.py에 있다.
새 판정 규칙은 이 파일이 아니라 그쪽에 추가한다.
"""

from __future__ import annotations

import pytest

from intent.classifier import classify, format_history_context, _correct_count_typo
from intent.schemas import ChatTurn, QueryIntent


@pytest.fixture(autouse=True)
def _legacy_lane(monkeypatch):
    monkeypatch.setenv("INTENT_CLASSIFIER_MODE", "legacy")


@pytest.mark.parametrize(
    "raw,corrected",
    [
        ("종목은 5게", "종목은 5개"),
        ("종목은 120게", "종목은 120개"),
        ("5게 이상", "5개 이상"),
        ("120게임 만들기", "120게임 만들기"),  # 게로 시작하는 단어는 보존
    ],
)
def test_correct_count_typo_ge_to_gae(raw, corrected):
    # [회귀] 숫자 뒤 '게'(개 오타)를 분류 전에 보정해 OFF_TOPIC 오분류를 막는다.
    assert _correct_count_typo(raw) == corrected


def test_classifier_prompt_has_typo_tolerance_guidance():
    # [회귀] 결정적 정규화가 못 잡는 미지의 오타도 LLM이 의미로 분류하도록 프롬프트가 안내해야 한다.
    from intent.classifier import _CLASSIFIER_SYSTEM_PROMPT
    assert "오타" in _CLASSIFIER_SYSTEM_PROMPT
    assert "OFF_TOPIC이 아니다" in _CLASSIFIER_SYSTEM_PROMPT


def test_stock_question_redirect_tailors_universe_by_market():
    # 예시 전략의 유니버스는 언급 종목의 시장에 맞춘다(KOSPI→코스피200 대형주, KOSDAQ→코스닥).
    from intent.scope import stock_question_redirect
    kospi = stock_question_redirect("삼성전자", "KOSPI")
    assert "코스피200" in kospi
    kosdaq = stock_question_redirect("에코프로", "KOSDAQ")
    assert "코스닥" in kosdaq
    generic = stock_question_redirect()
    assert "추천은 제공하지 않아요" in generic


def test_stock_question_redirect_has_no_action_directives():
    # 안내 문구 자체가 매수·매도 지시/추천 표현을 담으면 안 된다(유사투자자문 회피).
    from stock_analysis.guardrails import contains_forbidden
    from intent.scope import stock_question_redirect
    assert contains_forbidden(stock_question_redirect("삼성전자", "KOSPI")) is False


def test_llm_fallback_stock_analysis_sets_redirect_reply():
    # LLM 폴백으로 STOCK_ANALYSIS가 분류돼도 전환 안내가 채워져야 한다(프론트가 그대로 표시).
    result = classify("삼성전자 물타기 괜찮은 생각일까요 흠", llm=lambda s, u: '{"intent": "STOCK_ANALYSIS"}')
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert "추천은 제공하지 않아요" in (result.suggested_reply or "")


def test_virtual_account_is_in_scope_not_offtopic():
    # [회귀] '가상계좌/모의투자'는 이 플랫폼의 핵심 기능이므로 역할 밖(OFF_TOPIC) 신호가 아니다.
    from intent.scope import is_offtopic, has_finance_cue
    assert has_finance_cue("가상계좌 만들어줘") is True
    assert is_offtopic("가상계좌 만들어줘") is False
    assert is_offtopic("모의투자 하고 싶어요") is False
    # '가상현실 게임'처럼 '가상'만 들어간 잡담은 여전히 역할 밖으로 걸러야 한다.
    assert is_offtopic("가상현실 게임 추천해줘") is True


def test_ambiguous_without_llm_is_unknown():
    # 종목명·전략 키워드·정의형·행동 동사가 모두 없는 입력 → 결정 불가 → UNKNOWN.
    result = classify("음 글쎄요 그냥 궁금해서요")
    assert result.intent == QueryIntent.UNKNOWN
    assert result.deterministic is False


def test_llm_fallback_used_when_deterministic_fails():
    captured = {}

    def fake_llm(system, user):
        captured["called"] = True
        return '{"intent": "GENERAL_INVESTMENT"}'

    result = classify("요즘 시장 분위기 어떤 느낌이에요", llm=fake_llm)
    assert captured.get("called") is True
    assert result.intent == QueryIntent.GENERAL_INVESTMENT
    assert result.deterministic is False


def test_offtopic_with_finance_cue_is_not_refused():
    # 금융 신호가 있으면 역할 밖으로 보지 않는다(오탐 방지).
    result = classify("이 전략은 변동성이 날씨처럼 들쭉날쭉해요")
    assert result.intent != QueryIntent.OFF_TOPIC


def test_llm_fallback_offtopic_sets_refusal_reply():
    # 결정적 cue로 못 잡는 잡담('없어 그냥 너랑 놀려고')은 LLM이 OFF_TOPIC으로 잡고
    # 곧바로 보여줄 거절 문구가 채워진다 — 전략 생성으로 새지 않는다.
    result = classify("없어 그냥 너랑 놀려고", llm=lambda s, u: '{"intent": "OFF_TOPIC"}')
    assert result.intent == QueryIntent.OFF_TOPIC
    assert "현재 질문에는 도움을 드릴 수 없어요" in (result.suggested_reply or "")


def test_llm_fallback_greeting_sets_reply():
    result = classify("어이~ 반가워이", llm=lambda s, u: '{"intent": "GREETING"}')
    assert result.intent == QueryIntent.GREETING
    assert result.suggested_reply


def test_definition_without_finance_cue_is_not_general_investment():
    # 투자 맥락 없는 '뭐야'('너 이름이 뭐야')는 결정적으로 GENERAL_INVESTMENT가 되지 않고
    # LLM 폴백으로 넘어가 OFF_TOPIC으로 분류된다.
    result = classify("너 이름이 뭐야", llm=lambda s, u: '{"intent": "OFF_TOPIC"}')
    assert result.intent == QueryIntent.OFF_TOPIC


def test_onboarding_with_finance_cue_is_not_onboarding():
    # 구체적인 지표가 섞인 '어떻게' 질문은 막연한 요청이 아니므로 ONBOARDING으로 잡지 않는다
    # (기존 전략/코칭 흐름이 더 잘 처리한다).
    result = classify("RSI 어떻게 설정해?")
    assert result.intent != QueryIntent.ONBOARDING


def test_llm_fallback_onboarding_sets_reply():
    # 결정적 cue로 못 잡는 막막한 입력도 LLM이 ONBOARDING으로 잡으면 안내 문구가 채워진다.
    result = classify("나 이런 거 잘 못하는데", llm=lambda s, u: '{"intent": "ONBOARDING"}')
    assert result.intent == QueryIntent.ONBOARDING
    assert result.suggested_reply


def test_llm_fallback_strategy_pick_sets_reply():
    # 결정적 cue로 못 잡는 애매한 전략 추천 요청도 LLM이 STRATEGY_PICK으로 잡으면 안내가 채워진다.
    result = classify("나한테 맞는 게 뭘까", llm=lambda s, u: '{"intent": "STRATEGY_PICK"}')
    assert result.intent == QueryIntent.STRATEGY_PICK
    assert result.suggested_reply


def test_news_definition_question_is_not_declined():
    # 순수 정의형 질문("공시가 뭐야?")은 미제공 안내로 가로채지 않는다(지식 질문).
    result = classify("공시가 뭐야?")
    assert result.intent != QueryIntent.UNSUPPORTED_FEATURE


def test_llm_fallback_unsupported_feature_sets_reply():
    # 결정적 cue로 못 잡는 긴 꼬리 phrasing도 LLM이 UNSUPPORTED_FEATURE로 잡으면 안내가 채워진다.
    result = classify(
        "요즘 화제성 높은 걸로 부탁해", llm=lambda s, u: '{"intent": "UNSUPPORTED_FEATURE"}'
    )
    assert result.intent == QueryIntent.UNSUPPORTED_FEATURE
    assert result.suggested_reply
    assert "전략 생성·검증·백테스트 전문 도구" in result.suggested_reply


# ─── 대화 맥락(history) 기반 후속 질문 분류 ──────────────────────────────────────
# 실제 사고 재현: 직전 답변이 전략 예시를 보여준 뒤 "다른 예는 없어?"라고 물으면,
# 문장만 보면 투자 신호가 없어 LLM 폴백이 OFF_TOPIC으로 오판 → 거절 문구가 나갔다.
# 최근 대화 턴을 LLM 폴백에 함께 넘겨 직전 주제의 연속으로 분류하게 한다.

_EXAMPLES_SHOWN_HISTORY = [
    ChatTurn(role="user", text="삼성전자 지금 사도 될까?"),
    ChatTurn(
        role="assistant",
        text="삼성전자에 대한 매수·매도 판단이나 종목 추천은 제공하지 않아요. "
        "예를 들어 이렇게 시작해볼 수 있어요: RSI 과매도 반등 전략, 골든크로스 추세 전략",
    ),
]


def test_format_history_context_truncates_and_caps_turns():
    long_text = "가" * 500
    history = [ChatTurn(role="assistant", text=long_text)] + [
        ChatTurn(role="user", text=f"turn-{i}") for i in range(10)
    ]
    context = format_history_context(history)
    # 최근 6턴만 남는다 → 긴 첫 턴은 잘려 나간다.
    assert "가" not in context
    assert "turn-9" in context and "turn-4" in context
    assert "turn-3" not in context
    # 개별 턴 텍스트는 240자로 잘린다.
    truncated = format_history_context([ChatTurn(role="assistant", text=long_text)])
    assert len(truncated) < 260
    assert truncated.endswith("…")


def test_format_history_context_empty_and_blank_turns():
    assert format_history_context(None) == ""
    assert format_history_context([]) == ""
    assert format_history_context([ChatTurn(role="user", text="   ")]) == ""


def test_general_query_user_msg_includes_history():
    from api.intent_routes import GeneralQueryRequest, _build_general_user_msg

    req = GeneralQueryRequest(query="다른 예는 없어?", history=_EXAMPLES_SHOWN_HISTORY)
    msg = _build_general_user_msg(req)
    assert "[대화 맥락]" in msg
    assert "[질문]\n다른 예는 없어?" in msg
    # 맥락이 없으면 질문만 그대로.
    assert _build_general_user_msg(GeneralQueryRequest(query="PER이 뭐야?")) == "PER이 뭐야?"
