"""Query Intent 분류기 테스트 — 스펙 예시 + 결정적 규칙 + LLM 폴백."""

from __future__ import annotations

import pytest

from intent.classifier import classify
from intent.schemas import QueryIntent


@pytest.mark.parametrize(
    "query, expected",
    [
        ("RSI 30 이하에서 매수하는 전략 어때?", QueryIntent.STRATEGY_ADVICE),
        ("지금 삼성전자 사도 될까요?", QueryIntent.STOCK_ANALYSIS),
        ("PER이 뭐야?", QueryIntent.GENERAL_INVESTMENT),
        ("SK하이닉스 전망 어때?", QueryIntent.STOCK_ANALYSIS),
        ("엔비디아 지금 들어가도 돼?", QueryIntent.STOCK_ANALYSIS),
        ("카카오 계속 들고 있어도 될까?", QueryIntent.STOCK_ANALYSIS),
    ],
)
def test_spec_examples(query, expected):
    assert classify(query).intent == expected


@pytest.mark.parametrize(
    "query",
    [
        "PBR 1 이하, PER 10 이하 저평가 종목",  # 실제 버그 재현 케이스
        "저평가 종목",
        "고배당주 추천해줘",
        "ROE 15 이상 우량주",
        "거래량 100만 이상 종목",
        "시총 1조 이상인 종목",
    ],
)
def test_fundamental_screening_is_strategy(query):
    # 특정 종목명 없는 '조건/필터로 종목 고르기'는 전략 설계(스크리닝)다.
    # 종목 분석(STOCK_ANALYSIS)으로 빠지면 "어떤 종목?" 막다른 길이 된다.
    result = classify(query)  # llm 없이도 결정적으로 잡혀야 한다
    assert result.intent == QueryIntent.STRATEGY_ADVICE
    assert result.deterministic is True


@pytest.mark.parametrize(
    "query",
    [
        "어떤 주식을 사야 할까요?",
        "어떤 종목을 사야 하나요?",
        "추천 종목이 있나요?",
        "지금 살 만한 종목이 있나요?",
        "뭐를 사면 좋을까요?",
        "AI 관련주 추천해 주세요.",
        "수익이 잘 날 종목이 있나요?",
    ],
)
def test_open_stock_pick_is_redirected(query):
    # [규제 안전] 특정 종목명·조건 없이 '무엇을 사야 하나'라는 열린 추천 요청은
    # 추천하지 않고 전략 설계로 전환하는 안내(STOCK_PICK + suggested_reply)로 잡혀야 한다.
    result = classify(query)  # llm 없이도 결정적으로
    assert result.intent == QueryIntent.STOCK_PICK
    assert result.deterministic is True
    assert result.suggested_reply
    assert "전략" in result.suggested_reply


