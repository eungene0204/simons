"""분류·일반답변 레인 Trace 테스트 — "무엇을 못 알아듣나"의 근거를 남기는 계측.

전략 파싱 레인과 달리 이 레인은 계측 사각지대였다(라벨 분포·UNKNOWN 발화를 사후
조회할 수 없었다). 검증 대상은 관찰 계층 계약 그대로다:

- 관찰이 결과를 바꾸지 않는다(반환값 통과).
- 추적이 꺼져 있어도 동일하게 동작한다.
- span 출력이 IntentResult 필드와 어긋나지 않는다 — enum 필드(workflow_effect)를
  꺼내다 AttributeError가 나면 엔드포인트 자체가 깨진다.
"""

from __future__ import annotations

import asyncio

import pytest

from api import intent_routes
from intent.schemas import (
    DetectedSymbol,
    IntentRequest,
    IntentResult,
    QueryIntent,
    WorkflowEffect,
    WorkflowStatus,
)


@pytest.fixture(autouse=True)
def _local_trace_on(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_TRACE_LOCAL", "1")
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)


_RESULT = IntentResult(
    intent=QueryIntent.UNKNOWN,
    symbols=[DetectedSymbol(symbol="005930", name="삼성전자")],
    confidence=0.4,
    reason="LLM 의미 해석",
    deterministic=False,
    workflow_effect=WorkflowEffect.NONE,
    workflow_status=WorkflowStatus.IDLE,
)


def test_classify_span_passes_result_through(monkeypatch):
    """계측이 붙어도 분류 결과는 그대로 나간다."""
    monkeypatch.setattr(intent_routes, "_llm_available", lambda: False)
    monkeypatch.setattr(intent_routes, "classify", lambda *a, **k: _RESULT)

    result = asyncio.run(intent_routes.classify_query(IntentRequest(query="그건 뭐야?")))

    assert result is _RESULT


def test_classify_span_reads_every_reported_field(monkeypatch):
    """span이 꺼내는 필드가 IntentResult에 실제로 있어야 한다.

    workflow_effect·workflow_status는 enum이라 .value로 꺼낸다 — 스키마가 평문
    문자열로 바뀌면 여기서 먼저 깨져야 하고, 엔드포인트가 500으로 깨지면 안 된다.
    """
    monkeypatch.setattr(intent_routes, "_llm_available", lambda: False)
    monkeypatch.setattr(intent_routes, "classify", lambda *a, **k: _RESULT)

    result = asyncio.run(
        intent_routes.classify_query(
            IntentRequest(query="그건 뭐야?", active_strategy=True, pending_question="손절은?")
        )
    )

    assert result.intent is QueryIntent.UNKNOWN


def test_classify_works_with_tracing_disabled(monkeypatch):
    """관찰이 꺼져 있어도(no-op span) 동작이 같다."""
    monkeypatch.setenv("AGENT_TRACE_LOCAL", "0")
    monkeypatch.setattr(intent_routes, "_llm_available", lambda: False)
    monkeypatch.setattr(intent_routes, "classify", lambda *a, **k: _RESULT)

    assert asyncio.run(intent_routes.classify_query(IntentRequest(query="그건 뭐야?"))) is _RESULT


def test_general_answer_span_reports_deterministic_source(monkeypatch):
    """플랫폼 기본값으로 결정적으로 답한 턴은 LLM을 부르지 않는다."""
    monkeypatch.setattr(intent_routes.platform_defaults, "reply", lambda q: "기본 수수료는 0.015%입니다.")

    def _boom(*a, **k):  # pragma: no cover — 불리면 실패
        raise AssertionError("결정론 답변 경로에서 LLM을 부르면 안 된다")

    # 어댑터 두 갈래(구조화·산문) 모두 막는다 — 결정론 경로는 어느 쪽도 부르지 않는다.
    monkeypatch.setattr(intent_routes, "_mlx_llm_structured", _boom)
    monkeypatch.setattr(intent_routes, "_mlx_llm_prose", _boom)

    assert intent_routes.generate_general_answer("수수료 기본값이 뭐야?") == "기본 수수료는 0.015%입니다."


def test_general_answer_span_returns_none_without_llm(monkeypatch):
    """LLM이 없으면 None을 그대로 돌려준다(계측이 삼키지 않는다)."""
    monkeypatch.setattr(intent_routes.platform_defaults, "reply", lambda q: None)
    monkeypatch.setattr(intent_routes, "_llm_available", lambda: False)

    assert intent_routes.generate_general_answer("RSI가 뭐야?") is None
