"""Trace 파사드 — 실행 경로를 읽기만 하는 단일 진입점.

기록처(sink)는 둘이고 서로 독립이다:

- **LangSmith** — LANGSMITH_TRACING이 참일 때만. 외부 전송이므로 기본 꺼짐.
- **로컬(local_trace)** — AGENT_TRACE_LOCAL이 거짓이 아니면. 콘솔 트리 + JSONL 파일로
  같은 정보를 남긴다(외부 전송 없음이라 기본 켜짐). 끄기 = AGENT_TRACE_LOCAL=0.

계약(이 셋이 깨지면 관찰 계층이 아니다):

1. **LangSmith는 비활성이 기본값.** LANGSMITH_TRACING이 참이 아니면 langsmith를
   import하지 않는다. 활성 여부는 매번 env를 읽는다(캐시하지 않는다 — 테스트·운영이
   프로세스 수명 중에 끄고 켤 수 있어야 한다). 두 sink 모두 꺼져 있으면 span은
   완전한 no-op이다.
2. **감싼 코드의 반환값과 예외를 바꾸지 않는다.** span은 예외를 기록하고 다시 던진다.
   삼키지 않는다 — 폴백 판정은 전부 기존 호출부 소관이다.
3. **관찰 계층 자체의 실패는 실행을 깨뜨리지 않는다.** langsmith 장애·직렬화 실패는
   debug 로그로만 남기고 통과시킨다.

스레드 경계: langsmith는 contextvar로 부모를 찾는다. 이 코드베이스는 parse-stream이
파스를 별도 스레드에서 돌리고 planner shadow도 자기 daemon 스레드를 쓰므로, 그대로
두면 **Trace 계층이 끊긴다**(자식 span이 각자 루트가 된다). current_parent()로 부모를
꺼내 스레드에 넘기고 use_parent()로 복원하면 계층이 유지된다.
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from typing import Any, Dict, Iterator, Optional

from observability import local_trace as _local_trace
from observability import metrics as _metrics

logger = logging.getLogger("observability.tracing")

_TRUTHY = frozenset({"1", "true", "on", "yes"})

# span의 역할 → 성능 지표 버킷(스펙 § Performance Metrics). 여기 없는 역할은 총
# 소요 시간에만 잡힌다.
_DURATION_BUCKET = {
    "planner": "planner_ms",
    "tool": "tool_ms",
    "llm": "llm_ms",
    "state": "state_update_ms",
    "responder": "responder_ms",
}
# span의 역할 → 카운터.
_COUNTER = {"tool": "tool_count", "llm": "llm_calls", "action": "action_count"}

# 출력 직렬화 상한 — Trace에 전략 State 전문이 들어가면 UI에서 읽을 수 없고 전송량만
# 커진다. 잘린 값은 프리뷰이며, 판정에 쓰지 않는다.
_VALUE_LIMIT = 4000


def tracing_enabled() -> bool:
    """LANGSMITH_TRACING이 참일 때만 True. 기본 False(외부 전송 없음)."""
    return os.environ.get("LANGSMITH_TRACING", "").strip().lower() in _TRUTHY


def project_name() -> str:
    return os.environ.get("LANGSMITH_PROJECT", "").strip() or "NullStock"


def _environment() -> str:
    return (os.environ.get("NODE_ENV") or os.environ.get("APP_ENV") or "development").strip()


def base_metadata() -> Dict[str, Any]:
    """모든 Trace 공통 메타데이터(스펙 § LangSmith Metadata).

    version은 백테스트 엔진 버전 SOT를 그대로 쓴다 — 관찰 계층이 자기 버전 문자열을
    따로 만들면 정본이 둘이 된다(engine/version.py 계약).
    """
    meta: Dict[str, Any] = {
        "project": project_name(),
        "agent": "Strategy Planner",
        "environment": _environment(),
    }
    try:
        from engine.version import ENGINE_VERSION

        meta["version"] = f"v{ENGINE_VERSION}"
    except Exception:  # noqa: BLE001 — 버전 조회 실패가 추적을 막지 않는다
        meta["version"] = "unknown"
    return meta


def _truncate(value: Any) -> Any:
    """직렬화 안전 + 길이 제한. 실패해도 예외를 내지 않는다(문자열로 강등)."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= _VALUE_LIMIT else value[:_VALUE_LIMIT] + "…(생략)"
    if isinstance(value, dict):
        return {str(k): _truncate(v) for k, v in list(value.items())[:80]}
    if isinstance(value, (list, tuple)):
        return [_truncate(v) for v in list(value)[:80]]
    if hasattr(value, "model_dump"):
        try:
            return _truncate(value.model_dump())
        except Exception:  # noqa: BLE001
            pass
    return _truncate(repr(value))


