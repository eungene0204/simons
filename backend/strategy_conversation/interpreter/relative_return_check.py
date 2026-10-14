"""Check whether an inferred zero excess-return threshold was actually requested.

The main interpreter sometimes maps a qualitative absolute-return phrase to
``technical.relative_return > 0``. Only an LLM verdict may reinterpret that
phrase; this module never classifies the user's words in deterministic code.
"""

from __future__ import annotations

from .decisions import observed_verdict

import json
import logging
from typing import Any, Callable, Optional

from .models import RankingSpec, StrategyIntent
from .output_repair import extract_json_object

logger = logging.getLogger(__name__)

_KINDS = frozenset({
    "relative_positive", "return_rank", "relative_rank",
    "qualitative_return", "qualitative_relative", "unclear",
})

_SYSTEM = """전략의 수익률 조건 인용이 사용자 요청에서 무엇을 뜻하는지 판정하세요.
relative_positive: 시장 지수보다 높은 수익률을 명시적으로 요구함.
return_rank: 종목 자체의 기간 수익률 상위 순위로 선정하라고 명시함.
relative_rank: 시장 대비 초과수익률 상위 순위로 선정하라고 명시함.
qualitative_return: 종목 자체의 수익률이 좋다/높다 등 정성적 조건이지만 임계값이나 순위를 지정하지 않음.
qualitative_relative: 시장 대비 수익률을 정성적으로 요구하지만 임계값이나 순위를 지정하지 않음.
unclear: 위 구분을 확정할 수 없음.
여러 조건 뒤의 일반적인 '상위 N종목'만으로 특정 수익률 지표의 순위를 확정하지 마세요.
다른 조건이나 종목 수의 숫자를 수익률 임계값으로 옮기지 마세요. quote는 주어진 인용을 정확히 복사하세요.
JSON만 출력: {"kind":"unclear","quote":null}"""


@observed_verdict("return")
def classify_return_quote(
    user_input: str, quote: str, chat: Callable[..., str],
) -> Optional[str]:
    """Return a grounded enum, or None on an invalid/unavailable verdict."""
    if not callable(chat) or not quote or quote not in user_input:
        return None
    request = {"utterance": user_input, "condition_quote": quote}
    try:
        from observability import span

        with span("Relative Return Check · 수익률 기준 대조", "chain",
                  inputs={"quote": quote}) as trace:
            raw = chat(_SYSTEM, json.dumps(request, ensure_ascii=False), max_tokens=96)
            payload = json.loads(extract_json_object(raw))
            kind = payload.get("kind") if isinstance(payload, dict) else None
            copied = payload.get("quote") if isinstance(payload, dict) else None
            if kind not in _KINDS or (kind != "unclear" and copied != quote):
                trace.output(failed=True)
                return None
            trace.output(kind=kind)
            return kind
    except Exception as exc:  # noqa: BLE001 — auxiliary failure is fail-open
        logger.warning("relative return check failed | err=%s", str(exc)[:200])
        return None


def reconcile_qualitative_return(
    intent: StrategyIntent, user_input: str, chat: Callable[..., str],
) -> list[str]:
    """Apply only a grounded correction to a zero relative-return condition."""
    strategy = intent.strategy
    from .required_checks import policy
    targets = [c for field in ("entry_conditions", "exit_conditions")
               for c in getattr(strategy, field) if c.factor == "technical.relative_return"
               and c.operator in (">", ">=") and c.value == 0 and c.source_text] if strategy and not strategy.ranking else []
    if policy() is not None:
        policy().plan("return", targets)
    if strategy is None or strategy.ranking:
        return []
    notices: list[str] = []
    for role in ("entry_conditions", "exit_conditions"):
        conditions = getattr(strategy, role)
        for condition in list(conditions):
            if (condition.factor != "technical.relative_return"
                    or condition.operator not in (">", ">=")
                    or condition.value != 0 or not condition.source_text):
                continue
            kind = classify_return_quote(user_input, condition.source_text, chat)
            from .required_checks import note
            note("return", condition, "UNRESOLVED" if kind in (None, "unclear") else "ACCEPT",
                 role, kind)
            if kind in (None, "unclear", "relative_positive"):
                continue
            if kind in ("return_rank", "relative_rank"):
                if role != "entry_conditions":
                    continue
                period: Any = (condition.parameters or {}).get("period")
                days = (
                    int(period) if isinstance(period, (int, float))
                    and not isinstance(period, bool) and float(period).is_integer()
                    else None
                )
                strategy.ranking.append(RankingSpec(
                    metric="ranking.return" if kind == "return_rank" else "ranking.relative_return",
                    lookback_days=days, direction="top", source_text=condition.source_text,
                ))
                conditions.remove(condition)
                notices.append(f"'{condition.source_text}'은 수익률 순위로 반영했어요.")
            else:
                if kind == "qualitative_return":
                    condition.factor = "technical.roc"
                condition.operator = None
                condition.value = None
                condition.value_source = "MISSING"
                notices.append(
                    f"'{condition.source_text}'의 수익률 기준값은 명시되지 않아 확인이 필요해요."
                )
    return notices
