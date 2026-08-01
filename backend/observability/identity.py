"""Trace 식별자 파생 — 백엔드가 이미 가진 값에서만 만든다.

스펙은 user_id·session_id·strategy_id를 요구하지만 **백엔드에는 셋 다 없다**.
전략 대화 API(NLParseRequest)는 무상태 에코 계약이라 사용자·세션 개념을 갖지 않는다.
관찰 계층이 요청 스키마를 늘리는 것은 실행 경로 변경이므로(관찰은 관찰만 한다),
여기서는 **가진 값에서 파생 가능한 것만** 만들고 없는 것은 없다고 표시한다.

파생 규칙:

- ``strategy_id``  = 이 턴이 산출한 전략 State의 내용 해시.
- ``parent_strategy_id`` = 이 턴에 들어온 전략 State(previous_parsed)의 내용 해시.
- ``session_id``  = parent_strategy_id (첫 턴이면 프롬프트 해시).

세 번째 규칙이 대화를 잇는 방법이다: **턴 N의 session_id는 턴 N-1의 strategy_id와
같다.** LangSmith에서 한 대화를 복원하려면 그 사슬을 따라가면 된다. 진짜 세션 키가
아니므로 '한 세션의 모든 턴'을 한 번에 필터할 수는 없다 — 그건 요청 계약에 세션
필드가 생겨야 가능하고, 그때 이 모듈만 바꾸면 된다.

``user_id``는 파생할 근거가 전혀 없으므로 None이다. 없는 값을 그럴듯하게 지어내면
(IP·해시 등) Trace를 신뢰할 수 없게 된다.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

_UNSET = "none"


def content_hash(value: Any) -> Optional[str]:
    """전략 State 등 내용의 안정 해시(12자리). 값이 없으면 None."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:  # noqa: BLE001
            return None
    if isinstance(value, (dict, list)) and not value:
        return None
    try:
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        canonical = repr(value)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def trace_identity(
    prompt: str,
    previous_parsed: Optional[dict],
) -> Dict[str, Optional[str]]:
    """요청 시점에 알 수 있는 식별자(Trace 시작 메타데이터)."""
    parent = content_hash(previous_parsed)
    return {
        "user_id": None,           # 요청 계약에 없음 — 지어내지 않는다
        "session_id": parent or f"new:{content_hash(prompt) or _UNSET}",
        "parent_strategy_id": parent,
        "turn_kind": "modify" if previous_parsed else "create",
    }
