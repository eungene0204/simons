"""전략 대화 LLM-first 아키텍처 (Phase 1: Shadow Mode).

사용자 자연어 → LLM Strategy Interpreter → StrategyIntent(JSON)
→ 검증 계층(Schema/Capability/Parameter/Conflict/Completeness)
→ Strategy Compiler → ParsedStrategy(기존 내부 DSL) → 백테스트 엔진.

설계 원칙: LLM은 자연어 이해를, 결정론 코드는 검증·컴파일·실행을 담당한다.
Regex는 자연어 의미 해석에 쓰지 않는다(숫자/날짜/형식 정규화만 허용).

Phase 1에서는 기존 규칙 파서 경로를 건드리지 않고, STRATEGY_INTERPRETER_MODE=shadow
일 때 신규 파이프라인을 병행 실행해 diff를 로그로 남긴다(shadow.py).
"""

from strategy_conversation.interpreter.models import StrategyIntent  # noqa: F401
