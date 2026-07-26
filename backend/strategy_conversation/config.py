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


# 수정(modify) 경로의 해석 권한 순서:
#   llm_first(기본)      — LLM 인터프리터가 최초 해석자, 결정론 fast-path는 폴백으로 강등
#   fast_path_first(롤백) — 기존 동작(결정론 fast-path가 인터프리터를 선점)
# 어떤 값이든 fast-path는 살아 있다 — 순서만 바뀐다(롤백 = 이 값을 fast_path_first로).
def modify_interpreter_mode() -> str:
    mode = os.environ.get("STRATEGY_MODIFY_INTERPRETER_MODE", "llm_first").strip().lower()
    return mode if mode in ("llm_first", "fast_path_first") else "llm_first"


# 결정적 프롬프트 보정(_apply_prompt_overrides)의 적용 여부:
#   off(기본) — LLM 해석을 최종 진실로 둔다(자연어 해석 계약 목표 상태)
#   on        — 컴파일 결과를 사용자 원문 기반 결정적 추출로 덮어쓴다(롤백용)
# 2026-07-26 기본값 전환: 계약(docs/nl_interpretation_contract.md § 3)상 원문 정규식은
# 제거 대상이며, 사용자가 "어떤 경우라도 regex가 자연어를 해석하려 해선 안 된다"고 확정했다.
# 합성 코퍼스 A/B는 기대값이 정규식 인코딩 관례를 담고 있어(§ 11-2) 전환 판정 기준으로
# 쓰지 않기로 했고, 이후 개선은 실사용에서 나온 케이스로 진행한다.
def prompt_override_mode() -> str:
    mode = os.environ.get("STRATEGY_PROMPT_OVERRIDE_MODE", "off").strip().lower()
    return mode if mode in ("on", "off") else "off"


def prompt_overrides_enabled() -> bool:
    return prompt_override_mode() == "on"


# 수치 반영 대조(recall_validator) 사용 여부. 누락 감지 시 LLM 재생성 1회를 더 쓰므로
# 지연이 늘 수 있다 — 롤백은 이 값을 off로.
def recall_check_enabled() -> bool:
    return os.environ.get("STRATEGY_RECALL_CHECK", "on").strip().lower() != "off"


def shadow_log_path() -> str:
    return os.environ.get(
        "STRATEGY_INTERPRETER_SHADOW_LOG",
        os.path.join(os.path.dirname(__file__), "..", "logs", "strategy_interpreter_shadow.jsonl"),
    )
