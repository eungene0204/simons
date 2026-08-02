"""관찰(Observability) 계층 — Agent 실행을 추적만 하고 제어하지 않는다.

이 패키지는 전략 대화 Agent(Planner → Action DAG → Tool → State → Responder)의
실행 과정을 Trace로 남긴다. **어떤 실행 경로도 바꾸지 않는다** —
분기·되묻기 조건·폴백 판정·반환값·예외 전파는 전부 기존 코드 소관이며, 이 계층은
읽기만 한다.

기록처는 둘이다:
- LangSmith(외부 전송) — LANGSMITH_TRACING 미설정이 기본이며 그때는 langsmith를
  import조차 하지 않는다.
- 로컬(local_trace) — 콘솔 트리 + logs/agent_traces/*.jsonl. 외부 전송이 없으므로
  기본 켜짐이고, AGENT_TRACE_LOCAL=0으로 끈다.
"""

from observability.metrics import current_metrics, record_duration  # noqa: F401
from observability.tracing import (  # noqa: F401
    TraceHandle,
    current_parent,
    span,
    tracing_enabled,
    use_parent,
)
