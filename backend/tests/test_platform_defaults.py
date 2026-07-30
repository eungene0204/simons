"""백테스트 설정 기본값 질문 — 결정적 답변 테스트.

전략 분석실에서 "슬리피지는 몇 %가 기본 값이지?"에 LLM이 "0%"라고 지어낸 사고 재현.
실제 코드 기본값(ParsedStrategy default·시뮬레이터 상수)으로 정확히 답해야 한다.
"""

from __future__ import annotations

import pytest

from intent import platform_defaults
from intent.classifier import classify
from intent.schemas import QueryIntent


# ─── 감지 ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "query",
    [
        "슬리피지는 몇 %가 기본 값이지?",  # 사고 재현 케이스
        "현재 셋팅된 슬리피지 값은?",       # 사고 재현 케이스
        "수수료 기본값 알려줘",
        "거래세는 얼마야?",
        "초기자금은 얼마로 설정돼 있어?",
        "백테스트 기본 설정값이 뭐야?",
        "체결 시점은 기본으로 언제야?",
        # 직전 기본값 답변에 이어지는 설정 용어 단독 후속 질문(2026-07-20 실측 "수수료는?")
        "수수료는?",
        "그럼 거래세는?",
        "초기자금은?",
    ],
)
def test_default_question_detected(query):
    assert platform_defaults.is_default_question(query)


@pytest.mark.parametrize(
    "query",
    [
        "슬리피지를 0.1%로 설정해줘",       # 값 변경 명령 — 수정 경로
        "수수료를 0.2%로 바꿔줘",
        "슬리피지가 뭐야?",                 # 개념 질문 — LLM 설명(사실 주입)
        "수수료는 왜 내야 해?",             # 개념 질문 — 단독 용어가 아님
        "RSI 30 이하 매수 전략 만들어줘",
        "얼마나 벌 수 있어?",
    ],
)
def test_non_default_question_not_detected(query):
    assert not platform_defaults.is_default_question(query)


# ─── 답변 값 정확성 — SOT(코드 기본값)와 일치 ────────────────────────────────

def test_reply_slippage_value():
    answer = platform_defaults.reply("슬리피지는 몇 %가 기본 값이지?")
    assert "0.05%" in answer
    assert "0%입니다" not in answer


def test_reply_fee_includes_sell_tax():
    answer = platform_defaults.reply("수수료 기본값은?")
    assert "0.015%" in answer
    assert "0.15%" in answer  # 매도 시 증권거래세 동반 안내
    assert "ETF" in answer


def test_reply_initial_capital():
    answer = platform_defaults.reply("초기자금 얼마로 설정돼?")
    assert "1,000만원" in answer
    assert "100만원" in answer  # 최소 하한선


def test_reply_generic_lists_all():
    answer = platform_defaults.reply("백테스트 기본 설정값 알려줘")
    for expected in ("1,000만원", "0.015%", "0.15%", "0.05%", "시가"):
        assert expected in answer


def test_reply_none_for_non_default_question():
    assert platform_defaults.reply("모멘텀 전략 만들어줘") is None


# ─── 분류 라우팅 — [레거시 레인] LLM 없이 결정적으로 GENERAL_INVESTMENT ──────
# 계약 레인에서는 분류기가 원문을 읽지 않는다. 설정 기본값 질문은 LLM이
# GENERAL_INVESTMENT로 분류하고, 실제 값 답변은 /query/general이
# platform_defaults.reply로 결정적으로 낸다
# (test_generate_general_answer_deterministic_without_llm 이 그 경로를 보증).

@pytest.mark.parametrize(
    "query",
    [
        "슬리피지는 몇 %가 기본 값이지?",
        "현재 셋팅된 슬리피지 값은?",
        "백테스트 수수료 기본값은?",  # '백테스트' 전략 키워드가 섞여도 설정 질문 우선
    ],
)
def test_classify_routes_to_general_with_reply(query, monkeypatch):
    monkeypatch.setenv("INTENT_CLASSIFIER_MODE", "legacy")
    result = classify(query)
    assert result.intent == QueryIntent.GENERAL_INVESTMENT
    assert result.suggested_reply and "0.0" in result.suggested_reply


def test_classify_set_command_stays_strategy():
    # 값 변경 명령은 기본값 답변으로 가로채지 않는다.
    result = classify("슬리피지를 0.1%로 설정해줘")
    assert result.intent != QueryIntent.GENERAL_INVESTMENT


# ─── /query/general 결정적 경로 — LLM 미가용이어도 정확한 답 ─────────────────

def test_generate_general_answer_deterministic_without_llm():
    from api.intent_routes import generate_general_answer

    answer = generate_general_answer("현재 셋팅된 슬리피지 값은?")
    assert answer is not None and "0.05%" in answer


def test_facts_block_for_concept_question():
    block = platform_defaults.facts_block("슬리피지가 뭐야?")
    assert block is not None and "0.05%" in block
    # 존재하지 않는 UI('설정 패널') 언급 금지 지시가 주입된다.
    assert "설정 패널" in block and "언급하지" in block
    assert platform_defaults.facts_block("PBR이 뭐야?") is None


def test_reply_does_not_mention_settings_panel():
    # 실사용 교정(2026-07-20): '설정 패널' 같은 화면은 없다 — 채팅 요청으로 변경 안내.
    answer = platform_defaults.reply("수수료는?")
    assert "설정 패널" not in answer
    assert "요청하시면" in answer
