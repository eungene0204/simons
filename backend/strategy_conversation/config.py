"""전략 대화 파이프라인 설정 — 환경변수로 오버라이드 가능한 운영 파라미터.

confidence 임계값은 절대 정확도가 아니라 '되묻기 유도' 신호로만 쓴다
(높아도 Schema/Capability 검증은 생략하지 않는다).
"""

from __future__ import annotations

import os


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# confidence >= FINALIZE: 정상 검증 절차 후 확정 가능
# MIN_ACCEPT <= confidence < FINALIZE: 검증 후 확인 질문
# confidence < MIN_ACCEPT: 전략 확정 금지, 의미 확인 필요
CONFIDENCE_MIN_FINALIZE = _env_float("STRATEGY_INTERPRETER_CONF_FINALIZE", 0.85)
CONFIDENCE_MIN_ACCEPT = _env_float("STRATEGY_INTERPRETER_CONF_ACCEPT", 0.60)

# LLM 출력 복구 재시도 횟수(무한 재시도 금지)
MAX_REPAIR_ATTEMPTS = int(_env_float("STRATEGY_INTERPRETER_MAX_REPAIRS", 1))

# 운영 모드: off(기본) / shadow(기존 파서와 병행 실행 + diff 로그) / primary(Phase 2)
def interpreter_mode() -> str:
    return os.environ.get("STRATEGY_INTERPRETER_MODE", "off").strip().lower()


def shadow_log_path() -> str:
    return os.environ.get(
        "STRATEGY_INTERPRETER_SHADOW_LOG",
        os.path.join(os.path.dirname(__file__), "..", "logs", "strategy_interpreter_shadow.jsonl"),
    )
