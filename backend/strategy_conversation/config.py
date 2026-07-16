"""전략 대화 파이프라인 설정 — 환경변수로 오버라이드 가능한 운영 파라미터.

confidence는 상태 판정·사용자 노출에 쓰지 않는다(텔레메트리 전용) —
과거의 confidence 임계값 게이트는 "확신이 낮다" 자기회의 문구가 사용자에게
노출되는 사고(2026-07-17)로 제거됐다.
"""

from __future__ import annotations

import os


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


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
