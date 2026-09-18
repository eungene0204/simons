"""거래대금 비교 대상 대조 — "이 거래대금 인용은 금액과 비교하나, 자기 평균과 비교하나"를 LLM에게 묻는다.

왜 필요한가(2026-09-18 실측, nemotron-120b): '최근 거래대금이 30일 평균보다 높은'을 인터프리터가 4회 중
1회 평균 기간 없이 `fundamental.trading_value`(값 없음)로 냈다. 그 형태는 "금액 기준을 아직 말하지 않은
거래대금 조건"과 구별되지 않아, 시스템이 "일평균거래대금 기준값을 몇 억으로 할까요?"라는 엉뚱한 질문을
냈다. 형태로 가를 수 없는 것은 의미이므로 LLM이 판정한다(대원칙 1). 평균 기간이 실린 형태는 검증기가
출력 형태만 보고 거래대금 배수로 옮기므로(capability_validator) 여기 대상이 아니다.

결정론 코드의 몫: ① 대상 조건 고르기(LLM 출력 필드의 형태) ② 응답이 정해진 enum·숫자 범위인지 확인
③ 판정에 따라 지표를 옮기고 LLM이 옮겨 적은 기간·배수·부등호를 싣기. 인용 문자열은 읽지 않는다.

실패 동작: 호출 오류·JSON 불성립·항목 수 불일치·enum 밖·"unclear"는 판정 없음 — 조건을 그대로 둔다
(fail-open, 조건 인용 대조와 같은 원칙). 그때는 종전대로 금액 기준값을 되묻는다(조용한 대체는 없다).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

TRADING_VALUE_FACTORS = ("fundamental.trading_value", "technical.trading_value")
RATIO_FACTOR = "technical.trading_value_ratio"

COMPARES = frozenset({"amount", "own_average", "unclear"})
OPERATORS = frozenset({">", ">=", "<", "<="})

_SYSTEM = """당신은 **대조기**입니다. 전략 문장에서 뽑은 거래대금 조건의 인용 조각마다, 거래대금을 무엇과 비교하는지 답하세요.

compares — 억 원·달러 같은 금액 기준과 비교하면 "amount", 그 종목의 과거 평균 거래대금과 비교하면 "own_average", 판단이 어려우면 "unclear".
"일평균 거래대금이 높은"·"최근 20일 평균 거래대금이 많은"처럼 평균 거래대금 자체가 많다·높다고만 말하면 평균과 비교하는 것이 아니라 거래대금 수준을 말하는 것이므로 "amount"입니다. "평균보다"·"평균의 N배"·"평균을 넘으면"·"평소보다"처럼 평균을 비교 상대로 삼을 때만 "own_average"입니다.
own_average일 때만 아래 세 값을 인용에 적힌 그대로 옮겨 적습니다(인용에 없으면 null).
average_days — 평균 기간을 일(日) 수로 말했으면 그 숫자("30일 평균" → 30).
multiple — 평균의 몇 배인지("2배 이상" → 2). 배수 없이 평균보다 높다·낮다만 말했으면 1.
operator — 평균보다 높으면 ">", 이상이면 ">=", 낮으면 "<", 이하면 "<=".

