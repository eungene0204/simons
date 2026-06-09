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
