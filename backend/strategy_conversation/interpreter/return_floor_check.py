"""수익률 하한 대조 — 수익률 랭킹 전략에서 "후보가 넘어야 할 수익률 하한"을 사용자가 말했는지 LLM에게 묻는다.

왜 필요한가(2026-10-26 속설 #27 녹화, nemotron-3.5-super-vl): "최근 20일 동안 30% 이상 오른 KOSPI 종목을
매수"가 2회 중 1회는 랭킹 + `portfolio.absolute_momentum_threshold_percent=30`으로 정확히 읽혔지만, 다른 1회는
하한 칸을 비우고 원문에 없는 "(시장 대비)"를 덧붙인 인용으로 `technical.relative_return > 0` 조건을 만들었다.
그 조건은 랭킹 중복 제거(`_dedupe_relative_return_against_ranking`)가 걷어내 30% 기준이 조용히 사라졌고,
백테스트는 20일 수익률 30% 미만 종목까지 샀다(473건 중 19건). 구절이 하한을 말하는지는 의미이므로
LLM이 판정한다(대원칙 1 — 원문에서 숫자를 뽑지 않는다).

결정론 코드의 몫: ① 대상 고르기(구조만 — 위쪽 순위 수익률 랭킹이 있고 하한 칸이 비어 있음) ② 응답이 정해진
enum·형식인지 확인 ③ LLM이 옮겨 적은 표기가 입력에 실재하는지(출처 대조) ④ 그 표기를 숫자로 정규화.

실패 동작: 호출 오류·JSON 불성립·enum 밖·"none"·"unclear"·옮겨 적은 표기가 입력에 없거나 숫자가 아님 →
판정 없음, 칸을 그대로 둔다(fail-open — 종전 동작).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

KINDS = frozenset({"stated", "none", "unclear"})

_SYSTEM = """당신은 **대조기**입니다. 아래 전략은 종목 자체의 기간 수익률이 높은 순으로 후보를 고릅니다.
사용자 문장이 그 수익률에 대해 "이 수익률을 넘은 종목만 산다"는 하한 숫자(예: 'N% 이상 오른', '수익률이 N% 넘는')를
직접 말했는지 답하세요.

kind — 하한 숫자를 말했으면 "stated", 말하지 않았으면 "none", 판단이 어려우면 "unclear".
value_text — kind가 "stated"일 때만, 그 숫자 표기를 문장에서 글자 그대로 옮겨 적으세요(예: "30%"). 계산·변환하지 마세요.
종목 수·보유 기간·손절·익절·다른 지표의 숫자는 하한이 아닙니다. 시장(지수) 대비 초과수익률 기준은 하한이 아닙니다.

출력 형식(JSON만):
{"kind": "none", "value_text": null}"""

_PERCENT_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로)\s*$")


def build_system_prompt() -> str:
    return _SYSTEM


def needs_check(intent: Any) -> bool:
    """구조만 본다 — 위쪽 순위 수익률 랭킹이 있고 하한 칸이 비어 있을 때."""
    strategy = getattr(intent, "strategy", None)
    if strategy is None or not strategy.ranking:
        return False
    if strategy.portfolio.absolute_momentum_threshold_percent is not None:
        return False
    return _return_ranking(strategy) is not None


def _return_ranking(strategy: Any) -> Any:
    from strategy_conversation.validation.capability_validator import _ranking_id

    return next((rank for rank in strategy.ranking
                 if _ranking_id(rank.metric) == "ranking.return" and rank.direction in (None, "top")), None)


def parse_value_text(value_text: Any, user_input: str) -> Optional[float]:
    """LLM이 옮겨 적은 표기의 형식 정규화 — 입력에 실재하고 '숫자+%' 꼴일 때만 숫자로."""
    if not isinstance(value_text, str) or not value_text.strip():
        return None
    if value_text.replace(" ", "") not in (user_input or "").replace(" ", ""):
        return None
    match = _PERCENT_RE.match(value_text)
    return float(match.group(1)) if match else None


def check_return_floor(user_input: str, intent: Any, chat: Callable[..., str]) -> Optional[float]:
    """하한 숫자를 받는다. 판정 없음은 None(fail-open)."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    if not callable(chat) or not needs_check(intent):
        return None
    rank = _return_ranking(intent.strategy)
    request = {"utterance": user_input, "ranking": {"metric": "기간 수익률", "lookback_days": rank.lookback_days}}
    with span("Return Floor Check · 수익률 하한 대조", "chain", inputs=request) as trace:
        try:
            raw = chat(_SYSTEM, json.dumps(request, ensure_ascii=False), max_tokens=64)
            payload = json.loads(extract_json_object(raw))
            kind = payload.get("kind") if isinstance(payload, dict) else None
            if kind not in KINDS:
                raise ValueError(f"enum 밖: {kind!r}")
        except Exception as exc:  # noqa: BLE001 — 보조 판정이 턴을 깨지 않는다(fail-open)
            logger.warning("return floor check failed — no verdict | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        value = parse_value_text(payload.get("value_text"), user_input) if kind == "stated" else None
        trace.output(kind=kind, value_text=payload.get("value_text"), value=value)
        return value


def recover_return_floor(intent: Any, user_input: str, chat: Callable[..., str]) -> Optional[float]:
    """판정된 하한을 빈 칸에 채운다. 채운 값을 돌려준다."""
    value = check_return_floor(user_input, intent, chat)
    if value is None:
        return None
    intent.strategy.portfolio.absolute_momentum_threshold_percent = value
    logger.info("✓ 수익률 하한 복구 | absolute_momentum_threshold_percent=%s", value)
    return value
