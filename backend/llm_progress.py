"""LLM 호출 재시도 진행 표시 — 요청 단위 진행 단계 채널.

전략 분석(파싱·빌더 스텝)은 SSE 요청 하나가 워커 스레드 하나를 돌리고, 엔드포인트는 그
스레드의 `stage_holder["stage"]`를 폴링해 `{"type":"stage","stage":…}` 이벤트로 흘린다.
LLM 전송 계층(`llm_chat`·`engine.nl_parser`)은 그 holder를 모르므로, 여기서 스레드 컨텍스트
(contextvar — `cancellation.bind`와 같은 계약: 워커 스레드 진입 함수 안에서 연다)에 holder를
묶어 두고, 재시도가 시작되면 `retrying` 단계를 쓰고 끝나면 이전 단계로 되돌린다.

사용자 지시(2026-09-08): LLM 호출 자체가 실패하면 먼저 재시도하고, 그동안 '재시도 중...'을
보여준다. 단계 어휘는 프론트 `ANALYSIS_STAGE_LABEL`(app/analytics/new/page.tsx)과 동기화한다.
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import Iterator, MutableMapping, Optional

RETRYING_STAGE = "retrying"

_holder: contextvars.ContextVar[Optional[MutableMapping[str, object]]] = contextvars.ContextVar(
    "llm_progress_holder", default=None
)


@contextlib.contextmanager
def bind(stage_holder: MutableMapping[str, object]) -> Iterator[None]:
    """현재 실행 컨텍스트(워커 스레드)에 진행 holder(`{"stage": …}`)를 묶는다."""
    reset = _holder.set(stage_holder)
    try:
        yield
    finally:
        _holder.reset(reset)


@contextlib.contextmanager
def retrying() -> Iterator[None]:
    """블록 동안 단계를 `retrying`으로 바꾸고, 벗어나면(성공·실패 모두) 이전 단계로 되돌린다.

    holder가 묶이지 않은 컨텍스트(비스트리밍 라우트·스크립트·테스트)에서는 아무 일도 하지 않는다.
    중첩되면 바깥 블록이 이전 단계를 되돌린다(안쪽은 이미 retrying이라 그대로 둔다)."""
    holder = _holder.get()
    if holder is None:
        yield
        return
    previous = holder.get("stage")
    if previous == RETRYING_STAGE:
        yield
        return
    holder["stage"] = RETRYING_STAGE
    try:
        yield
    finally:
        holder["stage"] = previous
