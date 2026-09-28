"""첫 매수 비중 되묻기 답 옮겨 적기 — "첫 매수에는 최대 투자금의 몇 %를 살까요?"의 자유 서술 답에서 값을 LLM이 옮겨 적는다.

일반 수정 인터프리터는 이 답을 옮길 칸을 찾지 못했다(2026-09-28 실측: "첫 매수는 50%"를 `/position_sizing`
`fixed_first_tranche`·`/portfolio/selection_count=5`로 지어내 패치가 버려지고 답이 조용히 사라졌다).
답이 어느 질문의 것인지는 primary가 우리가 낸 질문 문장의 동일성으로 판정한다(사용자 원문 해석이 아니다) —
현금 하한 답변(cash_pool_check)과 같은 계약이다.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_ANSWER_SYSTEM = """당신은 **옮겨 적기 도우미**입니다. 우리는 사용자에게 "첫 매수(매수 신호가 난 날)에는 최대 투자금의 몇 %를 살까요?"라고 물었습니다. 사용자의 답에서 값을 옮겨 적으세요.

percent — 답한 비율의 숫자("50%"·"절반"=50·"65퍼센트"=65), 값을 말하지 않았거나 질문에 대한 답이 아니면 null(지어내지 마세요).

출력 형식(JSON만):
{"percent": 50}"""


def check_first_buy_answer(answer: str, chat: Callable[..., str]) -> Optional[dict]:
    """첫 매수 비중 질문의 자유 서술 답 → {"first_percent": x}. 값이 없으면 {}.
    실패는 None(판정 없음 — 호출부가 일반 수정 레인으로 넘긴다)."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    with span("Tranche Check · 첫 매수 비중 답변", "chain", inputs={"answer": answer}) as trace:
        try:
            payload = json.loads(extract_json_object(
                chat(_ANSWER_SYSTEM, f"[사용자의 답]\n{answer}", max_tokens=32)))
            if not isinstance(payload, dict):
                raise ValueError("객체가 아님")
        except Exception as exc:  # noqa: BLE001
            logger.warning("first buy answer check failed | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        value = payload.get("percent")
        ok = (isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < float(value) <= 100)
        verdict = {"first_percent": float(value)} if ok else {}
        trace.output(verdict=verdict)
        return verdict
