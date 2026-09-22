"""현금 하한 되묻기 답 옮겨 적기 — "현금을 얼마나 남겨 둘까요?"의 자유 서술 답에서 값을 LLM이 옮겨 적는다.

생성 턴의 현금 풀 판정(하한·단일 매수 상한을 말했는가)은 2026-09-22부터 적립식 통합 판정
(contribution_plan_check)이 맡는다 — 이 모듈에는 되묻기 답 전용 옮겨 적기만 남았다. 답이 어느 질문의
것인지는 primary가 우리가 낸 질문 문장의 동일성으로 판정한다(사용자 원문 해석이 아니다).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _number(value: Any, low: float, high: float, *, low_open: bool, high_open: bool) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if (number < low or (low_open and number == low)
            or number > high or (high_open and number == high)):
        return None
    return number


_ANSWER_SYSTEM = """당신은 **옮겨 적기 도우미**입니다. 우리는 사용자에게 "현금을 얼마나 남겨 둘까요?(초기 자본 대비 비율이나 금액)"라고 물었습니다. 사용자의 답에서 값을 옮겨 적으세요.

percent — 비율로 답했으면 그 숫자("20%"·"이십 퍼센트"=20), 아니면 null.
amount — 금액으로 답했으면 말한 표기 그대로("300만원"), 아니면 null.
질문에 대한 답이 아니거나 값을 말하지 않았으면 둘 다 null입니다(지어내지 마세요).

출력 형식(JSON만):
{"percent": 20, "amount": null}"""


def check_reserve_answer(answer: str, chat: Callable[..., str]) -> Optional[dict]:
    """현금 하한 질문의 자유 서술 답 → {"reserve_pct": x} 또는 {"reserve_amount": y}. 값이 없으면 {}.
    실패는 None(판정 없음 — 호출부가 일반 수정 레인으로 넘긴다)."""
    from observability import span
    from strategy_conversation.interpreter.models import _normalize_amount
    from strategy_conversation.interpreter.output_repair import extract_json_object

    with span("Cash Pool Check · 현금 하한 답변", "chain", inputs={"answer": answer}) as trace:
        try:
            payload = json.loads(extract_json_object(
                chat(_ANSWER_SYSTEM, f"[사용자의 답]\n{answer}", max_tokens=64)))
            if not isinstance(payload, dict):
                raise ValueError("객체가 아님")
        except Exception as exc:  # noqa: BLE001
            logger.warning("cash reserve answer check failed | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        pct = _number(payload.get("percent"), 0, 100, low_open=False, high_open=True)
        amount = _normalize_amount(payload.get("amount"))
        if pct is not None:
            verdict = {"reserve_pct": pct}
        elif isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 0:
            verdict = {"reserve_amount": float(amount)}
        else:
            verdict = {}
        trace.output(verdict=verdict)
        return verdict