class TraceHandle:
    """span 안에서 관찰값을 덧붙이는 손잡이 — LangSmith run과 로컬 노드 양쪽에 쓴다.

    비활성 span에서도 같은 메서드를 제공한다(호출부에 분기를 만들지 않기 위해) —
    그때는 전부 no-op이다.
    """

    __slots__ = ("_run", "_local")

    def __init__(self, run: Any = None, local: Any = None):
        self._run = run
        self._local = local

    @property
    def active(self) -> bool:
        return self._run is not None or self._local is not None

    def output(self, **values: Any) -> None:
        """이 span의 산출값. 여러 번 부르면 병합된다."""
        if not self.active:
            return
        truncated = {k: _truncate(v) for k, v in values.items()}
        if self._run is not None:
            try:
                merged = dict(getattr(self._run, "outputs", None) or {})
                merged.update(truncated)
                self._run.outputs = merged
            except Exception:  # noqa: BLE001
                logger.debug("trace output 기록 실패", exc_info=True)
        if self._local is not None:
            try:
                self._local.outputs.update(truncated)
            except Exception:  # noqa: BLE001
                logger.debug("로컬 trace output 기록 실패", exc_info=True)

    def meta(self, **values: Any) -> None:
        """이 span의 메타데이터."""
        if not self.active:
            return
        truncated = {k: _truncate(v) for k, v in values.items()}
        if self._run is not None:
            try:
                self._run.metadata.update(truncated)
            except Exception:  # noqa: BLE001
                logger.debug("trace metadata 기록 실패", exc_info=True)
        if self._local is not None:
            try:
                self._local.metadata.update(truncated)
            except Exception:  # noqa: BLE001
                logger.debug("로컬 trace metadata 기록 실패", exc_info=True)

    def error(self, kind: str, message: str) -> None:
        """실패 원인의 분류와 메시지(스펙 § Error Trace).

        예외로 끝나지 않는 실패 — 폴백 반환(None), 계약 위반, 예산 소진 — 를 남긴다.
        예외로 끝나는 실패는 span이 자동으로 잡는다.
        """
        if not self.active:
            return
        _metrics.bump("failure_count")
        text = f"[{kind}] {message}"[:2000]
        if self._run is not None:
            try:
                self._run.metadata.update({"error_kind": kind})
                self._run.error = text
            except Exception:  # noqa: BLE001
                logger.debug("trace error 기록 실패", exc_info=True)
        if self._local is not None:
            try:
                self._local.metadata["error_kind"] = kind
                self._local.error = text
            except Exception:  # noqa: BLE001
                logger.debug("로컬 trace error 기록 실패", exc_info=True)


_NOOP = TraceHandle(None)


@contextlib.contextmanager
def span(
    name: str,
    role: str = "chain",
    *,
    inputs: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    run_type: Optional[str] = None,
    root: bool = False,
) -> Iterator[TraceHandle]:
    """관찰 span 하나. 두 sink(LangSmith·로컬) 모두 비활성이면 no-op 손잡이를 즉시 내준다.

    role은 성능 지표 버킷·카운터를 고르는 우리 쪽 축이고, run_type은 LangSmith UI의
    표시 종류다(미지정 시 role에서 유도).

    root=True면 이 span이 Trace 루트다 — 성능 지표 누적기를 새로 걸고, 끝날 때
    누적 결과를 메타데이터로 붙인다.
    """
    ls_on = tracing_enabled()
    local_on = _local_trace.enabled()
    if not ls_on and not local_on:
        yield _NOOP
        return

    started = time.perf_counter()
    token = _metrics.bind(_metrics.new_metrics()) if root else None
    safe_inputs = {k: _truncate(v) for k, v in (inputs or {}).items()}
    meta = base_metadata() if root else {}
    meta.update(metadata or {})

    run = None
    cm = None
    if ls_on:
        try:
            from langsmith.run_helpers import trace as _ls_trace

            cm = _ls_trace(
                name,
                run_type=run_type or _ls_run_type(role),
                inputs=safe_inputs,
                metadata=meta,
                project_name=project_name() if root else None,
            )
            run = cm.__enter__()
        except Exception:  # noqa: BLE001 — 추적 개시 실패는 실행을 막지 않는다
            logger.debug("trace span 개시 실패 | name=%s", name, exc_info=True)
            cm = None
            run = None

    local_node = None
    local_token = None
    if local_on:
        try:
            local_node, local_token = _local_trace.start(
                name, role=role, inputs=safe_inputs, metadata=meta,
            )
        except Exception:  # noqa: BLE001
            logger.debug("로컬 trace span 개시 실패 | name=%s", name, exc_info=True)
            local_node = None
            local_token = None

    handle = TraceHandle(run, local_node) if (run is not None or local_node is not None) else _NOOP

    _bump_counter(role)
    exc_info: tuple = (None, None, None)
    try:
        yield handle
    except BaseException as exc:  # noqa: BLE001 — 기록만 하고 그대로 다시 던진다
        exc_info = (type(exc), exc, exc.__traceback__)
        _metrics.bump("failure_count")
        handle.meta(error_kind=type(exc).__name__)
        if local_node is not None and local_node.error is None:
            local_node.error = f"{type(exc).__name__}: {exc}"[:2000]
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        bucket = _DURATION_BUCKET.get(role)
        if bucket:
            _metrics.record_duration(bucket, elapsed_ms)
        if root and handle.active:
            collected = _metrics.current_metrics() or {}
            handle.meta(**collected, total_duration_ms=round(elapsed_ms, 2))
        if cm is not None:
            # langsmith가 예외를 삼켜도(__exit__ True) 무시한다 — 예외 전파는
            # 우리 계약이지 관찰 계층이 정할 일이 아니다.
            with contextlib.suppress(Exception):
                cm.__exit__(*exc_info)
        if local_node is not None:
            with contextlib.suppress(Exception):
                _local_trace.finish(local_node, local_token, elapsed_ms)
        if token is not None:
            _metrics.unbind(token)


