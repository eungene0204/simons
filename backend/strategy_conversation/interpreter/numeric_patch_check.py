"""Independent LLM evidence check for numeric modification patches."""

from __future__ import annotations

import json
import math
from typing import Callable, Sequence

from .models import PatchOp
from .output_repair import extract_json_object


_SYSTEM = """전략 수정 요청에서 각 패치 경로에 사용자가 명시한 수량 표현을 독립적으로 옮겨 적으세요. quote는 그 표현의 짧은 원문 인용, number_text는 인용 안의 수량 표현 그대로, value는 그 수량, unit은 count/percent/total_multiplier/day/month/year/unknown 중 하나입니다. total_multiplier는 원금 대비 최종 금액의 배수이고 day/month/year는 보유 기간 단위입니다. 요청에 해당 경로의 수량이 없으면 quote, number_text, value를 null로 쓰세요. 다른 전략 값이나 질문의 예시값을 복사하거나 추측하지 마세요. JSON만 출력하세요: {"items":[{"id":"1","quote":null,"number_text":null,"value":null,"unit":"unknown"}]}"""


def confirmed_numeric_patches(
    candidates: Sequence[tuple[int, PatchOp]], user_input: str, chat: Callable,
) -> set[int]:
    """Return only patch indices whose independent value and literal quote agree."""
    if not candidates or not callable(chat):
        return set()
    request = {
        "utterance": user_input,
        "patches": [
            {"id": str(position), "path": patch.path,
             "source_text": patch.source_text}
            for position, (_, patch) in enumerate(candidates, 1)
        ],
    }
    try:
        raw = chat(_SYSTEM, json.dumps(request, ensure_ascii=False),
                   max_tokens=min(512, 96 + 80 * len(candidates)))
        payload = json.loads(extract_json_object(raw))
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) != len(candidates):
            return set()
        by_id = {item.get("id"): item for item in items if isinstance(item, dict)}
        expected = {str(position) for position in range(1, len(candidates) + 1)}
        if len(by_id) != len(candidates) or set(by_id) != expected:
            return set()

        confirmed = set()
        for position, (index, patch) in enumerate(candidates, 1):
            item = by_id[str(position)]
            quote = item.get("quote")
            number_text = item.get("number_text")
            value = item.get("value")
            if (not isinstance(quote, str) or not quote.strip()
                    or quote not in user_input or quote not in (patch.source_text or "")
                    or not isinstance(number_text, str) or not number_text.strip()
                    or number_text not in quote
                    or isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                continue
            unit = item.get("unit")
            if unit in ("total_multiplier", "배"):
                if patch.path != "/risk_management/take_profit":
                    continue
                value = (float(value) - 1) * 100
            elif unit in ("day", "month", "year"):
                if patch.path not in ("/portfolio/hold_period_days",
                                      "/portfolio/min_hold_period_days"):
                    continue
                if value <= 0 or not float(value).is_integer():
                    continue
                from .holding_period_check import _HOLD_UNIT_DAYS

                value = int(value) * _HOLD_UNIT_DAYS[unit]
            if math.isclose(float(value), float(patch.value), rel_tol=0, abs_tol=1e-9):
                confirmed.add(index)
        return confirmed
    except Exception:
        # A failed auxiliary check cannot authorize a previously rejected patch.
        return set()
