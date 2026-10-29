"""돌파 가격 기준 대조 — "이 신고가·신저가 돌파 인용은 종가로 판정하나, 고가·저가로 판정하나"를 LLM에게 묻는다.

왜 필요한가(2026-10-29 실측, nemotron-3.5-super): '종가가 20일 신고가를 돌파하면 매수'를 인터프리터가
technical.breakout(lookback_period=20)으로 옳게 냈지만, 그 형태에는 가격 기준을 실을 자리가 없어 엔진의
고가 기준(오늘 고가 > 직전 20일 최고 고가)으로 백테스트됐다. 종가 기준은 메인 프롬프트가 모르는 칸이라
돌파 조건이 있는 턴에만 도는 전용 판정이 채운다(메인 프롬프트 불변).

사용자 결정(2026-10-29): '종가가 신고가 돌파' = 오늘 종가 > 직전 N거래일 최고 종가(신저가는 최저 종가).
기준을 말하지 않으면 종전대로 고가·저가 기준이다(되묻지 않는다).

결정론 코드의 몫: ① 대상 조건 고르기(LLM 출력 필드의 형태) ② 응답이 정해진 enum인지 확인
③ "close" 판정이면 parameters.price_basis를 싣기. 인용 문자열은 읽지 않는다.

실패 동작: 호출 오류·JSON 불성립·항목 수 불일치·enum 밖·"unclear"는 판정 없음 — 조건을 그대로 둔다
(fail-open). 그때는 종전대로 고가·저가 기준이다.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, List, Optional, Tuple

from .decisions import observed_verdict

logger = logging.getLogger(__name__)

BREAKOUT_FACTORS = ("technical.breakout", "technical.breakout_low")

BASES = frozenset({"close", "intraday", "unspecified", "unclear"})

_SYSTEM = """당신은 **대조기**입니다. 전략 문장에서 뽑은 신고가·신저가 돌파 조건의 인용 조각마다, 돌파를 어떤 가격으로 판정하는지 답하세요.

basis — 인용이 종가(마감 가격)로 돌파·이탈을 판정한다고 말하면 "close", 고가·저가·장중 가격으로 판정한다고 말하면 "intraday", 가격 종류를 말하지 않았으면 "unspecified", 판단이 어려우면 "unclear".

출력 형식(JSON만, 항목 순서대로):
{"items": [{"basis": "close"}]}"""


def build_system_prompt() -> str:
    return _SYSTEM


def _canonical_factor(factor: Optional[str]) -> Optional[str]:
    from strategy_conversation.registry.indicator_registry import REGISTRY

    spec = REGISTRY.get(factor) if factor else None
    return spec.id if spec is not None else factor


def conditions_to_check(strategy: Any, only: Optional[List[Any]] = None) -> List[Any]:
    """물어볼 조건 — 인용이 있고 가격 기준이 아직 없는 돌파 조건."""
    targets: List[Any] = []
    for role in ("entry_conditions", "exit_conditions"):
        for cond in getattr(strategy, role):
            if only is not None and not any(cond is c for c in only):
                continue
            if (_canonical_factor(cond.factor) in BREAKOUT_FACTORS and cond.source_text
                    and (cond.parameters or {}).get("price_basis") is None):
                targets.append(cond)
    return targets


def build_request(user_input, targets):
    rows = "\n".join(f'{i}. 인용: "{cond.source_text}"' for i, cond in enumerate(targets, 1))
    return _SYSTEM, f"[전략 문장]\n{user_input}\n\n[돌파 조건]\n{rows}", 32 + 16 * len(targets)


@observed_verdict("breakout")
def check_breakout_basis(
    user_input: str, targets: List[Any], chat: Callable[..., str],
) -> Optional[List[Tuple[Any, Optional[str]]]]:
    """조건마다 가격 기준 판정을 받는다. 실패는 None(fail-open), enum 밖은 판정 없음(None)."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    if not targets:
        return []
    system, user, max_tokens = build_request(user_input, targets)
    with span("Breakout Basis Check · 돌파 가격 기준 대조", "chain",
              inputs={"quotes": [c.source_text for c in targets]}) as trace:
        try:
            raw = chat(system, user, max_tokens=max_tokens)
            payload = json.loads(extract_json_object(raw))
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list) or len(items) != len(targets):
                raise ValueError(f"항목 수 불일치: {len(targets)}개 요청")
        except Exception as exc:  # noqa: BLE001 — 보조 판정이 턴을 깨지 않는다(fail-open)
            logger.warning("breakout basis check failed — no verdicts | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        pairs: List[Tuple[Any, Optional[str]]] = []
        for cond, item in zip(targets, items):
            basis = item.get("basis") if isinstance(item, dict) else None
            pairs.append((cond, basis if basis in BASES else None))
        trace.output(verdicts=[{"quote": c.source_text, "basis": b} for c, b in pairs])
        return pairs


def apply_verdicts(pairs: Optional[List[Tuple[Any, Optional[str]]]]) -> List[Any]:
    """종가 기준으로 판정된 조건에 price_basis="close"를 싣는다. 실은 조건 목록을 돌려준다."""
    marked: List[Any] = []
    for cond, basis in pairs or []:
        if basis != "close":
            continue
        cond.parameters = {**(cond.parameters or {}), "price_basis": "close"}
        marked.append(cond)
    return marked
