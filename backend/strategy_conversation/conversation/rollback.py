"""되돌리기 대상 판정(설계 스펙 § 19) — "어디로 되돌리는가"를 LLM이 정한다.

"아까 바꾼 거 취소해"·"ETF로 바꾸기 전으로"·"PER 조건 지운 것만 되돌려"는 전부
사용자 원문의 의미 해석이다 → LLM 소관이다(CLAUDE.md 대원칙 1). 이 모듈의 정규식은
LLM 출력에만 걸리고, 원문에는 어떤 패턴 매칭도 하지 않는다.

결정론 코드가 하는 일은 셋뿐이다:
  ① LLM이 고른 턴 번호가 실제 이력 범위 안인지 대조
  ② LLM이 고른 필드가 그 이력에 실제로 등장한 필드인지 대조(닫힌 목록)
  ③ 둘 중 하나라도 어긋나면 임의 보정하지 않고 되묻기로 강등

되돌리기의 **적용**은 여기가 아니다 — 스냅샷을 들고 있는 프론트가 결정론으로 복원한다.
이 레인은 "무엇을 복원할지"만 정한다.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from strategy_conversation.conversation.change_log import (
    restorable_fields,
    summarize_for_prompt,
)

logger = logging.getLogger("strategy_interpreter.rollback")

LLMFn = Callable[[str, str], str]

SYSTEM_PROMPT = (
    "너는 주식 전략 대화의 '되돌리기' 요청에서 되돌릴 지점을 고르는 판정기다.\n"
    "사용자가 방금 이전 상태로 되돌려 달라고 했다. 변경 이력을 보고 어디로 되돌릴지 정한다.\n"
    "\n"
    "scope 값:\n"
    "TURN — 특정 변경을 통째로 되돌린다. 그 변경 **직전** 상태로 돌아간다.\n"
    "  ('아까 바꾼 거 취소해' → 가장 최근 변경, 'ETF로 바꾸기 전으로' → ETF로 바꾼 그 변경)\n"
    "FIELDS — 그 변경 중 일부 항목만 되돌린다.\n"
    "  ('PER 조건 지운 것만 되돌려' → 그 변경에서 재무 조건 항목만)\n"
    "NONE — 되돌릴 지점을 이력에서 특정할 수 없다.\n"
    "\n"
    "판단 규칙:\n"
    "1. turn_index는 반드시 이력에 있는 번호 중 하나다. 없는 번호를 지어내지 마라.\n"
    "2. fields는 그 턴의 '바뀐 항목'에 실제로 있는 이름만 쓴다. 괄호 안 설명이 아니라\n"
    "   괄호 앞의 영문 이름을 그대로 쓴다. 새 이름을 만들지 마라.\n"
    "3. 사용자가 특정 항목을 말하면 그 항목이 '바뀐 항목'에 있는 턴을 고른다.\n"
    "   괄호 안 설명이 사용자의 표현과 이어진다 — 예: '손절 바꾼 거'는 손절이\n"
    "   바뀐 턴이고, 'PER 조건 지운 거'는 재무 조건이 바뀐 턴이다.\n"
    "4. 가리키는 대상이 없는 요청('되돌려', '취소해', '아까 거')은 **가장 큰 번호**의\n"
    "   변경을 되돌린다 — 방금 한 것을 되돌리는 뜻이다.\n"
    "5. 사용자가 말한 항목이 여러 턴에서 바뀌었고 어느 쪽인지 좁혀지지 않으면\n"
    "   ambiguous를 true로 하고, 무엇을 되돌릴지 고르게 하는 짧은 질문을 question에 쓴다.\n"
    "6. 되돌리기는 사용자가 쌓아온 작업을 지운다 — 확실하지 않으면 추측하지 말고 물어라.\n"
    "7. 사용자가 말한 항목이 이력의 어느 턴에도 없으면 scope는 NONE이다.\n"
    "\n"
    "출력 형식(JSON 한 줄, 다른 말 금지):\n"
    '{"scope": "<TURN|FIELDS|NONE>", "turn_index": <번호 또는 null>, '
    '"fields": ["<항목 이름>"], "ambiguous": <true|false>, '
    '"question": "<되물을 질문 또는 null>"}'
)


class RollbackTarget(BaseModel):
    """LLM이 내놓는 제한된 구조화 출력. 이 모델을 통과한 값만 결정론 대조로 넘어간다."""

    scope: str = "NONE"
    turn_index: Optional[int] = None
    fields: List[str] = Field(default_factory=list)
    ambiguous: bool = False
    question: Optional[str] = None


class RollbackDecision(BaseModel):
    """결정론 대조를 마친 최종 판정. 프론트는 이 값만 보고 복원한다."""

    # "turn": 그 턴 직전 상태로 전체 복원 / "fields": 지정 항목만 그때 값으로 되돌림
    # "clarify": 되물어야 함(복원하지 않음) / "unsupported": 되돌릴 이력이 없음
    action: str
    turn_index: Optional[int] = None
    fields: List[str] = Field(default_factory=list)
    question: Optional[str] = None
    reason: str = ""


_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

_CLARIFY_QUESTION = "어떤 변경을 되돌릴까요? 되돌릴 항목을 말씀해 주세요."
_NO_HISTORY_QUESTION = (
    "아직 되돌릴 변경 이력이 없어요. 바꾸고 싶은 조건을 말씀해 주시면 반영해 드릴게요."
)


def _extract_json(raw: str) -> Optional[dict]:
    """LLM 출력에서 JSON 객체 하나를 꺼낸다. 실패하면 None(임의 보정 금지)."""
    text = _THINK_BLOCK.sub("", raw or "")
    text = _CODE_FENCE.sub("", text.strip())
    match = _JSON_OBJECT.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def build_user_message(user_input: str, events: List[Dict[str, Any]]) -> str:
    return (
        f"[변경 이력]\n{summarize_for_prompt(events)}\n\n"
        f"[되돌리기 요청]\n{user_input}"
    )


def _event_by_index(events: List[Dict[str, Any]], index: Any) -> Optional[Dict[str, Any]]:
    for event in events:
        if event.get("index") == index:
            return event
    return None


def resolve(
    user_input: str, events: List[Dict[str, Any]], llm: Optional[LLMFn]
) -> RollbackDecision:
    """되돌리기 대상을 판정한다. 복원은 하지 않는다(프론트 소관).

    events: 프론트가 에코한 변경 이력. 각 항목은 {index, user_text, changed_fields}.
    되돌릴 수 있는 변경(changed_fields가 있는 항목)이 없으면 LLM을 부르지 않는다.
    """
    revertible = [e for e in events if e.get("changed_fields")]
    if not revertible:
        return RollbackDecision(
            action="unsupported", question=_NO_HISTORY_QUESTION,
            reason="되돌릴 변경 이력 없음",
        )
    if llm is None:
        return RollbackDecision(
            action="clarify", question=_CLARIFY_QUESTION, reason="판정 LLM 미가용",
        )

    raw = llm(SYSTEM_PROMPT, build_user_message(user_input, revertible))
    payload = _extract_json(raw)
    if payload is None:
        return RollbackDecision(
            action="clarify", question=_CLARIFY_QUESTION, reason="LLM 구조화 출력 해석 실패",
        )
    try:
        target = RollbackTarget.model_validate(payload)
    except ValidationError:
        return RollbackDecision(
            action="clarify", question=_CLARIFY_QUESTION, reason="LLM 출력 스키마 불일치",
        )

    scope = (target.scope or "").strip().upper()
    if target.ambiguous or scope == "NONE":
        # 되돌리기는 사용자가 쌓아온 작업을 지운다 — 추측으로 실행하지 않는다.
        return RollbackDecision(
            action="clarify",
            question=(target.question or "").strip() or _CLARIFY_QUESTION,
            reason="LLM이 대상을 특정하지 못함",
        )

    event = _event_by_index(revertible, target.turn_index)
    if event is None:
        # 지어낸 번호는 임의 보정하지 않는다(가장 최근 턴으로 떨어뜨리면 사용자가
        # 의도하지 않은 변경이 조용히 사라진다).
        return RollbackDecision(
            action="clarify", question=_CLARIFY_QUESTION,
            reason=f"이력에 없는 턴 번호({target.turn_index!r})",
        )

    if scope == "FIELDS":
        allowed = set(event.get("changed_fields") or [])
        picked = [f for f in target.fields if f in allowed]
        if not picked:
            # 그 턴에서 바뀌지 않은 항목은 되돌릴 것이 없다.
            return RollbackDecision(
                action="clarify", question=_CLARIFY_QUESTION,
                reason="LLM이 고른 항목이 그 턴의 변경 목록에 없음",
            )
        return RollbackDecision(
            action="fields", turn_index=target.turn_index, fields=picked,
            reason="지정 항목만 되돌림",
        )

    if scope == "TURN":
        return RollbackDecision(
            action="turn", turn_index=target.turn_index,
            fields=list(event.get("changed_fields") or []),
            reason="해당 변경 전체를 되돌림",
        )

    return RollbackDecision(
        action="clarify", question=_CLARIFY_QUESTION,
        reason=f"알 수 없는 scope({target.scope!r})",
    )


# 닫힌 목록 노출용 — 라우트가 이력 전체의 되돌릴 수 있는 필드를 함께 내려준다.
__all__ = ["RollbackDecision", "RollbackTarget", "resolve", "restorable_fields"]
