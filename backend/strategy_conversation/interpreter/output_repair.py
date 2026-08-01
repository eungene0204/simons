"""LLM 출력 안정화 — JSON 추출과 1회 자동 수정 요청 프롬프트.

인터프리터 LLM의 출력이 항상 완벽한 JSON이라고 가정하지 않는다. 파싱/검증 실패 시
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
    repaired = _close_unbalanced_containers(text, start)
    if repaired is not None:
        return repaired
    raise ValueError("unbalanced JSON object in model output")


def _close_unbalanced_containers(text: str, start: int) -> Optional[str]:
    """닫는 괄호가 빠진 출력에서 **빠진 닫는 괄호만** 채워 넣는다(실패 시 None).

    9B 드리프트 실측(2026-07-31): 패치 값이 3단 중첩(패치 → 조건 객체 → parameters)이면
    조건 객체의 닫는 중괄호를 빠뜨린다 —
    `"patches":[{"op":"add","path":"/exit_conditions/-","value":{...}], "unsupported_features":[]}`
    (`]` 자리에서 `}`가 하나 모자란다). 이 형태는 위 스캐너가 depth 0으로 돌아오지 못해
    통째로 버려졌고, 1회 복구 요청에도 모델이 같은 위치에서 같은 출력을 냈다(2/2 재현) —
    그 결과 "데드크로스 나오면 팔아" 같은 청산 조건 답변이 전부 해석 실패로 끝났다.

    복구는 **닫는 괄호 삽입뿐**이다. 값·키·구조를 바꾸지 않으므로 의미 해석이 아니라
    형식 정규화이며(계약 § 3-2), 올바른 JSON에는 애초에 도달하지 않는다(위 스캐너가
    먼저 반환하므로 멱등). 짝이 아예 없는 닫는 괄호처럼 삽입만으로 설명되지 않는
    붕괴는 None으로 두어 기존 실패 경로(재요청 → InterpreterError)에 맡긴다.
    """
    stack: list[str] = []
    out: list[str] = []
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        out.append(ch)
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
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            opener = "{" if ch == "}" else "["
            if not stack:
                return None
            if stack[-1] != opener:
                if opener not in stack:
                    return None  # 짝 없는 닫는 괄호 — 삽입으로 설명되지 않는다
                # 이 닫는 괄호의 짝이 스택 깊은 곳에 있다 = 그 사이 컨테이너의 닫는
                # 괄호가 누락된 것이다. 누락분을 이 자리 **앞에** 채운다.
                missing = []
                while stack and stack[-1] != opener:
                    missing.append("}" if stack.pop() == "{" else "]")
                out[-1:] = missing + [ch]
            stack.pop()
            if not stack:
                return "".join(out)
    return None


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
