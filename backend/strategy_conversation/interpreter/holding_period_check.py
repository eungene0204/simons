"""Check explicit holding-day values in modification patches with an LLM."""

from __future__ import annotations

import json
import math
import re
from typing import Callable

from .models import PatchOp, StrategyIntent
from .output_repair import extract_json_object


_HOLD_PATHS = frozenset({
    "/portfolio/hold_period_days", "/portfolio/min_hold_period_days",
})

_SYSTEM = """당신은 전략 수정 패치의 보유 기간 숫자를 대조합니다. 사용자 발화에서 각 패치의 보유 기간 표현을 짧게 그대로 인용하고, 그 표현에 적힌 숫자 표기와 단위를 옮겨 적으세요. 이동평균 기간이나 다른 설정의 숫자를 보유 기간으로 해석하지 마세요. 명확하지 않으면 quote와 number_text를 null, unit을 unknown으로 답하세요. 계산하거나 날짜를 환산하지 마세요. JSON만 출력하세요: {"items":[{"id":"1","quote":null,"number_text":null,"unit":"unknown"}]}"""

_MISFILED_SYSTEM = """당신은 인용 대조에서 거부된 전략 조건의 원래 요청을 다시 확인합니다. 사용자 발화의 짧은 구절이 '사고 나서 얼마 동안 보유한 뒤 청산'하는 기간을 명시했다면 kind를 max_hold로, '최소 얼마 동안 보유'라면 min_hold로 답하세요. 지표의 계산 기간, 이동평균선, 손절률, 청산 신호만 말했거나 보유 기간의 수량이 명확하지 않으면 kind를 none으로 답하세요. 직전 질문이나 기존 전략의 숫자를 기간 값으로 복사하지 마세요. quote와 number_text는 사용자 발화에서 그대로 짧게 옮겨 적고, count는 그 수량, unit은 day/month/year 중 하나로 쓰세요. 월·년을 거래일로 환산하지 마세요. 여러 기간이 섞여 하나를 특정할 수 없거나 확신이 없으면 none으로 답하세요. JSON만 출력하세요: {"kind":"none","quote":null,"number_text":null,"count":null,"unit":null}"""

_HOLD_UNIT_DAYS = {"day": 1, "month": 21, "year": 252}


def recover_misfiled_holding_period(
    user_input: str, source_text: str, pending_question: str | None,
    chat: Callable,
) -> PatchOp | None:
    """Return a quoted holding patch only when the independent LLM verdict is complete."""
    if not callable(chat) or not source_text or source_text not in user_input:
        return None
    request = {"utterance": user_input, "source_text": source_text,
               "pending_question": pending_question}
    try:
        raw = chat(_MISFILED_SYSTEM, json.dumps(request, ensure_ascii=False), max_tokens=160)
        answer = json.loads(extract_json_object(raw))
        if not isinstance(answer, dict):
            return None
        kind = answer.get("kind")
        quote = answer.get("quote")
        number_text = answer.get("number_text")
        count = answer.get("count")
        unit = answer.get("unit")
        if (kind not in ("max_hold", "min_hold")
                or not isinstance(quote, str) or not quote.strip()
                or quote not in user_input or quote not in source_text
                or not isinstance(number_text, str) or not number_text.strip()
                or number_text not in quote
                or isinstance(count, bool) or not isinstance(count, (int, float))
                or not math.isfinite(count) or count <= 0 or not float(count).is_integer()
                or (number_text.isdecimal() and int(number_text) != int(count))
                or unit not in _HOLD_UNIT_DAYS):
            return None
        written_numbers = re.findall(r"\d+", number_text)
        if written_numbers and (len(written_numbers) != 1
                                or int(written_numbers[0]) != int(count)):
            return None
        days = int(count) * _HOLD_UNIT_DAYS[unit]
        path = ("/portfolio/hold_period_days" if kind == "max_hold"
                else "/portfolio/min_hold_period_days")
        return PatchOp(op="replace", path=path, value=days, source_text=quote)
    except Exception:
        # An invalid or unavailable auxiliary verdict keeps the original result.
        return None


def recover_create_misfiled_holding_period(
    intent: StrategyIntent, user_input: str, chat: Callable,
) -> list[str]:
    """Move one invalid exit into an explicitly quoted holding-period field."""
    from strategy_conversation.registry.indicator_registry import REGISTRY

    strategy = intent.strategy
    if strategy is None or not callable(chat):
        return []
    candidates = [
        (index, condition)
        for index, condition in enumerate(strategy.exit_conditions)
        if condition.factor not in REGISTRY and condition.source_text
        and condition.source_text in user_input
    ]
    if len(candidates) != 1:
        return []
    index, condition = candidates[0]
    patch = recover_misfiled_holding_period(
        user_input, condition.source_text, None, chat)
    if patch is None:
        return []
    field = ("hold_period_days" if patch.path == "/portfolio/hold_period_days"
             else "min_hold_period_days")
    if getattr(strategy.portfolio, field) is not None:
        return []

    setattr(strategy.portfolio, field, patch.value)
    strategy.exit_conditions.pop(index)
    question_paths = (
        f"strategy.exit_conditions[{index}]",
        f"strategy.exit_conditions.{index}",
    )
    intent.clarification_questions = [
        question for question in intent.clarification_questions
        if not any(question.field == path or question.field.startswith(path + ".")
                   for path in question_paths)
    ]
    return [f"청산 조건 '{condition.source_text}'을 보유 기간 {patch.value}거래일로 반영했어요."]


def reconcile_holding_days(
    intent: StrategyIntent, user_input: str, chat: Callable,
) -> StrategyIntent:
    """Correct only an explicit day count; leave every other patch unchanged."""
    targets = [
        (index, patch)
        for index, patch in enumerate(intent.patches)
        if patch.op in ("add", "replace") and patch.path in _HOLD_PATHS
        and isinstance(patch.value, (int, float)) and not isinstance(patch.value, bool)
        and patch.source_text
    ]
    if not targets:
        return intent

    payload = {
        "utterance": user_input,
        "patches": [
            {"id": str(position), "path": patch.path,
             "source_text": patch.source_text, "value": patch.value}
            for position, (_, patch) in enumerate(targets, 1)
        ],
    }
    try:
        raw = chat(_SYSTEM, json.dumps(payload, ensure_ascii=False), max_tokens=192)
        answer = json.loads(extract_json_object(raw))
        items = answer.get("items") if isinstance(answer, dict) else None
        if not isinstance(items, list) or len(items) != len(targets):
            return intent
        by_id = {item.get("id"): item for item in items if isinstance(item, dict)}
        if len(by_id) != len(targets) or set(by_id) != {
            str(position) for position in range(1, len(targets) + 1)
        }:
            return intent

        patches = list(intent.patches)
        changed = False
        for position, (index, patch) in enumerate(targets, 1):
            item = by_id[str(position)]
            quote = item.get("quote")
            number_text = item.get("number_text")
            if (item.get("unit") not in ("day", "일") or not isinstance(quote, str)
                    or not isinstance(number_text, str) or not number_text.isdecimal()
                    or quote not in user_input or quote not in patch.source_text
                    or number_text not in quote):
                continue
            value = int(number_text)
            if value > 0 and value != patch.value:
                patches[index] = patch.model_copy(update={"value": value})
                changed = True
        return intent.model_copy(update={"patches": patches}) if changed else intent
    except Exception:
        # A failed auxiliary check must not discard the original interpretation.
        return intent