def _ls_run_type(role: str) -> str:
    """우리 역할 축 → LangSmith run_type(표시 전용)."""
    if role in ("tool", "llm"):
        return role
    if role == "responder":
        return "chain"
    return "chain"


def _bump_counter(role: str) -> None:
    key = _COUNTER.get(role)
    if key:
        _metrics.bump(key)


def bump(key: str, amount: int = 1) -> None:
    """카운터 직접 증가(retry_count 등 span 경계와 맞지 않는 지표용)."""
    if tracing_enabled() or _local_trace.enabled():
        _metrics.bump(key, amount)


# ── 스레드 경계 ───────────────────────────────────────────────────────────────

def current_parent() -> Optional[Any]:
    """현재 span(부모)을 꺼낸다 — 스레드에 넘겨 계층을 잇기 위한 것.

    비활성이거나 추적 밖이면 None. 이 값을 받는 쪽은 use_parent()로 복원한다.
    반환값은 불투명하다(내부적으로 LangSmith run·성능 지표·로컬 노드의 묶음).
    """
    ls_on = tracing_enabled()
    local_on = _local_trace.enabled()
    if not ls_on and not local_on:
        return None
    run = None
    if ls_on:
        try:
            from langsmith.run_helpers import get_current_run_tree

            run = get_current_run_tree()
        except Exception:  # noqa: BLE001
            run = None
    local_node = _local_trace.current() if local_on else None
    if run is None and local_node is None:
        return None
    # 성능 지표 누적기도 함께 넘긴다 — 다른 스레드에서 잰 시간이 같은 Trace의 지표에
    # 잡혀야 한다(parse-stream은 파스 전체가 자식 스레드에 있다).
    return (run, _metrics.current_metrics(), local_node)


@contextlib.contextmanager
def use_parent(parent: Optional[Any]) -> Iterator[None]:
    """다른 스레드에서 current_parent()의 컨텍스트를 복원한다.

    parent가 None이거나 두 sink 모두 꺼져 있으면 아무 일도 하지 않는다.
    """
    if parent is None:
        yield
        return
    if isinstance(parent, tuple):
        if len(parent) == 3:
            run, collected, local_node = parent
        else:  # 구 형식 (run, metrics)
            run, collected = parent
            local_node = None
    else:
        run, collected, local_node = parent, None, None

    token = _metrics.bind(collected) if collected is not None else None
    local_token = None
    if local_node is not None and _local_trace.enabled():
        with contextlib.suppress(Exception):
            local_token = _local_trace.bind_parent(local_node)
    ls_cm = None
    if run is not None and tracing_enabled():
        try:
            from langsmith.run_helpers import tracing_context

            ls_cm = tracing_context(parent=run, enabled=True)
            ls_cm.__enter__()
        except Exception:  # noqa: BLE001 — 복원 실패는 계층만 잃고 실행은 계속된다
            logger.debug("trace 부모 복원 실패", exc_info=True)
            ls_cm = None
    try:
        yield
    finally:
        if ls_cm is not None:
            with contextlib.suppress(Exception):
                ls_cm.__exit__(None, None, None)
        if local_token is not None:
            _local_trace.unbind(local_token)
        if token is not None:
            _metrics.unbind(token)
