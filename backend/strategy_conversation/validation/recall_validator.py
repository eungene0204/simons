"""Recall Validator — 입력의 수치가 LLM 출력에 반영됐는지 **대조**한다.

계약상 위치(docs/nl_interpretation_contract.md § 3-1): 이 모듈은 사용자 원문을 읽지만
**해석하지 않는다**. 숫자 토큰이 출력 어딘가에 나타나는지만 확인하고, 그 숫자가 어떤
지표의 임계값인지는 판단하지 않는다. 어떤 경우에도 값을 만들어 채우지 않는다.

동기(2026-07-26 A/B 실측): 결정적 보정을 끄면 "부채비율 80% 이하이고 시가총액 5000억
이상인 종목 중 RSI 35 이하에서 매수" 같은 복합 발화에서 4B가 조건을 통째로 빠뜨린다.
잔여 실패 34건 중 20건이 이 유형이었다.

대응은 2026-08-07에 바뀌었다. 예전에는 누락을 발견하면 LLM에 **재생성을 요청**했는데
(§ 8-1), 전수 실측에서 재요청 62건 중 45건이 아무것도 고치지 못했고(47%는 1차와 바이트
동일 — temperature=0) 고친 17건도 구제 3건 대 훼손 3건이었다. 재요청이 1차보다 더 알던
정보는 '어느 수치가 빠졌나' 목록 하나뿐인데 그 목록은 입력만으로 계산되므로, 지금은
**1차 프롬프트의 체크리스트**로 앞당긴다(input_number_labels → prompts._number_checklist).
탐지 결과는 근거 없는 기간 비우기(drop_ungrounded_condition_periods)와 진단 로그가 쓴다.
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


def input_number_labels(user_input: str) -> List[str]:
    """입력에 등장한 수치 표현 목록(중복 제거, 등장 순서).

    1차 호출 프롬프트에 실을 체크리스트다 — 이 목록을 만드는 데 출력이 필요 없다는 것이
    수치 재요청 폐지의 근거였다(재요청이 1차보다 더 알던 유일한 정보가 이것이었다).
    여기서 하는 일은 숫자 토큰 나열뿐이며, 그 수치가 무엇을 뜻하는지는 판단하지 않는다 —
    귀속은 전부 LLM이 한다(모듈 상단 § 3-1 계약 그대로).
    """
    labels: List[str] = []
    for label, _value, _unit in _input_anchors(user_input):
        if label not in labels:
            labels.append(label)
    return labels


def find_unreflected_numbers(user_input: str, intent) -> List[str]:
    """입력에 있으나 출력 어디에도 나타나지 않는 수치 표현 목록.

    반환값은 **증거**이며, 이 값으로 출력을 고치지 않는다. 소비자는 둘뿐이다 —
    근거 없는 기간 비우기(drop_ungrounded_condition_periods)와 진단 로그.
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


# 조건의 기간 파라미터 — 프롬프트 5-0이 "사용자가 말한 경우에만" 채우라고 계약한 칸들.
_PERIOD_KEYS = ("period", "short_period", "long_period", "lookback_period")


def drop_ungrounded_condition_periods(user_input: str, intent, missing: Iterable[str]) -> List[str]:
    """입력에 근거가 없는 조건 기간 파라미터를 **비운다**(제자리). 반환: 비운 항목 라벨.

    값을 만들어 채우지 않는다 — 이 모듈의 계약(§ 3-1)대로 비우기만 하고, 되묻기는
    completeness_validator가 registry 기본값을 권장값으로 달아 낸다.

    사고(2026-08-07): "60일 신고가"에 9B가 `lookback_period=252`를 냈다(프롬프트 5-1의
    '52주 신고가=252' 예시를 잘못 집었다). 재요청도 같은 값을 반복했고, 검증은 READY·
    미지원 0으로 통과해 사용자가 말한 적 없는 252가 조용히 확정됐다. 프롬프트는 이미
    "기간 언급이 없으면 비워 두세요(되묻기)"를 계약하므로, 여기서는 그 계약을 결정론으로
    강제할 뿐이다.

    판단 입력은 **LLM 출력의 숫자와 입력 숫자의 크기**뿐이다 — 어느 지표인지, 그 수치가
    무엇을 뜻하는지는 보지 않는다(원문 해석 아님). 두 조건을 모두 만족할 때만 비운다:
      ① 그 값이 입력의 어떤 수치로도 환산되지 않는다(_candidates가 단위 환산을 흡수하므로
         '52주 신고가'→252 같은 정당한 변환은 걸리지 않는다).
      ② LLM이 그 조건에 스스로 붙인 source_text에 **미반영 수치**가 들어 있다 — 즉 모델
         자신이 "이 조건은 그 수치에서 나왔다"고 적어 놓고 다른 값을 넣었다.
    ②가 없으면 기간 없는 '골든크로스'에 시스템 정본(5/20)이 들어간 경우까지 비우게 된다.
    """
    strategy = getattr(intent, "strategy", None)
    if strategy is None:
        return []
    missing_values: Set[float] = set()
    for label in missing:
        m = _NUMBER_RE.match(label or "")
        value = _to_float(m.group(1)) if m else None
        if value is not None:
            missing_values.add(value)
    if not missing_values:
        return []

    grounded: Set[float] = set()
    for _label, value, unit in _input_anchors(user_input):
        grounded |= _candidates(value, unit)

    cleared: List[str] = []
    for field in ("entry_conditions", "exit_conditions"):
        for cond in getattr(strategy, field, None) or []:
            params = getattr(cond, "parameters", None)
            if not isinstance(params, dict):
                continue
            quoted = {v for _l, v, _u in _input_anchors(getattr(cond, "source_text", "") or "")}
            if not (quoted & missing_values):
                continue
            for key in _PERIOD_KEYS:
                value = params.get(key)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    continue
                if any(abs(float(value) - g) < _TOLERANCE for g in grounded):
                    continue
                params[key] = None
                cleared.append(f"{field}.{key}={float(value):g}")
    return cleared
