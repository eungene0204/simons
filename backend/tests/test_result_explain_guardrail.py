"""결과 수치 설명의 규제 가드 테스트.

[규제 안전] CLAUDE.md — 과거 데이터 사실 서술은 허용, 우열 판단은 금지다.
프롬프트로 "등급 매기지 마라"를 지시해도 9B가 완전히 지키지 못하므로(실측 2026-08-11:
'샤프 지수 1.21은 위험 조정 후 수익성이 긍정적인 수준') 출력 필터를 마지막에 둔다.

필터가 **지워야 하는 것**과 **남겨야 하는 것**을 같이 고정한다 — 과하게 지우면
정당한 사실 설명까지 사라져 답변이 빈다.
"""

from __future__ import annotations

import pytest

from stock_analysis.guardrails import strip_metric_grading


@pytest.mark.parametrize(
    "sentence",
    [
        "샤프 지수 1.21은 위험 조정 후 수익성이 긍정적인 수준으로 해석됩니다.",
        "이 전략의 성과는 양호합니다.",
        "수익률이 우수한 편입니다.",
        "변동성이 낮아 안정적인 결과입니다.",
        "자본 효율이 효율적으로 사용되었습니다.",
        "승률이 저조합니다.",
        "이 정도면 좋은 결과입니다.",
    ],
)
def test_grading_sentences_are_removed(sentence):
    assert strip_metric_grading(sentence) == ""


@pytest.mark.parametrize(
    "sentence",
    [
        "최대 낙폭은 -22.5%였습니다.",
        "승률이 54.0%로 절반을 넘었습니다.",
        "승률이 높아도 평균 손실이 크면 총손익은 마이너스가 될 수 있습니다.",
        "샤프 지수는 위험 대비 초과 수익을 나타내는 지표이며, 계산된 값은 1.21입니다.",
        "총 88회의 거래가 발생했습니다.",
        "과거 데이터를 기반으로 한 시뮬레이션 결과입니다.",
    ],
)
def test_factual_sentences_survive(sentence):
    """사실 서술·지표 간 관계 설명은 남는다(과하게 지우면 답변이 빈다)."""
    assert strip_metric_grading(sentence) == sentence


def test_mixed_answer_keeps_facts_and_drops_grading():
    text = (
        "최대 낙폭은 -22.5%였습니다. "
        "이는 위험 대비 수익 효율이 양호하다는 뜻입니다. "
        "총 88회의 거래가 발생했습니다."
    )

    cleaned = strip_metric_grading(text)

    assert "최대 낙폭은 -22.5%였습니다." in cleaned
    assert "총 88회의 거래가 발생했습니다." in cleaned
    assert "양호" not in cleaned


def test_empty_input_is_safe():
    assert strip_metric_grading("") == ""


def test_result_prompt_forbids_recommendation_and_forecast():
    """프롬프트가 금지 축 세 가지를 모두 명시해야 한다(평가·권유·전망)."""
    from api.intent_routes import _RESULT_SYSTEM_PROMPT

    assert "지어내지" in _RESULT_SYSTEM_PROMPT          # 수치 환각 금지
    assert "전망" in _RESULT_SYSTEM_PROMPT              # 미래 예측 금지
    assert "등급" in _RESULT_SYSTEM_PROMPT              # 지표 등급 금지
    assert "몬테카를로" in _RESULT_SYSTEM_PROMPT        # 판단 요구 → 검증 기능 안내
