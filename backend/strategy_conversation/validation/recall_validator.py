"""Recall Validator — 입력의 수치가 LLM 출력에 반영됐는지 **대조**한다.

계약상 위치(docs/nl_interpretation_contract.md § 3-1): 이 모듈은 사용자 원문을 읽지만
**해석하지 않는다**. 숫자 토큰이 출력 어딘가에 나타나는지만 확인하고, 그 숫자가 어떤
지표의 임계값인지는 판단하지 않는다. 누락을 발견했을 때 할 수 있는 유일한 동작은
LLM에 재생성을 요청하는 것이다(§ 8-1) — 값을 만들어 채우지 않는다.

동기(2026-07-26 A/B 실측): 결정적 보정을 끄면 "부채비율 80% 이하이고 시가총액 5000억
이상인 종목 중 RSI 35 이하에서 매수" 같은 복합 발화에서 4B가 조건을 통째로 빠뜨린다.
잔여 실패 34건 중 20건이 이 유형이었다. 원문 정규식으로 값을 **채우는** 대신, 빠졌다는
사실만 감지해 모델에게 다시 시킨다.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Set

# 숫자 + 뒤따르는 단위(있으면). 콤마 구분 허용. 복합 단위(천만·백만·십만)는 단일 단위보다
# 먼저 매칭해야 한다 — "5천만원"이 "5천"(5,000)으로 잘려 정당한 5천만(5e7) 패치가 환각
# 게이트에서 자릿수 모순으로 거부되던 실측(2026-08-02 감사 #3 C1-T6).
_NUMBER_RE = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(조|억|천만|백만|십만|만|천|퍼센트|%|일|주|개월|년|종목|개)?")

# 6자리 종목코드는 universe.symbols에 문자열로 담기므로 수치 대조 대상이 아니다.
_SYMBOL_CODE_RE = re.compile(r"^\d{6}$")

_TOLERANCE = 1e-6


def _to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _candidates(value: float, unit: str | None) -> Set[float]:
    """같은 수치가 출력에서 취할 수 있는 표현들. 의미 판단이 아니라 **단위 환산**이다."""
    out = {value}
    if unit == "조":
        # 맨값은 후보에서 뺀다 — "1조"의 1이 출력의 무관한 1(종목수·기간 등)과 우연히 맞아
        # 누락을 못 잡던 미탐 실측(2026-07-26: 시총 1조 → 100000억 오변환이 통과).
        out.discard(value)
        out.add(value * 10_000)        # 억원 단위 필드(시가총액·거래대금)
        out.add(value * 1_0000_0000_0000)
    elif unit == "억":
        out.add(value * 100_000_000)   # 원 단위 필드(초기 자본금)
    elif unit == "천만":
        out.add(value * 10_000_000)
    elif unit == "백만":
        out.add(value * 1_000_000)
    elif unit == "십만":
        out.add(value * 100_000)
    elif unit == "만":
        out.add(value * 10_000)
    elif unit == "천":
        out.add(value * 1_000)
    elif unit == "주":
        out.add(value * 5)             # 거래일 환산(52주=260, 계약상 252도 허용)
        out.add(value * 5 - 8)
    elif unit == "개월":
        out.add(value * 21)
    elif unit == "년":
        out.add(value * 252)
        out.add(value * 12)
    return out


def _collect_numbers(node: Any, acc: Set[float]) -> None:
    """출력 트리에서 사용된 모든 수치를 모은다(어느 필드인지는 보지 않는다)."""
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        acc.add(float(node))
    elif isinstance(node, str):
        for m in _NUMBER_RE.finditer(node):
            v = _to_float(m.group(1))
            if v is not None:
                acc.add(v)
    elif isinstance(node, dict):
        for value in node.values():
            _collect_numbers(value, acc)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_numbers(item, acc)


def _reflected_numbers(intent) -> Set[float]:
    """반영으로 인정하는 출력 영역의 수치 집합.

    source_text와 assumptions는 제외한다 — 둘 다 자유 서술이라 포함시키면 '조건은 버렸지만
    말로는 언급했다'가 반영으로 둔갑해 검사가 무력해진다(실측 2026-07-26: 거래대금 조건을
    조건 배열이 아니라 assumptions="거래대금 300억 이상은 종목 선정 기준으로 해석하여
    적용함"에 서술하고 빠져나갔다). unsupported_features는 포함한다 — '표현할 수 없다'는
    정당한 처리 결과이고 하류에 안내 채널이 정해져 있다.

    clarification_questions도 제외한다(2026-07-27). 이 검사가 대조하는 수치는 **입력에 이미
    있는** 값이라 그것을 되묻는 것은 처리가 아니며, 검증 파이프라인은 READY 상태에서 LLM
    자체 질문을 전부 폐기한다(pipeline.py — 잉여·자기회의 질문 차단) — 하류 채널이 없다.
    실측 사고: "일평균 거래대금 50억 원 이상"을 조건 대신 "추가해 드릴까요?" 질문 +
    recommended_value로 돌려주자 검사는 반영으로 인정하고 질문은 폐기돼 조건이 사라졌다.
    """
    dumped = intent.model_dump()
    strategy = dumped.get("strategy") or {}
    for path in ("entry_conditions", "exit_conditions", "ranking"):
        for cond in strategy.get(path) or []:
            cond.pop("source_text", None)
    # 패치의 source_text도 같은 이유로 제외한다(2026-07-31). 인용문은 사용자 원문 조각이라
    # 항상 입력의 숫자를 포함한다 — 값이 틀려도 인용이 대신 대조를 통과시킨다. 실측:
    # "3억원" 답변에 9B가 `value=30000000`(10배 오차) + `source_text="3억원"`을 내자
    # 인용의 3이 앵커 3과 맞아 검사가 통과, 3천만원이 조용히 확정됐다.
    patches = dumped.get("patches") or []
    for patch in patches:
        if isinstance(patch, dict):
            patch.pop("source_text", None)

    acc: Set[float] = set()
    _collect_numbers(strategy, acc)
    _collect_numbers(patches, acc)
    _collect_numbers(dumped.get("unsupported_features"), acc)
    return acc


def _input_anchors(user_input: str) -> List[tuple[str, float, str | None]]:
    anchors: List[tuple[str, float, str | None]] = []
    for m in _NUMBER_RE.finditer(user_input or ""):
        raw, unit = m.group(1), m.group(2)
        if _SYMBOL_CODE_RE.match(raw.replace(",", "")):
            continue
        value = _to_float(raw)
        if value is None:
            continue
        anchors.append((f"{raw}{unit or ''}", value, unit))
    return anchors


def find_unreflected_numbers(user_input: str, intent) -> List[str]:
    """입력에 있으나 출력 어디에도 나타나지 않는 수치 표현 목록.

    반환값은 재생성 요청에 실을 **증거**이며, 이 값으로 출력을 고치지 않는다.
    """
    reflected = _reflected_numbers(intent)
    if not reflected and not _input_anchors(user_input):
        return []

    missing: List[str] = []
    for label, value, unit in _input_anchors(user_input):
        # 부호는 대조 대상이 아니다 — "CCI가 -100 밑으로"의 앵커는 100이고 출력은 -100이다.
        # 어느 쪽이 맞는지는 의미 판단이므로 여기서 하지 않는다(크기만 대조).
        cands = _candidates(value, unit)
        if any(
            any(abs(c - abs(r)) < _TOLERANCE for r in reflected)
            for c in cands
        ):
            continue
        if label not in missing:
            missing.append(label)
    return missing


def labels_absent_from(labels: Iterable[str], payload: Any) -> List[str]:
    """수치 표현 라벨 중 payload(최종 전략 dump) 어디에도 나타나지 않는 것만 남긴다.

    인터프리터 단계의 미반영 목록을 **컴파일·결정적 보정까지 끝난 결과**로 다시 걸러,
    이미 되살아난 값까지 "반영하지 못했다"고 알리는 모순을 막는다.
    """
    reflected: Set[float] = set()
    _collect_numbers(payload, reflected)
    remaining: List[str] = []
    for label in labels:
        m = _NUMBER_RE.match(label or "")
        value = _to_float(m.group(1)) if m else None
        if value is None:
            continue
        if any(
            any(abs(c - abs(r)) < _TOLERANCE for r in reflected)
            for c in _candidates(value, m.group(2))
        ):
            continue
        remaining.append(label)
    return remaining


def build_recall_repair_prompt(
    user_input: str,
    missing: Iterable[str],
    bad_output: str,
    draft: Any = None,
) -> str:
    """누락 수치 재요청 프롬프트. draft가 있으면 수정 턴(patches 형식 유지)이다.

    출력 형식을 명시하지 않으면 모델이 수정 턴처럼 patches만(strategy=null) 돌려주고,
    초기 파스에서는 적용할 초안이 없어 정상 해석이 통째로 버려진다(실측 2026-07-27).
    """
    listed = ", ".join(f"'{m}'" for m in missing)
    if draft is not None:
        form_rule = (
            "직전 출력과 같은 수정 형식을 유지하세요 — 누락된 조건을 patches에 추가하고 "
            "strategy는 null로 둡니다.\n\n"
        )
    else:
        form_rule = (
            "직전 출력의 strategy를 통째로 다시 담으세요 — 유니버스·진입·청산·랭킹·포트폴리오·"
            "리스크 설정을 하나도 빠뜨리지 않고 그대로 유지한 뒤 누락된 조건만 더합니다. "
            "intent는 CREATE_STRATEGY, patches는 빈 배열입니다. **strategy를 null로 두거나 "
            "patches만 돌려주면 직전 해석 전체가 버려집니다.**\n"
            "누락된 조건은 직접 추가하세요 — 예를 들어 '거래대금 50억 이상'이 빠졌다면 "
            'entry_conditions에 {"factor": "fundamental.trading_value", "operator": ">=", '
            '"value": 50, "unit": "억원", "source_text": "거래대금 50억 이상"}을 넣습니다. '
            "'~를 추가해 드릴까요?'·'~를 사용하시겠습니까?'처럼 질문으로 돌려주거나 "
            "assumptions에 '추가해야 합니다'라고 적으면 그 조건은 사라집니다.\n\n"
        )
    return (
        "직전 출력에서 사용자가 말한 수치 일부가 반영되지 않았습니다. "
        f"반영되지 않은 표현: {listed}\n\n"
        + form_rule
        + "해당 수치가 가리키는 조건을 빠짐없이 포함한 완전한 JSON 하나만 다시 출력하세요"
        "(설명 금지). assumptions에 '종목 선정 기준으로 처리했다'처럼 말로 적는 것은 "
        "반영이 아닙니다 — 조건 배열(entry_conditions·exit_conditions·ranking)이나 "
        "portfolio·risk_management의 실제 항목으로 넣으세요. 사용자가 값을 이미 말한 조건은 "
        "clarification_questions·missing_fields로 미루지 마세요 — 되묻기는 값이 실제로 비었을 "
        "때만이고, 그렇게 미룬 조건은 사용자에게 전달되지 않고 사라집니다. 시스템이 표현할 수 "
        "없는 개념이면 그 원문 표현을 unsupported_features에 넣으세요 — 조용히 생략하지 마세요.\n\n"
        f"## 원래 사용자 입력\n\"{user_input}\"\n\n"
        f"## 직전 출력\n{bad_output[:2000]}"
    )
