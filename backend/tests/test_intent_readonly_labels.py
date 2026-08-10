"""읽기 전용 라벨(STRATEGY_STATUS·RESULT_EXPLAIN) 도메인 정책 테스트.

이 두 라벨이 없을 때 9B는 같은 입력을 STRATEGY_ADVICE↔UNKNOWN으로 흔들었고, 라벨
자리에 제어값을 넣는 출력(`{"intent": "NONE"}`)까지 냈다(2026-08-11 커버리지 프로브).
라벨을 만든 뒤 지켜야 하는 계약은 둘이다:

1. **읽기 전용이다** — 상태를 묻기만 하는 발화가 워크플로를 제어하거나 되묻기 대상을
   지목하면 안 된다. '아까 손절 몇 퍼센트로 했었지?'가 ROLLBACK으로 새면 묻기만 한
   사용자의 전략이 되감긴다.
2. **규제 게이트가 아니다** — 정형 거절 문구를 달지 않는다(답은 화면이 상태로 만든다).
"""

from __future__ import annotations

import pytest

from intent import classifier, interpreter
from intent.schemas import QueryIntent, WorkflowEffect, WorkflowStatus


def _interp(intent: QueryIntent, **kwargs) -> interpreter.IntentInterpretation:
    return interpreter.IntentInterpretation(intent=intent, **kwargs)


@pytest.mark.parametrize(
    "intent", [QueryIntent.STRATEGY_STATUS, QueryIntent.RESULT_EXPLAIN]
)
@pytest.mark.parametrize(
    "effect",
    [
        WorkflowEffect.ROLLBACK,
        WorkflowEffect.CANCEL,
        WorkflowEffect.RESTART,
        WorkflowEffect.UPDATE,
    ],
)
def test_readonly_labels_never_control_workflow(intent, effect):
    """묻기만 하는 발화는 상태를 바꾸지 않는다 — 제어 효과는 NONE으로 강등된다."""
    result = classifier._apply_domain_policy(
        _interp(intent, workflow_effect=effect),
        last_symbol=None,
        query="아까 손절 몇 퍼센트로 했었지?",
        active_strategy=True,
        workflow_status=WorkflowStatus.ACTIVE,
    )

    assert result.intent is intent
    assert result.workflow_effect is WorkflowEffect.NONE
    # 진행 상태도 제어 전이를 타지 않는다(묻기 전과 같다).
    assert result.workflow_status is WorkflowStatus.ACTIVE


@pytest.mark.parametrize(
    "intent", [QueryIntent.STRATEGY_STATUS, QueryIntent.RESULT_EXPLAIN]
)
def test_readonly_labels_never_set_clarify_target(intent):
    """되묻기 대상 지목도 없다 — 바꿀 대상을 말한 것이 아니라 물은 것이다."""
    result = classifier._apply_domain_policy(
        _interp(intent, clarify_target="stop_loss"),
        last_symbol=None,
        query="아까 손절 몇 퍼센트로 했었지?",
        active_strategy=True,
        workflow_status=WorkflowStatus.ACTIVE,
    )

    assert result.clarify_target is None


@pytest.mark.parametrize(
    "intent", [QueryIntent.STRATEGY_STATUS, QueryIntent.RESULT_EXPLAIN]
)
def test_readonly_labels_carry_no_canned_reply(intent):
    """규제 게이트가 아니므로 정형 거절 문구를 달지 않는다.

    답은 상태를 가진 화면이 만든다 — 백엔드가 문구를 얹으면 카드와 문구가 어긋난다.
    """
    result = classifier._apply_domain_policy(
        _interp(intent),
        last_symbol=None,
        query="내가 지금까지 뭘 정했지?",
        active_strategy=True,
        workflow_status=WorkflowStatus.ACTIVE,
    )

    assert result.suggested_reply is None


def test_prompt_documents_both_labels():
    """프롬프트에 라벨 정의와 경계 규칙이 함께 있어야 한다.

    정의만 있고 경계(바꾸기 vs 묻기, 일반 지식 vs 내 결과)가 없으면 인접 라벨과
    섞인다 — 그게 라벨을 추가한 이유 자체다.
    """
    prompt = interpreter.SYSTEM_PROMPT

    assert "STRATEGY_STATUS" in prompt
    assert "RESULT_EXPLAIN" in prompt
    # 경계 규칙 4-3(묻기 vs 바꾸기)·4-4(일반 지식 vs 내 결과)
    assert "4-3." in prompt and "4-4." in prompt
