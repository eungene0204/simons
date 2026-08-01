"""관찰(Observability) 계층 — Agent 실행을 추적만 하고 제어하지 않는다.

이 패키지는 전략 대화 Agent(Planner → Action DAG → Tool → State → Responder)의
실행 과정을 LangSmith Trace로 남긴다. **어떤 실행 경로도 바꾸지 않는다** —
분기·되묻기 조건·폴백 판정·반환값·예외 전파는 전부 기존 코드 소관이며, 이 계층은
읽기만 한다.

비활성(LANGSMITH_TRACING 미설정)이 기본값이다. 비활성일 때는 langsmith를
import조차 하지 않는다.
"""

from observability.metrics import current_metrics, record_duration  # noqa: F401
from observability.tracing import (  # noqa: F401
    TraceHandle,
    current_parent,
    span,
    tracing_enabled,
    use_parent,
)
