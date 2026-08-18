"""조건 누락 대조 패스 — 1차 해석이 빠뜨린 조건을 **LLM에게 다시 묻는다**.

왜 필요한가(2026-08-18 실측): 9B는 조건이 여러 개 나열된 문장에서 **하나를 밀어낸다**.
temperature 0에서 재현되고, 무엇이 밀릴지는 위치·문장 길이가 정한다.
  - "…매출 성장률이 양호하고 PBR이 과도하게 높지 않은 기업만…" → PBR 소실
  - 순서를 바꾸면 둘 다 나오고, PBR만 남기면 이번엔 시가총액(숫자 조건)이 소실
프롬프트 규칙 보강은 효과가 없었고(규칙 4-1 확장 실측) 오히려 다른 예시의 조건을 밀어냈다.
num_ctx를 32768로 올려도 동일하다 — 컨텍스트 부족이 아니라 1차 생성의 회수(recall) 문제다.

계약상 위치: 이 패스는 **LLM 레인**이다(대원칙 1). 사용자 원문의 의미를 읽는 주체는 여기서도
LLM이고, 결정론 코드는 그 출력의 형식·정본 매핑·출처 대조만 한다:
  ① factor는 registry가 아는 것만(모르는 이름은 버린다)
  ② source_text는 입력에 실재해야 한다(_quote_has_echo — 환각 조건 가드와 같은 대조)
  ③ 이미 있는 factor는 다시 넣지 않는다
  ④ 값은 만들지 않는다 — 값이 없으면 MISSING으로 두고 되묻기 레인이 질문한다

2026-08-07에 폐지된 '전체 재생성'과 다른 점: 재생성은 1차와 **같은 정보**로 다시 만들게 해
47%가 바이트 동일이었다. 이 패스는 1차 출력을 근거로 주고 "빠진 것만" 뽑게 하므로 과제가
다르고, 1차 결과를 덮어쓰지 않는다(추가만 한다).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, List, Optional

from strategy_conversation.registry.indicator_registry import (
    REGISTRY,
    factor_ids_named_in,
    resolve,
)

logger = logging.getLogger(__name__)

# 한 턴에 되살리는 조건 수 상한 — 대조 패스가 폭주해 전략을 새로 쓰는 것을 막는다.
_MAX_RECOVERED = 3

_SYSTEM = """당신은 **추출기**입니다. 전략 문장에서 **조건을 말한 구절**을 빠짐없이 나열하세요.

규칙:
- 지표를 이름으로 부른 구절만 나열합니다(PBR·ROE·시가총액·거래대금·RSI·이동평균 등).
- 구절은 **입력 문장에 있는 그대로** 적습니다(요약·번역 금지).
- 값이 없어도 나열합니다("PBR이 과도하게 높지 않은"도 조건입니다).
- 유니버스(시장·업종)·종목 수·리밸런싱·손절·익절·기간·초기자금은 조건이 아닙니다 — 빼세요.
- 판단하지 말고 나열만 하세요. 순서는 문장에 나온 순서대로.

