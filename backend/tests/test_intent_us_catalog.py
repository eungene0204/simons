"""US 서비스(/us) 분류기 agent — KR과 같은 설계, US 전용 정형 응답 카탈로그 회귀.

/us 요청은 X-UI-Language: en → ui_language 컨텍스트로 도착한다. 해석 레인(LLM)은
KR과 공유하고, 도메인 정책(라벨→정형 응답)만 언어로 카탈로그를 고른다
(intent/scope_us.py). 2026-08-26: /us에서 "hello" 인사가 한국어 정형 응답·한국어
해석 실패 안내로 나가던 것의 회귀.
"""

from __future__ import annotations

import json

import pytest

import ui_language
from intent import scope_us
from intent.classifier import (
    classify,
    _EFFECT_REPLIES,
    _EFFECT_REPLIES_EN,
    _LABEL_REPLIES,
    _LABEL_REPLIES_EN,
)
from intent.schemas import QueryIntent, WorkflowEffect, WorkflowStatus


def stub_llm(intent: str, **extra):
    """구조화 출력을 그대로 돌려주는 LLM 스텁(test_intent_interpreter와 동일 패턴)."""
    payload = json.dumps({"intent": intent, **extra}, ensure_ascii=False)
    return lambda system, user: payload


def classify_en(query: str, **kwargs):
    with ui_language.bind("en"):
        return classify(query, **kwargs)


# ── 카탈로그 구조 동일성 — 라벨/효과 키가 KR과 1:1이어야 한다 ────────────────

def test_us_catalog_mirrors_kr_label_keys():
    assert set(_LABEL_REPLIES_EN) == set(_LABEL_REPLIES)


def test_us_catalog_mirrors_kr_effect_keys():
    assert set(_EFFECT_REPLIES_EN) == set(_EFFECT_REPLIES)


# ── 인사(스크린샷 사고 회귀) ─────────────────────────────────────────────────

def test_greeting_on_us_lane_replies_in_english():
    result = classify_en("hello", llm=stub_llm("GREETING"))
    assert result.intent == QueryIntent.GREETING
    assert result.suggested_reply in scope_us.GREETING_REPLIES


def test_greeting_reply_is_deterministic_per_input():
    assert scope_us.greeting_reply("hello") == scope_us.greeting_reply("hello")


def test_greeting_on_kr_lane_stays_korean():
    result = classify("안녕", llm=stub_llm("GREETING"))
    assert result.intent == QueryIntent.GREETING
    assert "안녕하세요" in (result.suggested_reply or "") or "반갑습니다" in (
        result.suggested_reply or ""
    )


# ── 라벨 → US 정형 응답 ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "label, reply",
    [
        ("OFF_TOPIC", scope_us.OFFTOPIC_REFUSAL),
        ("STRATEGY_PICK", scope_us.STRATEGY_PICK_REPLY),
        ("PERSONAL_ADVICE", scope_us.PERSONAL_ADVICE_REPLY),
        ("LIVE_TRADING", scope_us.LIVE_TRADING_REPLY),
        ("UNSUPPORTED_FEATURE", scope_us.UNSUPPORTED_FEATURE_REPLY),
        ("ONBOARDING", scope_us.ONBOARDING_REPLY),
    ],
)
def test_label_maps_to_us_policy_reply(label, reply):
    """[규제 안전] US 레인도 안내 문구는 LLM이 짓지 않고 라벨에서 결정적으로 나온다."""
    result = classify_en("whatever", llm=stub_llm(label))
    assert result.intent == QueryIntent(label)
    assert result.suggested_reply == reply


def test_stock_pick_on_us_lane_redirects_in_english():
    result = classify_en("what stock should I buy?", llm=stub_llm("STOCK_PICK"))
    assert result.intent == QueryIntent.STOCK_PICK
    assert result.suggested_reply in scope_us.STOCK_PICK_REDIRECT


def test_stock_analysis_on_us_lane_redirects_in_english():
    result = classify_en("should I buy AAPL now?", llm=stub_llm("STOCK_ANALYSIS"))
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert "buy/sell judgments or recommendations" in (result.suggested_reply or "")


def test_strategy_advice_on_us_lane_carries_no_canned_reply():
    """전략 요청은 US 레인에서도 정형 응답으로 끝내지 않고 파싱으로 흘려보낸다."""
    result = classify_en("buy when RSI drops below 30", llm=stub_llm("STRATEGY_ADVICE"))
    assert result.intent == QueryIntent.STRATEGY_ADVICE
    assert result.suggested_reply is None


# ── 워크플로 제어 안내 ───────────────────────────────────────────────────────

def test_pause_effect_on_us_lane_replies_in_english():
    result = classify_en(
        "hold on a second",
        llm=stub_llm("STRATEGY_ADVICE", workflow_effect="PAUSE"),
        active_strategy=True,
        workflow_status=WorkflowStatus.ACTIVE,
    )
    assert result.workflow_effect == WorkflowEffect.PAUSE
    assert result.suggested_reply == scope_us.EFFECT_PAUSE_REPLY


def test_pause_effect_on_kr_lane_stays_korean():
    result = classify(
        "잠깐 멈춰",
        llm=stub_llm("STRATEGY_ADVICE", workflow_effect="PAUSE"),
        active_strategy=True,
        workflow_status=WorkflowStatus.ACTIVE,
    )
    assert result.workflow_effect == WorkflowEffect.PAUSE
    assert result.suggested_reply == _EFFECT_REPLIES[WorkflowEffect.PAUSE]
