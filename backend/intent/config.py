"""의도 분류 레인 설정.

기본값은 계약(CLAUDE.md 자연어 해석 구조 원칙) 준수 레인이다 —
원문의 의미는 LLM만 해석하고, 정규식은 LLM 출력의 형식만 다룬다.

legacy는 원문 정규식이 의미를 먼저 판정하던 이전 레인으로, 계약 위반 상태이며
롤백 경로로만 보존한다(코드 삭제 아님·사용 중지 — strategy_conversation의
interpreter_mode와 같은 이관 관례). 기본값으로 되돌리지 않는다.
"""

from __future__ import annotations

import os


def classifier_mode() -> str:
    """'contract'(기본) | 'legacy'(롤백 — 원문 정규식 레인)."""
    mode = os.environ.get("INTENT_CLASSIFIER_MODE", "contract").strip().lower()
    return mode if mode in ("contract", "legacy") else "contract"