출력 형식(JSON만, 항목 순서대로):
{"items": [{"compares": "own_average", "average_days": 30, "multiple": 1, "operator": ">"}]}"""


@dataclass(frozen=True)
class Verdict:
    compares: Optional[str]
    average_days: Optional[int]
    multiple: Optional[float]
    operator: Optional[str]


def build_system_prompt() -> str:
    return _SYSTEM


def _canonical_factor(factor: Optional[str]) -> Optional[str]:
    from strategy_conversation.registry.indicator_registry import REGISTRY

    spec = REGISTRY.get(factor) if factor else None
    return spec.id if spec is not None else factor


def conditions_to_check(strategy: Any, only: Optional[List[Any]] = None) -> List[Any]:
    """물어볼 조건 — 인용이 있고, 금액도 평균 기간도 없는 거래대금 조건만."""
    targets: List[Any] = []
    for role in ("entry_conditions", "exit_conditions"):
        for cond in getattr(strategy, role):
            if only is not None and not any(cond is c for c in only):
                continue
            if (_canonical_factor(cond.factor) in TRADING_VALUE_FACTORS and cond.source_text
                    and cond.value is None
                    and (cond.parameters or {}).get("period") is None):
                targets.append(cond)
    return targets


def _int_in(value: Any, low: int, high: int) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() and low <= number <= high else None


def _float_in(value: Any, low: float, high: float) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def check_trading_value_quotes(
    user_input: str, targets: List[Any], chat: Callable[..., str],
) -> Optional[List[Tuple[Any, Verdict]]]:
    """조건마다 비교 대상 판정을 받는다. 실패는 None(fail-open)."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object
    from strategy_conversation.registry.indicator_registry import REGISTRY

    if not targets:
        return []
    ratio = REGISTRY[RATIO_FACTOR]
    period_spec = ratio.parameters["period"]
    low_multiple, high_multiple = ratio.value_range
    rows = "\n".join(f'{i}. 인용: "{cond.source_text}"' for i, cond in enumerate(targets, 1))
    with span("Trading Value Check · 거래대금 비교 대상 대조", "chain",
              inputs={"quotes": [c.source_text for c in targets]}) as trace:
        try:
            raw = chat(_SYSTEM, f"[전략 문장]\n{user_input}\n\n[거래대금 조건]\n{rows}",
                       max_tokens=64 + 48 * len(targets))
            payload = json.loads(extract_json_object(raw))
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list) or len(items) != len(targets):
                raise ValueError(f"항목 수 불일치: {len(targets)}개 요청")
        except Exception as exc:  # noqa: BLE001 — 보조 판정이 턴을 깨지 않는다(fail-open)
            logger.warning("trading value check failed — no verdicts | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        pairs: List[Tuple[Any, Verdict]] = []
        for cond, item in zip(targets, items):
            item = item if isinstance(item, dict) else {}
            compares = item.get("compares")
            operator = item.get("operator")
            pairs.append((cond, Verdict(
                compares=compares if compares in COMPARES else None,
                average_days=_int_in(item.get("average_days"),
                                     int(period_spec.minimum), int(period_spec.maximum)),
                multiple=_float_in(item.get("multiple"), low_multiple, high_multiple),
                operator=operator if operator in OPERATORS else None,
            )))
        trace.output(verdicts=[
            {"quote": c.source_text, "compares": v.compares, "average_days": v.average_days,
             "multiple": v.multiple, "operator": v.operator}
            for c, v in pairs
        ])
        return pairs


def apply_verdicts(pairs: Optional[List[Tuple[Any, Verdict]]]) -> List[Any]:
    """자기 평균 비교로 판정된 조건을 거래대금 배수로 옮긴다. 옮긴 조건 목록을 돌려준다.

    LLM이 옮겨 적은 값만 싣는다 — 기간이 없으면 비워 두고(표준 기간, 프롬프트 규칙 5-0과 같은 계약),
    배수가 없으면 값-대기로 남아 되묻는다. 부등호가 없으면 인터프리터가 낸 부등호를 쓴다."""
    moved: List[Any] = []
    for cond, verdict in pairs or []:
        if verdict.compares != "own_average":
            continue
        cond.factor = RATIO_FACTOR
        cond.unit = "ratio"
        if verdict.average_days is not None:
            cond.parameters = {**(cond.parameters or {}), "period": float(verdict.average_days)}
        if verdict.multiple is not None:
            cond.value = verdict.multiple
            cond.value_source = "USER_PROVIDED"
        if verdict.operator is not None:
            cond.operator = verdict.operator
        elif cond.operator not in OPERATORS:
            cond.operator = ">"
        moved.append(cond)
    return moved
