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
# 앞보기는 **다음 키의 시작**("+영문자)이어야 한다 — '"'만 보면 operator가 객체의 마지막 키일 때
# ('"operator":">"}') 닫는 따옴표를 다음 키로 오인해 멀쩡한 JSON을 '"operator":">","}'로 깨뜨렸다
# (2026-09-18, 거래대금 비교 대상 대조의 출력 형태에서 드러남).
_OPERATOR_TOKEN_DRIFT_RE = re.compile(r'"operator"[:\s>]*"?(<=|>=|<|>)"?[,\s]*(?="[A-Za-z_])')


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


def _salvage_array(raw_text: str, key: str) -> list:
    """깨진 원출력에서 `"<key>": [...]` 배열 하나만 형식 추출한다(실패 시 빈 리스트).

    스키마 검증은 호출부가 한다 — 여기서는 배열 경계만 추출한다.
    """
    quoted = f'"{key}"'
    pos = raw_text.find(quoted)
    if pos == -1:
        return []
    start = raw_text.find("[", pos + len(quoted))
    if start == -1:
        return []
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(raw_text)):
        ch = raw_text[i]
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
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(raw_text[start:i + 1])
                except json.JSONDecodeError:
                    return []
                return parsed if isinstance(parsed, list) else []
    return []


def salvage_clarification_questions(raw_text: str) -> list:
    """깨진 원출력에서 `clarification_questions` 배열만 형식 추출한다(실패 시 빈 리스트).

    수리 재요청이 원출력의 질문 목록을 통째로 비워 내는 드리프트 실측(2026-08-10):
    익절 질문에 "리스크 관리"라는 값 없는 답이 오자 9B가 take_profit 패치에 자기 의심
    질문("익절 기준을 의미하는 것인가요?")을 병행했는데, 첫 출력이 절단돼 수리가 돌았고
    수리본은 패치만 남기고 질문을 지웠다 — 자기 의심 패치 게이트가 볼 신호가 사라져
    지어낸 값이 그대로 확정됐다. 두 조각 모두 LLM 출력이므로 이 복원은 해석이 아니라
    형식 추출·결정적 병합이다(수정 RAG의 목록형 필드 소실 방지 병합과 같은 원칙).
    """
    return _salvage_array(raw_text, "clarification_questions")


def salvage_unsupported_features(raw_text: str) -> list:
    """깨진 원출력에서 `unsupported_features`의 문자열 항목만 형식 추출한다.

    수리 재요청이 원출력의 미지원 목록을 비워 내는 드리프트 실측(2026-09-20, 120B):
    "최근 3년 연속 배당을 지급한 기업만 선별하고"를 1차가 미지원으로 정확히 신고했는데
    시장 국면 필터를 객체 대신 배열로 내 스키마 검증에 걸렸고, 수리본은 미지원 목록을
    `[]`로 냈다 — 수리 프롬프트가 "삭제하지 말라"고 해도 지키지 않는다. 그 결과 사용자
    조건 하나가 안내도 없이 사라졌다. 질문 복원과 같은 형식 추출·결정적 병합이다.
    """
    return [
        item.strip() for item in _salvage_array(raw_text, "unsupported_features")
        if isinstance(item, str) and item.strip()
    ]


def echoes_whole_input(text: Optional[str], user_input: Optional[str]) -> bool:
    """LLM 출력 문자열이 사용자 입력 **전체**와 표기상 같은가(공백·대소문자 정규화 후 동일).

    LLM 출력과 입력의 문자열 대조다 — 원문의 의미를 읽지 않는다(계약 § 3-1).
    """
    from engine.nl_parser import _compact

    compact_input = _compact(user_input or "")
    return bool(compact_input) and _compact(text or "") == compact_input


def extracted_other_slots(strategy) -> bool:
    """같은 출력이 조건 말고 다른 칸(유니버스·랭킹·포트폴리오·리스크·백테스트)도 채웠는가.

    출력 필드의 값 존재만 본다(기본값과 다른 필드가 하나라도 있는가) — 원문을 읽지 않는다.
    """
    if strategy.ranking:
        return True
    return any(
        section.model_dump(exclude_defaults=True)
        for section in (strategy.universe, strategy.portfolio,
                        strategy.risk_management, strategy.backtest)
    )