def test_named_stock_is_not_pick_redirect():
    # 종목명이 특정된 매수 질문은 추천 거절이 아니라 종목 분석으로 가야 한다.
    result = classify("삼성전자 사야 할까요?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS


def test_screening_basket_recommend_is_strategy():
    # '고배당주 추천'은 열린 추천이 아니라 스크리닝 전략 설계로 분류돼야 한다.
    assert classify("고배당주 추천해줘").intent == QueryIntent.STRATEGY_ADVICE


def test_stock_question_extracts_symbol():
    result = classify("지금 삼성전자 사도 될까요?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert any(s.symbol == "005930" for s in result.symbols)


def test_strategy_keyword_beats_stock_name():
    # 종목명이 섞여 있어도 '전략/백테스트'가 있으면 전략 설계로 분류.
    result = classify("삼성전자로 백테스트하는 전략 만들어줘")
    assert result.intent == QueryIntent.STRATEGY_ADVICE


def test_anaphora_uses_last_symbol():
    result = classify("이 종목 팔아야 할까?", last_symbol="005930")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert any(s.symbol == "005930" for s in result.symbols)


def test_overseas_alias_detected_but_marked_overseas():
    result = classify("엔비디아 지금 들어가도 돼?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert any(s.overseas for s in result.symbols)


def test_definition_question_is_general():
    assert classify("골든크로스가 무엇인가요?").intent == QueryIntent.GENERAL_INVESTMENT


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


def test_substring_match_bug_sk_hynix_not_confused_with_inix():
    # 이닉스(452400)은 SK하이닉스(000660)에 substring으로 포함되지만,
    # 단어 경계를 고려해 정확히 구분해야 한다.
    result = classify("SK하이닉스 사도 될까?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert any(s.symbol == "000660" for s in result.symbols), \
        f"SK하이닉스 코드는 000660이어야 하는데, 찾은 symbol: {[s.symbol for s in result.symbols]}"
    assert not any(s.symbol == "452400" for s in result.symbols), \
        "이닉스(452400)이 잘못 매칭되면 안 된다"


@pytest.mark.parametrize(
    "query",
    ["안녕", "안녕하세요", "좋은 아침", "하이!", "ㅎㅇ"],
)
def test_greeting_is_detected(query):
    result = classify(query)
    assert result.intent == QueryIntent.GREETING
    assert result.deterministic is True
    assert result.suggested_reply  # 곧바로 보여줄 인사 문구가 채워진다


def test_greeting_with_strategy_question_is_strategy():
    # 인사 + 전략 질문이 섞이면 인사로 가로채지 않고 전략 설계로 분류한다.
    result = classify("안녕하세요 RSI 30 이하 매수 전략 어때요?")
    assert result.intent == QueryIntent.STRATEGY_ADVICE


@pytest.mark.parametrize(
    "query",
    ["오늘 날씨 어때?", "파이썬 코드를 작성해줘.", "대통령이 누구야?", "감기에 좋은 약 알려줘"],
)
def test_offtopic_is_refused(query):
    result = classify(query)
    assert result.intent == QueryIntent.OFF_TOPIC
    assert result.deterministic is True
    assert "투자 전략 및 투자 분석 전용" in (result.suggested_reply or "")


def test_offtopic_with_finance_cue_is_not_refused():
    # 금융 신호가 있으면 역할 밖으로 보지 않는다(오탐 방지).
    result = classify("이 전략은 변동성이 날씨처럼 들쭉날쭉해요")
    assert result.intent != QueryIntent.OFF_TOPIC


def test_llm_fallback_offtopic_sets_refusal_reply():
    # 결정적 cue로 못 잡는 잡담('없어 그냥 너랑 놀려고')은 LLM이 OFF_TOPIC으로 잡고
    # 곧바로 보여줄 거절 문구가 채워진다 — 전략 생성으로 새지 않는다.
    result = classify("없어 그냥 너랑 놀려고", llm=lambda s, u: '{"intent": "OFF_TOPIC"}')
    assert result.intent == QueryIntent.OFF_TOPIC
    assert "투자 전략 및 투자 분석 전용" in (result.suggested_reply or "")


def test_llm_fallback_greeting_sets_reply():
    result = classify("어이~ 반가워이", llm=lambda s, u: '{"intent": "GREETING"}')
    assert result.intent == QueryIntent.GREETING
    assert result.suggested_reply


def test_definition_without_finance_cue_is_not_general_investment():
    # 투자 맥락 없는 '뭐야'('너 이름이 뭐야')는 결정적으로 GENERAL_INVESTMENT가 되지 않고
    # LLM 폴백으로 넘어가 OFF_TOPIC으로 분류된다.
    result = classify("너 이름이 뭐야", llm=lambda s, u: '{"intent": "OFF_TOPIC"}')
    assert result.intent == QueryIntent.OFF_TOPIC


@pytest.mark.parametrize(
    "query",
    [
        "어떻게 시작하지?",
        "뭐부터 해야 해?",
        "처음인데 어떻게 써요?",
        "어디서부터 시작해야 할지 모르겠어요",
        "사용법 알려줘",
        "초보인데 도와주세요",
    ],
)
def test_onboarding_help_is_routed_to_builder(query):
    # [온보딩] 무엇을 해야 할지 막막한 도움 요청은 거절하거나 빈 전략 카드를 띄우지 않고
    # 전략 빌더로 유도한다(ONBOARDING + suggested_reply). LLM 없이 결정적으로 잡혀야 한다.
    result = classify(query)
    assert result.intent == QueryIntent.ONBOARDING
    assert result.deterministic is True
    assert result.suggested_reply


def test_onboarding_with_finance_cue_is_not_onboarding():
    # 구체적인 지표가 섞인 '어떻게' 질문은 막연한 요청이 아니므로 ONBOARDING으로 잡지 않는다
    # (기존 전략/코칭 흐름이 더 잘 처리한다).
    result = classify("RSI 어떻게 설정해?")
    assert result.intent != QueryIntent.ONBOARDING


def test_onboarding_does_not_steal_strategy_question():
    # '전략 어떻게 만들어?'처럼 전략 키워드가 있으면 전략 설계로 분류된다(온보딩보다 우선).
    result = classify("골든크로스 전략 어떻게 만들어?")
    assert result.intent == QueryIntent.STRATEGY_ADVICE


def test_llm_fallback_onboarding_sets_reply():
    # 결정적 cue로 못 잡는 막막한 입력도 LLM이 ONBOARDING으로 잡으면 안내 문구가 채워진다.
    result = classify("나 이런 거 잘 못하는데", llm=lambda s, u: '{"intent": "ONBOARDING"}')
    assert result.intent == QueryIntent.ONBOARDING
    assert result.suggested_reply