출력 형식(JSON만, 설명 금지):
{"phrases": ["<입력 조각>", "..."]}"""


def build_system_prompt() -> str:
    return _SYSTEM


def _draft_summary(conditions: List[Any]) -> str:
    rows = []
    for cond in conditions:
        quote = (getattr(cond, "source_text", None) or "").strip()
        rows.append(f'- {cond.factor} (근거: "{quote}")' if quote else f"- {cond.factor}")
    return "\n".join(rows) if rows else "- (없음)"


def extract_condition_phrases(
    user_input: str,
    chat: Callable[..., str],
) -> List[str]:
    """LLM에게 '조건을 말한 구절'만 나열시킨다 — 차집합 판단은 시키지 않는다.

    9B는 "무엇이 빠졌나"(집합 차) 과제를 신뢰할 수 없다(2026-08-18 실측: 1차가 PBR을
    빠뜨린 상태를 그대로 보여줘도 `{"missing": []}`). 나열은 훨씬 쉬운 과제이고, 대조는
    결정론이 정확하게 한다.

    실패(호출 오류·JSON 불성립)는 빈 목록이다 — 보조 그물이 턴을 깨지 않는다.
    """
    from strategy_conversation.interpreter.output_repair import extract_json_object

    try:
        raw = chat(build_system_prompt(), f"[전략 문장]\n{user_input}", max_tokens=512)
    except Exception:  # noqa: BLE001 — 보조 그물이 턴을 깨지 않는다
        logger.debug("condition recall pass failed", exc_info=True)
        return []
    try:
        payload = json.loads(extract_json_object(raw))
    except (ValueError, TypeError):
        return []
    phrases = payload.get("phrases") if isinstance(payload, dict) else None
    if not isinstance(phrases, list):
        return []
    return [p.strip() for p in phrases if isinstance(p, str) and p.strip()]


def recover_missing_conditions(
    intent: Any,
    user_input: str,
    chat: Callable[..., str],
) -> List[str]:
    """LLM이 나열한 구절 중 **1차 전략에 없는 지표**를 되살린다. 반환값은 factor id 목록."""
    from strategy_conversation.interpreter.models import StrategyCondition
    from strategy_conversation.primary import _quote_has_echo
    from engine.nl_parser import _compact

    strategy = getattr(intent, "strategy", None)
    if strategy is None:
        return []
    existing = list(strategy.entry_conditions) + list(strategy.exit_conditions)
    known = {cond.factor for cond in existing}
    # 이미 어떤 조건의 **근거로 쓰인 구절**은 빠진 것이 아니다. factor만 대조하면,
    # 결정론 보정이 지표를 바꾼 조건('거래대금이 30일 평균보다 높은'→거래량 급증)을
    # 원래 지표로 되살려 같은 문구가 두 조건이 된다(2026-08-18 실측).
    used_quotes = {
        _compact(cond.source_text) for cond in existing if cond.source_text
    }

    phrases = extract_condition_phrases(user_input, chat)
    compact_input = _compact(user_input)
    recovered: List[str] = []
    for phrase in phrases:
        if len(recovered) >= _MAX_RECOVERED:
            break
        compact_phrase = _compact(phrase)
        # ② 구절이 입력에 실재해야 한다(환각 조건 가드와 같은 출처 대조).
        if not _quote_has_echo(compact_phrase, compact_input):
            continue
        # ②-1 이미 쓰인 근거면 건너뛴다(양방향 포함 — 구절 경계가 조금씩 다르다).
        if any(
            compact_phrase in used or used in compact_phrase
            for used in used_quotes
            if used
        ):
            continue
        # ③ 구절이 지표를 **이름으로 불러야** 한다 — 정성 표현을 새 지표로 매핑하는 것은
        #    1차 해석의 몫이고, 이 패스는 되살리는 그물이지 해석하는 자리가 아니다
        #    (2026-08-18 실측: 대조를 LLM에 맡겼더니 '추세가 확실히 잡힌'→technical.roc,
        #    문장에 없는 AI 예측 조건까지 만들어 없던 되묻기가 생겼다).
        named = factor_ids_named_in(phrase)
        for factor_id in sorted(named):
            if len(recovered) >= _MAX_RECOVERED:
                break
            if factor_id in known:
                continue
            spec = REGISTRY.get(factor_id)
            # ① registry가 모르거나 엔진에 붙지 않는 개념은 버린다.
            if spec is None or spec.engine_binding is None:
                continue
            strategy.entry_conditions.append(
                StrategyCondition(
                    factor=spec.id,
                    operator=None,
                    value=None,
                    # ④ 값은 만들지 않는다 — 되묻기 레인이 질문한다.
                    value_source="MISSING",
                    source_text=phrase,
                )
            )
            known.add(spec.id)
            recovered.append(spec.id)
    return recovered