def whole_input_quote_fields(intent, user_input: Optional[str]) -> list:
    """source_text에 입력 전체를 담은 조건의 필드 경로 목록(형식 위반).

    프롬프트 규칙 4는 source_text를 **그 조건을 말한 원문 조각**으로 정한다. 같은 출력이
    다른 칸(랭킹·종목 수·손절·기간·자본·유니버스 등)까지 뽑아냈다면 입력에는 그 조건 말고도
    다른 말이 있다는 뜻이므로, 입력 전체는 조각이 아니다 — 출처 주장이 성립하지 않는다
    (2026-09-17 실측: 120B가 전체 문장을 인용으로 단 ma_crossover 매수 조건을 지어냈다).
    다른 칸이 비어 있으면(조건 하나뿐인 입력 "PER 10 이하") 입력 전체가 곧 정당한 조각이라
    위반이 아니다(사용자 결정 2026-09-17 (a) — 출력 필드끼리의 구조 대조만 한다).
    """
    strategy = getattr(intent, "strategy", None)
    if strategy is None or not extracted_other_slots(strategy):
        return []
    return [
        f"strategy.{role}[{index}].source_text"
        for role in ("entry_conditions", "exit_conditions")
        for index, cond in enumerate(getattr(strategy, role))
        if cond.source_text and echoes_whole_input(cond.source_text, user_input)
    ]


def whole_input_quote_error(fields: list) -> str:
    """형식 위반을 LLM에 되돌려줄 검증 오류 문구(build_repair_prompt의 error_message)."""
    return "\n".join(
        f"{path}: 입력 문장 전체를 담았습니다. source_text는 그 조건을 말한 입력 조각이어야 "
        "합니다(규칙 4). 그 조건을 말한 조각이 입력에 없으면 그 조건을 출력하지 마세요."
        for path in fields
    )


def is_bare_unsupported_request(intent) -> bool:
    """무엇이 지원되지 않는지 적지 않은 UNSUPPORTED_REQUEST인가(형식 위반).

    라벨은 '지원하지 않는 것이 있다'고 주장하는데 그 내용(unsupported_features)도 전략 골격도
    없다 — 이 출력으로는 시스템이 사용자에게 무엇이 안 되는지 말해 줄 수 없고 턴이 "해석하지
    못했어요"로 끝난다(2026-09-20 실측: 120B가 미지원 개념이 대부분인 퀀트 전략 서술에
    `{"intent": "UNSUPPORTED_REQUEST"}` 11토큰만 냈다, temperature=0 재현). 출력 필드의
    값 존재만 본다 — 원문을 읽지 않는다.
    """
    return (
        getattr(intent, "intent", None) == "UNSUPPORTED_REQUEST"
        and getattr(intent, "strategy", None) is None
        and not getattr(intent, "unsupported_features", None)
    )


def bare_unsupported_request_error() -> str:
    """빈 UNSUPPORTED_REQUEST를 LLM에 되돌려줄 검증 오류 문구(build_repair_prompt의 error_message).

    문장 통째 나열을 막는 두 번째 줄은 실측으로 넣었다 — 없으면 120B가 입력의 모든 문장을
    unsupported_features에 그대로 옮기고 옮길 수 있는 설정(주기·비중·체결 시점·수수료)까지 버린다.
    """
    return (
        "intent: UNSUPPORTED_REQUEST를 냈지만 unsupported_features가 비어 있습니다 — 무엇이 "
        "지원되지 않는지 적지 않은 UNSUPPORTED_REQUEST는 허용되지 않습니다.\n"
        "- 입력이 전략 서술이면 intent는 CREATE_STRATEGY입니다. 출력 형식의 필드로 옮길 수 있는 "
        "표현(종목 수·비중 방식·리밸런싱 주기·체결 시점·수수료·손절 등)은 strategy의 해당 필드에 "
        "값으로 채우고, 옮길 수 없는 개념만 그 개념을 말한 짧은 입력 조각으로 "
        "unsupported_features에 하나씩 적으세요(문장 통째 금지, 필드에 반영한 표현은 다시 넣지 "
        "않음).\n"
        "- 입력이 종목추천·시장전망 등 역할 밖 행위 요청이면 그 행위를 unsupported_features에 "
        "적으세요."
    )


def build_repair_prompt(
    user_input: str,
    bad_output: str,
    error_message: str,
    draft: Optional[dict] = None,
) -> str:
    parts = [
        "직전 출력이 StrategyIntent JSON 스키마 검증에 실패했습니다. "
        "오류를 수정한 완전한 JSON 하나만 다시 출력하세요(설명 금지). "
        "형식·스키마 오류만 고치세요 — 잘못된 출력에 이미 담긴 내용"
        "(patches, clarification_questions, unsupported_features)을 삭제하거나 "
        "바꾸지 마세요.",
        f"\n## 원래 사용자 입력\n\"{user_input}\"",
    ]
    if draft:
        parts.append(f"\n## 현재 전략 초안\n{json.dumps(draft, ensure_ascii=False)}")
    parts.append(f"\n## 잘못된 출력\n{bad_output[:2000]}")
    parts.append(f"\n## 검증 오류\n{error_message[:2000]}")
    return "\n".join(parts)
