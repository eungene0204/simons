"""유동성 제외 대조 — "미지원으로 보고된 이 구절이 '거래가 적은 종목 제외'인가"를 LLM에게 묻는다.

왜 필요한가(2026-10-07 예시 전수 재검증, nemotron-120b): '거래가 너무 없는 종목은 제외'를 인터프리터가
프롬프트 규칙 6-5(숫자 없는 유동성 제외 → 값 없는 거래대금 조건)를 두고도 unsupported_features로
보고했다 — 예시 23에서 3회 중 1회, 이미 '거래대금 30억 원 이상'을 말한 예시 18에서 3회 중 2회.
사용자 화면에는 "지원하지 않아 반영하지 못했어요"가 나갔다. 구절이 유동성 제외인지는 의미이므로
LLM이 판정한다(대원칙 1 — 어휘 목록으로 구절을 읽지 않는다).

결정론 코드의 몫: ① 대상 고르기(LLM이 낸 미지원 보고 중 입력에 실재하는 구절) ② 응답이 정해진 enum인지
확인 ③ 판정에 따른 구조 처리 — 전략에 이미 유동성 기준(값 있는 거래대금 조건·유니버스 거래대금 하위
비율)이 있으면 같은 말의 재진술이라 보고만 걷고, 없으면 값 없는 거래대금 조건으로 옮겨 검증기가
기준값을 묻게 한다(사용자 결정 2026-10-07: 기준을 사용자에게 묻는다). 값은 만들지 않는다.

실패 동작: 호출 오류·JSON 불성립·항목 수 불일치·enum 밖·"unclear"는 판정 없음 — 보고를 그대로 둔다
(fail-open, 종전대로 미지원 안내).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

TRADING_VALUE_FACTOR = "fundamental.trading_value"
KINDS = frozenset({"liquidity", "other", "unclear"})

_SYSTEM = """당신은 **대조기**입니다. 전략 문장에서 해석기가 '지원하지 않음'으로 보고한 구절마다, 그 구절이 무엇을 말하는지 답하세요.

kind — 거래가 적은(거래량·거래대금이 부족한, 유동성이 낮은) 종목을 대상에서 빼거나 거르자는 말이고 그 기준 숫자(금액·비율)가 구절에 없으면 "liquidity". 그 밖의 개념이거나 기준 숫자가 있으면 "other", 판단이 어려우면 "unclear".

출력 형식(JSON만, 항목 순서대로):
{"items": [{"kind": "liquidity"}]}"""


def build_system_prompt() -> str:
    return _SYSTEM


def features_to_check(intent: Any, user_input: str) -> List[str]:
    """물어볼 보고 — 입력에 실재하는(출처 대조를 통과하는) 미지원 보고 구절만."""
    from engine.nl_parser import _compact
    from strategy_conversation.primary import _quote_has_echo

    compact_input = _compact(user_input or "")
    targets: List[str] = []
    for feature in getattr(intent, "unsupported_features", None) or []:
        compact = _compact(str(feature or ""))
        if len(compact) >= 4 and _quote_has_echo(compact, compact_input):
            targets.append(feature)
    return targets


def build_request(user_input: str, targets: List[str]) -> Tuple[str, str, int]:
    rows = "\n".join(f'{i}. 구절: "{text}"' for i, text in enumerate(targets, 1))
    return _SYSTEM, f"[전략 문장]\n{user_input}\n\n[보고된 구절]\n{rows}", 32 + 24 * len(targets)


def check_features(
    user_input: str, targets: List[str], chat: Callable[..., str],
) -> Optional[List[Tuple[str, Optional[str]]]]:
    """구절마다 kind를 받는다. 실패는 None(fail-open)."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    if not targets:
        return []
    system, user, max_tokens = build_request(user_input, targets)
    with span("Liquidity Exclusion Check · 유동성 제외 대조", "chain",
              inputs={"features": targets}) as trace:
        try:
            raw = chat(system, user, max_tokens=max_tokens)
            payload = json.loads(extract_json_object(raw))
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list) or len(items) != len(targets):
                raise ValueError(f"항목 수 불일치: {len(targets)}개 요청")
        except Exception as exc:  # noqa: BLE001 — 보조 판정이 턴을 깨지 않는다(fail-open)
            logger.warning("liquidity exclusion check failed — no verdicts | err=%s",
                           str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        pairs = []
        for text, item in zip(targets, items):
            kind = item.get("kind") if isinstance(item, dict) else None
            pairs.append((text, kind if kind in KINDS else None))
        trace.output(verdicts=[{"feature": t, "kind": k} for t, k in pairs])
        return pairs


def _has_liquidity_criterion(strategy: Any) -> bool:
    from strategy_conversation.registry.indicator_registry import resolve

    universe = getattr(strategy, "universe", None)
    if getattr(universe, "liquidity_exclude_bottom_percent", None) is not None:
        return True
    for cond in strategy.entry_conditions:
        spec = resolve(cond.factor)
        if spec is not None and spec.id == TRADING_VALUE_FACTOR and cond.value is not None:
            return True
    return False


def apply_verdicts(intent: Any, pairs: Optional[List[Tuple[str, Optional[str]]]]) -> List[str]:
    """유동성 제외로 판정된 보고를 걷어 구조로 옮긴다. 옮긴 구절 목록을 돌려준다."""
    from strategy_conversation.interpreter.models import StrategyCondition

    strategy = getattr(intent, "strategy", None)
    liquidity = [text for text, kind in pairs or [] if kind == "liquidity"]
    if strategy is None or not liquidity:
        return []
    intent.unsupported_features = [
        f for f in intent.unsupported_features if f not in liquidity]
    # 이미 유동성 기준이 있으면 같은 말의 재진술이다 — 기준을 다시 묻지 않는다.
    if not _has_liquidity_criterion(strategy):
        strategy.entry_conditions.append(StrategyCondition(
            factor=TRADING_VALUE_FACTOR,
            operator=">=",
            value=None,
            value_source="MISSING",
            source_text=liquidity[0],
        ))
    return liquidity
