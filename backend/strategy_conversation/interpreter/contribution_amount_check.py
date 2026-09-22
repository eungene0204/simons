"""적립 종목 되묻기 답 옮겨 적기 — "어떤 종목(또는 ETF)을 적립식으로 사 모을까요?"의 답을 LLM이 옮겨 적는다.

생성 턴의 조건부 납입액 판정(조건마다 "성립하면 얼마를 사나")은 2026-09-22부터 적립식 통합 판정
(contribution_plan_check)이 맡는다 — 이 모듈에는 되묻기 답 전용 옮겨 적기만 남았다.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


_SYMBOL_ANSWER_SYSTEM = """당신은 **옮겨 적기 도우미**입니다. 우리는 사용자에게 "어떤 종목(또는 ETF)을 적립식으로 사 모을까요?"라고 물었습니다. 사용자의 답에서 종목·ETF 이름(또는 종목코드)을 **말한 그대로** 옮겨 적으세요.

이름을 바꾸거나 코드를 지어내지 마세요. 질문에 대한 답이 아니거나 종목을 말하지 않았으면 빈 배열입니다.

출력 형식(JSON만):
{"symbols": ["TIGER 미국S&P500"]}"""


def check_symbol_answer(answer: str, chat: Callable[..., str]) -> Optional[List[str]]:
    """'어떤 종목을 사 모을까요?'의 자유 서술 답 → 사용자가 말한 종목·ETF 표현 목록. 실패는 None.

    기준선 프롬프트의 수정 인터프리터(120B)는 이 답을 `/backtest/contribution_amount`에 넣는다
    (2026-09-21 실측 6/6 — 질문이 '적립'을 말하고 초안의 적립 칸이 바로 옆에 있다). 그러면 패치가
    거부돼 "해석하지 못했어요"로 끝난다. 표현만 옮겨 적게 하고 코드 해석은 정본 registry가 한다."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    with span("Contribution Amount Check · 적립 종목 답변", "chain", inputs={"answer": answer}) as trace:
        try:
            payload = json.loads(extract_json_object(
                chat(_SYMBOL_ANSWER_SYSTEM, f"[사용자의 답]\n{answer}", max_tokens=96)))
            names = payload.get("symbols") if isinstance(payload, dict) else None
            if not isinstance(names, list):
                raise ValueError("symbols 배열이 아님")
        except Exception as exc:  # noqa: BLE001
            logger.warning("contribution symbol answer check failed | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        symbols = [n.strip() for n in names if isinstance(n, str) and n.strip()]
        trace.output(symbols=symbols)
        return symbols
