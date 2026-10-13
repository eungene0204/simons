"""Independent LLM provenance verdict for a market modification patch."""

from __future__ import annotations

import json
from typing import Callable, Sequence

from .models import PatchOp
from .output_repair import extract_json_object


_MARKET_SYSTEM = """전략 수정 패치의 출처를 독립적으로 확인합니다. patch.path=/universe/markets는 대상 시장 변경입니다. 값 KOSPI는 코스피, KOSDAQ은 코스닥를 뜻합니다. utterance가 그 시장으로 변경하라고 명시하는지 판단하세요. 다른 조건 요청이나 기존 초안의 시장 값은 근거가 아닙니다. verdict는 yes/no/unclear 중 하나, quote는 그 변경을 말한 사용자 발화의 짧은 원문 조각입니다. 명시가 없으면 no와 quote=null, 모호하면 unclear와 quote=null을 쓰세요. JSON만 출력하세요: {"verdict":"no","quote":null}"""

_CONDITION_SYSTEM = """사용자 발화와 전략 수정 조건을 독립적으로 대조합니다. 각 candidate의 factor와 비교 기준을 사용자 발화가 실제로 요청했는지 yes/no/unclear로 답하세요. 기존 전략이나 질문의 예시값에서 근거를 가져오지 마세요. yes일 때만 그 조건을 말한 짧은 원문 quote를 적고, no/unclear이면 null로 두세요. id를 그대로 유지하세요. JSON만 출력하세요: {"items":[{"id":"1","verdict":"no","quote":null}]}"""


def market_patch_scope_verdict(
    patch: PatchOp, user_input: str, chat: Callable,
) -> bool | None:
    """Return an LLM yes/no; invalid or unavailable evidence makes no decision."""
    if patch.path != "/universe/markets" or not callable(chat):
        return None
    request = {
        "utterance": user_input,
        "patch": {"path": patch.path, "value": patch.value,
                  "source_text": patch.source_text},
    }
    try:
        raw = chat(_MARKET_SYSTEM, json.dumps(request, ensure_ascii=False),
                   max_tokens=120)
        answer = json.loads(extract_json_object(raw))
        if not isinstance(answer, dict):
            return None
        verdict = answer.get("verdict")
        quote = answer.get("quote")
        if verdict == "no" and quote is None:
            return False
        if (verdict == "yes" and isinstance(quote, str) and quote.strip()
                and quote in user_input and quote in (patch.source_text or "")):
            return True
    except Exception:
        pass
    return None


def condition_patch_scope_verdicts(
    candidates: Sequence[tuple[int, PatchOp]], user_input: str, chat: Callable,
) -> dict[int, bool]:
    """Check independent new conditions; omit invalid or uncertain verdicts."""
    if not candidates or not callable(chat):
        return {}
    request = {
        "utterance": user_input,
        "candidates": [
            {"id": str(position),
             "factor": patch.value.get("factor"),
             "operator": patch.value.get("operator"),
             "value": patch.value.get("value"),
             "source_text": patch.value.get("source_text") or patch.source_text}
            for position, (_, patch) in enumerate(candidates, 1)
        ],
    }
    try:
        raw = chat(_CONDITION_SYSTEM, json.dumps(request, ensure_ascii=False),
                   max_tokens=min(512, 80 + 60 * len(candidates)))
        answer = json.loads(extract_json_object(raw))
        items = answer.get("items") if isinstance(answer, dict) else None
        if not isinstance(items, list) or len(items) != len(candidates):
            return {}
        by_id = {item.get("id"): item for item in items if isinstance(item, dict)}
        expected = {str(position) for position in range(1, len(candidates) + 1)}
        if len(by_id) != len(candidates) or set(by_id) != expected:
            return {}
        verdicts: dict[int, bool] = {}
        for position, (index, patch) in enumerate(candidates, 1):
            item = by_id[str(position)]
            verdict, quote = item.get("verdict"), item.get("quote")
            if verdict == "no" and quote is None:
                verdicts[index] = False
            elif (verdict == "yes" and isinstance(quote, str) and quote.strip()
                  and quote in user_input
                  and quote in (patch.value.get("source_text") or patch.source_text or "")):
                verdicts[index] = True
        return verdicts
    except Exception:
        return {}
