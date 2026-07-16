"""StrategyDraft 대화 상태 — 다중 턴 전략 대화의 세션별 초안 유지.

사용자가 "10% 이상", "한 달마다"처럼 짧게 답해도 이전 질문과 초안을 기준으로
이해할 수 있도록, 대화별로 초안·대기 질문·필드 확정 이력을 보존한다.

Phase 1(Shadow)에서는 인메모리 저장소만 제공한다 — 라우트 배선(Phase 2)에서
대화 세션과 연결한다.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from strategy_conversation.interpreter.models import (
    ClarificationQuestion,
    PatchOp,
    StrategySpec,
)
from strategy_conversation.conversation.patch_applier import apply_patches


class StrategyDraftState(BaseModel):
    conversation_id: str
    revision: int = 0
    current_strategy_draft: Optional[StrategySpec] = None
    pending_questions: List[ClarificationQuestion] = Field(default_factory=list)
    confirmed_fields: List[str] = Field(default_factory=list)
    inferred_fields: List[str] = Field(default_factory=list)
    last_user_message: str = ""
    last_interpreter_result: Optional[dict] = None
    updated_at: float = Field(default_factory=time.time)

    def replace_draft(self, draft: StrategySpec, user_message: str) -> None:
        self.current_strategy_draft = draft
        self.last_user_message = user_message
        self.revision += 1
        self.updated_at = time.time()

    def apply_patches(self, patches: List[PatchOp], user_message: str) -> StrategySpec:
        """현재 초안에 패치를 적용하고 새 revision으로 갱신한다."""
        if self.current_strategy_draft is None:
            raise ValueError("패치를 적용할 전략 초안이 없습니다")
        patched = apply_patches(self.current_strategy_draft, patches)
        self.replace_draft(patched, user_message)
        return patched

    def confirm_field(self, field: str) -> None:
        if field not in self.confirmed_fields:
            self.confirmed_fields.append(field)
        self.pending_questions = [q for q in self.pending_questions if q.field != field]
        self.updated_at = time.time()


class DraftStore:
    """대화 ID → StrategyDraftState 인메모리 저장소(스레드 안전)."""

    def __init__(self, ttl_s: float = 3600.0):
        self._states: Dict[str, StrategyDraftState] = {}
        self._lock = threading.Lock()
        self._ttl_s = ttl_s

    def get_or_create(self, conversation_id: str) -> StrategyDraftState:
        with self._lock:
            self._evict_expired()
            state = self._states.get(conversation_id)
            if state is None:
                state = StrategyDraftState(conversation_id=conversation_id)
                self._states[conversation_id] = state
            return state

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, v in self._states.items() if now - v.updated_at > self._ttl_s]
        for key in expired:
            del self._states[key]
