"""관련주 대상의 미국 시장 명시 판정 — "사용자가 이 대상을 미국 시장에서 찾으라고 말했나"를 LLM에게 묻는다.

왜 필요한가: KR 레인의 관련주·테마 요청은 사용자가 '미국' 시장을 명시하지 않는 한 국내 시장에서
찾는다(2026-10-21 사용자 지시). 그런데 메인 인터프리터는 "스페이스x 관련주"처럼 미국 회사가
들어간 표현에 universe.markets=["US"]를 적는다(실측 4/4) — 그 시장 칸만으로는 사용자가 '미국'을
말했는지, 인터프리터가 회사 국적을 보고 붙였는지 구별할 수 없다. planner가 뽑은 표현의 접두로도
부족하다 — "미국 스페이스x 관련주"에서 planner는 '미국'을 떼고 "스페이스X 관련주"를 넘겼다(실측).

입력: 사용자 문장과 LLM이 뽑은 대상 표현. 판정은 LLM이 하고(대원칙 1), 결정론 코드의 몫은 enum
확인과 분기뿐이다.

호출 범위: KR 생성 턴에서 인터프리터가 미국 시장만 적었고 planner의 '…관련주' 표현이 국내 테마
상장사로 풀린 턴만, 한 턴 한 번(primary._recover_kr_theme_group). 수정 턴은 시장 범위 판정
(patch_scope_check)이 같은 일을 이미 한다.

실패 동작: 호출 오류·JSON 불성립·enum 밖은 **판정 없음(None)** — 복구하지 않고 지역 가드가
종전대로 판정한다(미국 요청을 조용히 국내 전략으로 바꾸지 않는 쪽).
"""

from __future__ import annotations

from .decisions import observed_verdict

import json
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# US_EXPLICIT=사용자가 미국 시장(미국 상장 종목)에서 찾으라고 말함, NOT_SPECIFIED=시장을 말하지 않음
VERDICTS = frozenset({"US_EXPLICIT", "NOT_SPECIFIED"})

_SYSTEM = """당신은 **판정기**입니다. 사용자 문장에서, 아래 투자 대상을 미국 시장(미국 상장 종목)에서 찾으라고 사용자가 직접 말했는지 답하세요.

verdict — 사용자가 미국 시장을 직접 지정했으면 "US_EXPLICIT", 시장을 말하지 않았으면 "NOT_SPECIFIED". 대상에 미국 회사 이름이 들어 있다는 것만으로는 시장 지정이 아닙니다.

출력 형식(JSON만):
{"verdict": "US_EXPLICIT" 또는 "NOT_SPECIFIED"}"""


def build_system_prompt() -> str:
    return _SYSTEM


@observed_verdict("us_market_explicit")
def check_us_market_explicit(user_input: str, term: str, chat: Callable[..., str]) -> Optional[str]:
    """대상 표현의 미국 시장 명시 여부 → "US_EXPLICIT" | "NOT_SPECIFIED", 실패는 None."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    with span("US Market Explicit Check · 미국 시장 명시 판정", "chain",
              inputs={"term": term}) as trace:
        try:
            raw = chat(_SYSTEM, f"[사용자 문장]\n{user_input}\n\n[투자 대상]\n{term}", max_tokens=32)
            payload = json.loads(extract_json_object(raw))
            verdict = payload.get("verdict") if isinstance(payload, dict) else None
            if verdict not in VERDICTS:
                raise ValueError(f"enum 밖: {verdict!r}")
        except Exception as exc:  # noqa: BLE001 — 보조 판정이 턴을 깨지 않는다
            logger.warning("us market explicit check failed — no verdict | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        trace.output(verdict=verdict)
        return verdict
