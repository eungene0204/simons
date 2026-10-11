"""Independent, source-only extraction shared by recall and planner scheduling."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import condition_recall
from .output_repair import extract_json_object
from ..registry.capability_registry import SUPPORTED_MARKETS


@dataclass
class ParseEvidence:
    phrases: list[str] | None = None
    period: dict | None = None
    universe_terms: list[str] | None = None
    # 구절별 정본 시장 코드(구절과 같은 순서) — 구절이 시장·지수 전체만 가리킬 때만 코드,
    # 범위를 좁히거나 다른 대상이면 None. 판정은 LLM이 하고 여기서는 정본 소속만 본다.
    universe_markets: list[str | None] | None = None

    def period_chat(self, chat):
        def answer(system, user, **kwargs):
            if self.period is not None and system == condition_recall.build_period_system_prompt():
                return json.dumps(self.period, ensure_ascii=False)
            return chat(system, user, **kwargs)
        return answer


def build_system_prompt() -> str:
    return (
        condition_recall.build_system_prompt() + "\n\n" + condition_recall.build_period_system_prompt()
        + '\n\n위 두 추출을 독립적으로 수행하세요. 조건을 기간으로 바꾸거나 생략하지 마세요. '
        '추가로 투자 대상의 시장·업종·테마·지정 종목·ETF·포함/제외 범위를 말한 구절을 '
        '모두 원문 그대로 universe.terms의 quote에 나열하세요. 단순 시장 이름만 남기고 테마 한정이나 '
        '제외 표현을 버리면 안 됩니다. 비교 기준 지수는 투자 대상이 아닙니다. '
        f'구절이 시장·지수 전체만 가리키면 market에 {"·".join(SUPPORTED_MARKETS)} 중 하나를, '
        '업종·테마·종목·ETF·제외로 범위를 좁히거나 목록에 없으면 null을 적으세요. '
        '대상이 없거나 모호하면 terms는 null입니다. 해석 결과 초안은 제공되지 않습니다. '
        '최종 출력은 반드시 아래 하나의 JSON 객체입니다. 각 하위 객체에 해당 추출 규칙을 적용하세요:\n'
        '{"conditions":{"phrases":["원문 조건 구절"]}, '
        '"backtest":{"quote":null,"period":null}, '
        '"universe":{"terms":[{"quote":"원문 대상 구절","market":null}]}}'
    )


def _universe_terms(terms: Any, user_input: str) -> list[tuple[str, str | None]] | None:
    """universe.terms 형식 검증 — 문자열 구절 또는 {quote, market}. 하나라도 어긋나면 전체 None.

    quote는 원문에 실재해야 하고, market은 정본 시장 코드이거나 null이어야 한다.
    """
    if not isinstance(terms, list) or not terms:
        return None
    parsed: list[tuple[str, str | None]] = []
    for term in terms:
        quote, market = (term, None) if isinstance(term, str) else (
            (term.get("quote"), term.get("market")) if isinstance(term, dict) else (None, None))
        if not (isinstance(quote, str) and quote.strip() and quote in user_input):
            return None
        if market is not None and market not in SUPPORTED_MARKETS:
            return None
        parsed.append((quote, market))
    return parsed


def extract_evidence(user_input: str, chat: Any) -> ParseEvidence:
    from observability import span

    result = ParseEvidence()
    try:
        with span("Parse Evidence · 독립 보조 추출", "chain"):
            payload = json.loads(extract_json_object(chat(
                build_system_prompt(), f"[전략 문장]\n{user_input}", max_tokens=1024)))
        if not isinstance(payload, dict):
            return result
        conditions = payload.get("conditions")
        phrases = conditions.get("phrases") if isinstance(conditions, dict) else None
        if isinstance(phrases, list) and all(isinstance(p, str) and p.strip() for p in phrases):
            result.phrases = phrases
        period = payload.get("backtest")
        if isinstance(period, dict) and {"quote", "period"} <= period.keys():
            if (period["quote"] is None and period["period"] is None) or (
                isinstance(period["quote"], str) and bool(period["quote"].strip())
                and isinstance(period["period"], str) and bool(period["period"].strip())
            ):
                result.period = period
        universe = payload.get("universe")
        terms = universe.get("terms") if isinstance(universe, dict) else None
        parsed_terms = _universe_terms(terms, user_input)
        if parsed_terms is not None:
            result.universe_terms = [quote for quote, _ in parsed_terms]
            result.universe_markets = [market for _, market in parsed_terms]
    except Exception:
        # A malformed section falls back to its original independent extractor.
        pass
    return result
