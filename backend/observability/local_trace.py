"""로컬 Agent Trace 레코더 — LangSmith와 같은 정보를 외부 전송 없이 남긴다.

tracing.span()이 수집하는 것(계층·입출력·메타데이터·소요 시간·오류·성능 지표)을
그대로 받아 두 곳에 남긴다:

1. **콘솔** — 요청 하나가 끝날 때 span 트리를 사람이 읽는 형태로 출력한다.
   값은 raw JSON 한 줄이 아니라 `key = value` 컬럼으로 편다([LLM-INTERPRETER]의
   _flatten_json_columns 선례, 사용자 요청 2026-07-29).
2. **JSONL 파일** — `logs/agent_traces/YYYY-MM-DD.jsonl`에 Trace 하나가 한 줄.
   전체 트리가 구조 그대로 들어가므로 나중에 프로그램으로도 조회할 수 있다.

계약은 tracing.py와 같다:
- 기록 실패는 실행을 깨뜨리지 않는다(debug 로그로만 남긴다).
- 감싼 코드의 반환값·예외를 바꾸지 않는다 — 이 모듈은 자료구조만 쌓는다.
- `AGENT_TRACE_LOCAL=0`이면 완전한 no-op. 기본은 켜짐(외부 전송이 없으므로
  LangSmith와 달리 opt-out이다). 테스트는 conftest가 기본 꺼짐으로 둔다.

스레드 경계: LangSmith와 같은 함정이 있다(contextvar는 스레드를 건너지 않는다).
tracing.current_parent()/use_parent()가 로컬 부모 노드도 함께 실어 나른다. 후행
검증(SSE 응답 후)처럼 **루트가 이미 방출된 뒤** 도착하는 span은 같은 trace_id를
단 별도 레코드(late_attach)로 남긴다 — 방출된 트리를 소급 수정하면 파일과 콘솔이
어긋난다.
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("observability.local_trace")

_TRUTHY = frozenset({"1", "true", "on", "yes"})

# 콘솔 컬럼 값의 길이 상한 — 전문은 JSONL에 있다. 콘솔은 흐름을 읽는 곳이다.
_CONSOLE_VALUE_LIMIT = 160
# span 하나가 콘솔에 찍는 상세 줄 상한 — DAG 스냅샷 같은 큰 관찰값의 폭주 방지.
_CONSOLE_ROW_LIMIT = 40

_current: contextvars.ContextVar[Optional["LocalSpan"]] = contextvars.ContextVar(
    "nullstock_local_trace_span", default=None,
)
_file_lock = threading.Lock()


def enabled() -> bool:
    """AGENT_TRACE_LOCAL이 거짓이 아니면 True. 기본 켜짐(로컬 기록만, 외부 전송 없음)."""
    return os.environ.get("AGENT_TRACE_LOCAL", "1").strip().lower() in _TRUTHY


def trace_dir() -> Path:
    """JSONL 저장 위치. 기본은 backend/logs/agent_traces(.gitignore의 /backend/logs/)."""
    override = os.environ.get("AGENT_TRACE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "logs" / "agent_traces"


class LocalSpan:
    """span 하나의 관찰값. tracing.TraceHandle이 outputs/metadata/error를 채운다."""

    __slots__ = (
        "name", "role", "trace_id", "started_at", "duration_ms",
        "inputs", "outputs", "metadata", "error",
        "children", "parent", "root", "late", "emitted",
    )

    def __init__(self, name: str, role: str, inputs: Dict[str, Any],
                 metadata: Dict[str, Any], trace_id: str, late: bool = False):
        self.name = name
        self.role = role
        self.trace_id = trace_id
        self.started_at = _dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
        self.duration_ms: Optional[float] = None
        self.inputs = dict(inputs)
        self.outputs: Dict[str, Any] = {}
        self.metadata = dict(metadata)
        self.error: Optional[str] = None
        self.children: List["LocalSpan"] = []
        self.parent: Optional["LocalSpan"] = None
        self.root: "LocalSpan" = self
        self.late = late
        self.emitted = False

    def to_dict(self) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "name": self.name,
            "role": self.role,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
        }
        if self.inputs:
            entry["inputs"] = self.inputs
        if self.outputs:
            entry["outputs"] = self.outputs
        if self.metadata:
            entry["metadata"] = self.metadata
        if self.error:
            entry["error"] = self.error
        if self.children:
            entry["children"] = [child.to_dict() for child in self.children]
        return entry


# ── span 수명 (tracing.span 전용 진입점) ─────────────────────────────────────

def start(name: str, role: str, inputs: Dict[str, Any],
          metadata: Dict[str, Any]) -> Tuple[LocalSpan, contextvars.Token]:
    """span 시작 — 현재 컨텍스트의 부모에 붙이고 자신을 현재 span으로 만든다.

    부모의 루트가 이미 방출됐으면(후행 스레드) 같은 trace_id의 새 최상위 span으로
    시작한다(late_attach).
    """
    parent = _current.get()
    if parent is not None and not parent.root.emitted:
        node = LocalSpan(name, role, inputs, metadata, trace_id=parent.trace_id)
        node.parent = parent
        node.root = parent.root
        parent.children.append(node)
    elif parent is not None:
        node = LocalSpan(name, role, inputs, metadata,
                         trace_id=parent.trace_id, late=True)
    else:
        node = LocalSpan(name, role, inputs, metadata, trace_id=uuid.uuid4().hex[:12])
    token = _current.set(node)
    return node, token


def finish(node: LocalSpan, token: Optional[contextvars.Token],
           elapsed_ms: float) -> None:
    """span 종료 — 최상위 span이면 Trace 하나로 방출(파일+콘솔)한다."""
    if token is not None:
        try:
            _current.reset(token)
        except ValueError:
            # 다른 컨텍스트에서 만든 토큰(스레드 경계) — 되돌릴 것이 없다.
            pass
    node.duration_ms = round(elapsed_ms, 2)
    if node.parent is None:
        _emit(node)


# ── 스레드 경계 (tracing.current_parent/use_parent 전용) ─────────────────────

def current() -> Optional[LocalSpan]:
    return _current.get()


def bind_parent(node: LocalSpan) -> contextvars.Token:
    return _current.set(node)


def unbind(token: contextvars.Token) -> None:
    try:
        _current.reset(token)
    except ValueError:
        pass


# ── 방출 ─────────────────────────────────────────────────────────────────────

def _emit(node: LocalSpan) -> None:
    """완결된 Trace 하나를 파일과 콘솔에 남긴다. 실패해도 예외를 내지 않는다."""
    node.emitted = True
    record = {
        "trace_id": node.trace_id,
        "ts": node.started_at,
        "root": node.name,
        "total_ms": node.duration_ms,
        "span": node.to_dict(),
    }
    if node.late:
        record["late_attach"] = True
    try:
        directory = trace_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{_dt.date.today():%Y-%m-%d}.jsonl"
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _file_lock:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        # 보관 정책(원문 3일, 집계 후 폐기) — 기록이 도는 곳에서만 하루 한 번 스윕한다.
        # cron이 아니라 여기 두는 이유: Trace가 꺼진 환경에는 정리할 파일도 안 생긴다.
        from observability import retention

        retention.maybe_sweep(directory)
    except Exception:  # noqa: BLE001 — 기록 실패가 실행을 막지 않는다
        logger.debug("로컬 trace 파일 기록 실패", exc_info=True)
    try:
        print(render_console(node), flush=True)
    except Exception:  # noqa: BLE001
        logger.debug("로컬 trace 콘솔 출력 실패", exc_info=True)


def render_console(node: LocalSpan) -> str:
    """Trace 트리를 사람이 읽는 한 덩어리로. 값은 key = value 컬럼."""
    late = " (late_attach)" if node.late else ""
    lines = [f"[AGENT-TRACE] trace={node.trace_id}{late} · {node.duration_ms}ms"]
    _render_span(node, lines, prefix="", connector="", child_prefix="")
    return "\n".join(lines)


def _render_span(node: LocalSpan, lines: List[str], prefix: str,
                 connector: str, child_prefix: str) -> None:
    duration = f"{node.duration_ms}ms" if node.duration_ms is not None else "…"
    head = f"{node.name} ({node.role} · {duration})"
    if node.error:
        head += f" ✗ {node.error}"
    lines.append(prefix + connector + head)
    detail_prefix = child_prefix + ("│    " if node.children else "     ")
    for row in _detail_rows(node):
        lines.append(detail_prefix + row)
    for i, child in enumerate(node.children):
        last = i == len(node.children) - 1
        _render_span(
            child, lines,
            prefix=child_prefix,
            connector="└─ " if last else "├─ ",
            child_prefix=child_prefix + ("   " if last else "│  "),
        )


def _detail_rows(node: LocalSpan) -> List[str]:
    rows: List[Tuple[str, str]] = []
    for section, data in (("in", node.inputs), ("out", node.outputs),
                          ("meta", node.metadata)):
        if not data:
            continue
        for path, value in _flatten(data):
            rows.append((f"{section}.{path}" if path else section, value))
    if not rows:
        return []
    overflow = len(rows) - _CONSOLE_ROW_LIMIT
    rows = rows[:_CONSOLE_ROW_LIMIT]
    width = max(len(key) for key, _ in rows)
    rendered = [f"{key.ljust(width)} = {value}" for key, value in rows]
    if overflow > 0:
        rendered.append(f"… (+{overflow}줄 — 전문은 JSONL)")
    return rendered


def _flatten(value: Any, path: str = "") -> List[Tuple[str, str]]:
    """중첩 dict를 점 표기 경로의 (key, 짧은 값) 목록으로 편다."""
    out: List[Tuple[str, str]] = []
    if isinstance(value, dict) and value:
        for key, child in value.items():
            out.extend(_flatten(child, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
        for i, child in enumerate(value):
            out.extend(_flatten(child, f"{path}[{i}]"))
    else:
        out.append((path, _short(value)))
    return out


def _short(value: Any) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        rendered = repr(value)
    if len(rendered) > _CONSOLE_VALUE_LIMIT:
        rendered = rendered[:_CONSOLE_VALUE_LIMIT] + "…"
    return rendered
