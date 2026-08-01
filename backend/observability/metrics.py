"""Trace 단위 성능 지표 누적기 — span이 끝날 때마다 스스로 더한다.

지표는 **관찰의 부산물**이다. 실행 코드가 자기 소요 시간을 보고하도록 고치는 대신,
tracing.span()이 종료 시점에 이 누적기에 더한다. 그래서 이 모듈을 아는 실행 코드는
하나도 없다.

누적기는 contextvar에 산다 — 요청(Trace) 하나가 자기 것만 본다. 요청이 스레드를
건너가면(parse-stream) contextvar가 따라가지 않으므로, tracing.use_parent()가
누적기도 함께 복원한다.
"""

from __future__ import annotations

import contextvars
from typing import Any, Dict, Optional

# 소요 시간을 더할 버킷 이름 ← span의 run_type/역할. 스펙 § Performance Metrics.
_DURATION_KEYS = ("planner_ms", "tool_ms", "llm_ms", "state_update_ms", "responder_ms")
_COUNT_KEYS = ("action_count", "tool_count", "llm_calls", "retry_count", "failure_count")

_current: contextvars.ContextVar[Optional[Dict[str, Any]]] = contextvars.ContextVar(
    "nullstock_trace_metrics", default=None,
)


def new_metrics() -> Dict[str, Any]:
    """Trace 하나의 빈 지표 묶음."""
    metrics: Dict[str, Any] = {key: 0.0 for key in _DURATION_KEYS}
    metrics.update({key: 0 for key in _COUNT_KEYS})
    return metrics


def current_metrics() -> Optional[Dict[str, Any]]:
    """현재 Trace의 지표 묶음(없으면 None — 추적 밖 호출)."""
    return _current.get()


def bind(metrics: Optional[Dict[str, Any]]) -> contextvars.Token:
    """지표 묶음을 현재 컨텍스트에 건다. 반환 토큰으로 되돌린다."""
    return _current.set(metrics)


def unbind(token: contextvars.Token) -> None:
    try:
        _current.reset(token)
    except ValueError:
        # 다른 컨텍스트에서 만든 토큰(스레드 경계) — 되돌릴 것이 없다.
        pass


def record_duration(bucket: str, elapsed_ms: float) -> None:
    """소요 시간을 버킷에 더한다. 추적 밖이면 아무 일도 하지 않는다."""
    metrics = _current.get()
    if metrics is None or bucket not in _DURATION_KEYS:
        return
    metrics[bucket] = round(metrics[bucket] + elapsed_ms, 2)


def bump(key: str, amount: int = 1) -> None:
    """카운터를 올린다. 추적 밖이면 아무 일도 하지 않는다."""
    metrics = _current.get()
    if metrics is None or key not in _COUNT_KEYS:
        return
    metrics[key] += amount
