"""필드 provenance — "이 설정값을 사용자가 실제로 말했나"의 정본 판정.

되묻기 게이트와 진행률 표시는 "값이 있나"가 아니라 "사용자가 말했나"를 물어야 한다.
설정 필드는 시스템 기본값이 물질화되므로(max_positions=10, initial_capital=10M) 값의
존재만으로는 둘을 구분할 수 없기 때문이다.

그 판정의 유일한 입력은 **인터프리터 LLM의 구조화 출력(StrategySpec)**이다 — 미언급
필드는 None/빈 배열로 오고, 그것이 곧 "사용자가 말하지 않았다"는 LLM의 해석 결과다.
사용자 원문을 정규식으로 재분석해 같은 질문에 답하는 것은 계약 위반이며(§ 판정 기준:
"입력이 사용자 원문이면 그것은 해석이다 → LLM"), 실제로 양방향 사고를 냈다:
  · 오탐 2026-07-29 '원자력 관련주' — '거래대금 20억 원'을 초기 자본 명시로 오인
  · 미탐 2026-07-29 '부채비율·ROE 보유 조건' — '보유 종목은 10개'를 못 잡음

대화 상태 계약: ParsedStrategy 왕복은 기본값을 물질화해 provenance를 지운다
(decompiler `selection_count=parsed.max_positions`). 그래서 이 목록은 pending_ask와
같은 무상태 에코로 프론트가 다음 턴에 되돌려주고, 여기서 합집합으로 누적한다 —
한 번 명시한 값은 이후 턴에서도 명시로 남는다(누적 원문을 보던 기존 의미와 동일).
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

# 프론트 되묻기 게이트·진행률 슬롯과 1:1로 맞춘 필드 이름(정본).
UNIVERSE = "universe"
MAX_POSITIONS = "max_positions"
REBALANCING = "rebalancing"
BACKTEST_PERIOD = "backtest_period"
INITIAL_CAPITAL = "initial_capital"

KNOWN_FIELDS = (UNIVERSE, MAX_POSITIONS, REBALANCING, BACKTEST_PERIOD, INITIAL_CAPITAL)


def explicit_fields_from_spec(strategy: Any) -> List[str]:
    """LLM 구조화 출력에서 사용자가 명시한 설정 필드를 뽑는다(정규식 무관여).

    strategy: StrategySpec. None이면 빈 목록(판단 근거 없음 = 명시 없음).
    """
    if strategy is None:
        return []
    universe = getattr(strategy, "universe", None)
    portfolio = getattr(strategy, "portfolio", None)
    backtest = getattr(strategy, "backtest", None)

    fields: List[str] = []
    if universe is not None and any((
        getattr(universe, "markets", None),
        getattr(universe, "sectors", None),
        getattr(universe, "symbols", None),
        getattr(universe, "etf_theme", None),
        getattr(universe, "new_listing_only", None),
    )):
        fields.append(UNIVERSE)
    if portfolio is not None and getattr(portfolio, "selection_count", None) is not None:
        fields.append(MAX_POSITIONS)
    if portfolio is not None and getattr(portfolio, "rebalance_frequency", None) is not None:
        fields.append(REBALANCING)
    if backtest is not None and any((
        getattr(backtest, "period", None),
        getattr(backtest, "start_date", None),
        getattr(backtest, "end_date", None),
    )):
        fields.append(BACKTEST_PERIOD)
    if backtest is not None and getattr(backtest, "initial_capital", None) is not None:
        fields.append(INITIAL_CAPITAL)
    return fields


def merge_explicit_fields(
    previous: Optional[Iterable[Any]], current: Optional[Iterable[Any]]
) -> List[str]:
    """이전 턴 에코와 이번 턴 판정을 합집합으로 누적한다(정본 순서 유지).

    비정상 입력(문자열 아닌 항목·알 수 없는 이름)은 조용히 버린다 — 프론트 에코는
    신뢰 경계 밖이고, 알 수 없는 이름을 통과시키면 게이트가 오작동한다.
    """
    seen = set()
    for source in (previous or (), current or ()):
        for item in source:
            if isinstance(item, str) and item in KNOWN_FIELDS:
                seen.add(item)
    return [field for field in KNOWN_FIELDS if field in seen]
