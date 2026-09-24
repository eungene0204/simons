"""Batch independent verdicts, then reuse the original validators and application order."""
from __future__ import annotations

import json

from . import contribution_plan_check as contribution
from . import quote_check, trading_value_check as trading
from .output_repair import extract_json_object

_SYSTEM = """여러 독립적인 전략 검사를 한 번에 수행합니다.
각 checks 항목의 instruction과 input을 따로 읽고 그 검사의 JSON 응답을 같은 키에 넣으세요.
다른 검사의 판정을 복사하거나 전략 자체를 다시 생성하지 마세요.
하위 instruction의 출력 예시보다 여기의 checks 포장과 item_ids 계약이 우선합니다.
items 배열을 반환하는 검사는 각 항목에 id를 추가하세요: '<검사 키>:<입력의 1부터 시작하는 항목 번호>'.
예: quote:1, trading:1. 항목을 합치거나 빠뜨리지 마세요. rules의 인용도 입력 그대로 유지하세요.
출력은 JSON 객체 하나: {"checks":{"quote":{"items":[...]},"trading":{"items":[...]},"contribution":{...}}}.
요청에 없는 검사 키는 출력하지 마세요."""


def _validated_section(name, section, count):
    if not isinstance(section, dict):
        return None
    if name == "contribution":
        if (not {"plan", "rules", "cash_reserve", "max_buy"} <= section.keys()
                or not isinstance(section["rules"], list)
                or not all(isinstance(section[k], dict) for k in ("cash_reserve", "max_buy"))
                or (section["plan"] is not None and not isinstance(section["plan"], dict))):
            return None
        return section
    items = section.get("items")
    if not isinstance(items, list) or len(items) != count:
        return None
    # A single item has an unambiguous identity even if the model omits its ID.
    # Never infer positions for multiple items or override a conflicting explicit ID.
    if count == 1 and isinstance(items[0], dict) and "id" not in items[0]:
        items = [{**items[0], "id": f"{name}:1"}]
    by_id = {item.get("id"): item for item in items
             if isinstance(item, dict) and isinstance(item.get("id"), str)}
    expected = [f"{name}:{i}" for i in range(1, count + 1)]
    if set(by_id) != set(expected):
        return None
    ordered = [by_id[key] for key in expected]
    for item in ordered:
        if name == "quote":
            if (item.get("expresses") not in quote_check.EXPRESSES
                    or item.get("describes") not in quote_check.DESCRIBES):
                return None
        elif item.get("compares") not in trading.COMPARES:
            return None
    return {"items": ordered}


def prepare_chat(intent, user_input, chat, only=None):
    strategy = getattr(intent, "strategy", None)
    if strategy is None or not callable(chat):
        return chat
    requests = {}
    counts = {}
    targets = quote_check.targets_for_intent(intent, user_input, only)
    if targets:
        requests["quote"] = quote_check.build_request(user_input, targets)
        counts["quote"] = len(targets)
    targets = trading.conditions_to_check(strategy, only)
    if targets:
        requests["trading"] = trading.build_request(user_input, targets)
        counts["trading"] = len(targets)
    if contribution.applies_to(intent):
        targets = [c for c in strategy.entry_conditions if c.buy_amount is None and c.source_text
                   and (only is None or any(c is o for o in only))]
        if only is None or targets:
            requests["contribution"] = contribution.build_request(user_input, targets)
            counts["contribution"] = len(targets)
    if len(requests) < 2:
        return chat
    responses = {}
    try:
        from observability import span
        with span("Condition Checks · 통합 조건 판정", "chain"):
            raw = chat(_SYSTEM, json.dumps({"checks": {
                name: {"instruction": system.replace('"items": [{', '"items": [{"id": "' + name + ':1", '), "input": user,
                       "item_ids": [f"{name}:{i}" for i in range(1, counts[name] + 1)]
                       if name != "contribution" else []}
                for name, (system, user, _) in requests.items()
            }}, ensure_ascii=False), max_tokens=sum(r[2] for r in requests.values()) + 256)
        payload = json.loads(extract_json_object(raw))
        sections = payload.get("checks") if isinstance(payload, dict) else None
        if isinstance(sections, dict):
            for name, (system, user, _) in requests.items():
                section = _validated_section(name, sections.get(name), counts[name])
                if section is not None:
                    responses[(system, user)] = json.dumps(section, ensure_ascii=False)
    except Exception:
        # Cancellation is a BaseException and must still stop the entire request.
        pass

    def replay(system, user, **kwargs):
        # Changed inputs and malformed sections use the original individual checker.
        cached = responses.pop((system, user), None)
        return cached if cached is not None else chat(system, user, **kwargs)
    return replay
