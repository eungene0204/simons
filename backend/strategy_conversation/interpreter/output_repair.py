"""LLM 출력 안정화 — JSON 추출과 1회 자동 수정 요청 프롬프트.

Qwen 3.5 4B의 출력이 항상 완벽한 JSON이라고 가정하지 않는다. 파싱/검증 실패 시
원래 입력·잘못된 출력·Pydantic 오류만 전달해 재생성을 요청한다(무한 재시도 금지).
"""

from __future__ import annotations

import json
import re
from typing import Optional

# 4B 토큰 드리프트 실측(2026-07-16, greedy라 결정적 재현): 비교 연산자 문자열 값에서
# 콜론·따옴표가 붕괴된다 — '"operator":">=","value"' → '"operator">="value"' 또는
# '"operator"><=","value"'. 올바른 JSON에는 no-op(멱등)인 기계적 구문 복구.
_OPERATOR_TOKEN_DRIFT_RE = re.compile(r'"operator"[:\s>]*"?(<=|>=|<|>)"?[,\s]*(?=")')


def _repair_operator_token_drift(text: str) -> str:
    return _OPERATOR_TOKEN_DRIFT_RE.sub(r'"operator":"\1",', text)


def extract_json_object(raw_text: str) -> str:
    """모델 응답에서 첫 번째 최상위 JSON 오브젝트 문자열을 추출한다.

    형식 추출(결정론)이며 의미 해석이 아니다. 실패 시 ValueError.
    """
    # 기존 파서와 동일한 트레일링 토큰 제거를 재사용한다
    from engine.nl_parser import _trim_model_trailing_tokens

    text = _repair_operator_token_drift(_trim_model_trailing_tokens(raw_text).strip())
    if text.startswith("```"):
        # ```json ... ``` 코드펜스 드리프트 제거
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in model output")
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("unbalanced JSON object in model output")


def build_repair_prompt(
    user_input: str,
    bad_output: str,
    error_message: str,
    draft: Optional[dict] = None,
) -> str:
    parts = [
        "직전 출력이 StrategyIntent JSON 스키마 검증에 실패했습니다. "
        "오류를 수정한 완전한 JSON 하나만 다시 출력하세요(설명 금지).",
        f"\n## 원래 사용자 입력\n\"{user_input}\"",
    ]
    if draft:
        parts.append(f"\n## 현재 전략 초안\n{json.dumps(draft, ensure_ascii=False)}")
    parts.append(f"\n## 잘못된 출력\n{bad_output[:2000]}")
    parts.append(f"\n## 검증 오류\n{error_message[:2000]}")
    return "\n".join(parts)
