"""Classify a dependent condition add/remove pair without reading raw words in code."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from .output_repair import extract_json_object


_SYSTEM = """사용자 발화가 기존 조건을 새 조건으로 교체하는지, 기존 조건은 두고 새 조건을 추가하는지 판정하세요. 패치 자체의 add/remove 연산을 정답으로 믿지 말고 사용자 발화와 직전 질문을 읽으세요. 명확하지 않으면 unclear로 답하세요. quote는 판단 근거인 사용자 발화의 짧은 조각을 그대로 인용하세요. JSON만 출력하세요: {"items":[{"id":"1","action":"unclear","quote":null}]}"""


def classify_condition_pair(
    user_input: str, pending_question: Optional[str], list_field: str,
    old_condition: Any, new_condition: Any, new_quote: str, chat: Callable,
) -> Optional[str]:
    """Return replace/add only for a valid quoted LLM verdict; otherwise None."""
    if not callable(chat) or not new_quote:
        return None
    request = {
        "utterance": user_input,
        "pending_question": pending_question,
        "condition_list": list_field,
        "existing_condition": old_condition,
        "proposed_condition": new_condition,
    }
    try:
        raw = chat(_SYSTEM, json.dumps(request, ensure_ascii=False), max_tokens=128)
        payload = json.loads(extract_json_object(raw))
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            return None
        item = items[0]
        quote = item.get("quote")
        if (item.get("id") != "1" or item.get("action") not in ("replace", "add")
                or not isinstance(quote, str) or not quote.strip()
                or quote not in user_input or quote not in new_quote):
            return None
        return item["action"]
    except Exception:
        return None
