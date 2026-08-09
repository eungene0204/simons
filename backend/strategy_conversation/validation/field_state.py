"""파생 런타임 상태(DerivedStatus) — 슬롯 오버라이드 조립.

**이 모듈의 산출물은 저장되지 않는다.** 매 턴 현재 전략 전체를 기준으로 다시 계산되며,
전략 State에는 원본 값만 남는다. 유니버스를 ETF로 바꾸면 기존 PER 조건은 여기서
NOT_APPLICABLE로 계산되지만 값은 그대로 보존되고, 다시 코스피로 되돌리면 역방향 패치
없이 APPLICABLE로 돌아온다(2026-07-30 설계 결정 — 상태를 저장하면 그 되돌림을 LLM이
발행해야 하고, 빠뜨리면 멀쩡한 조건에 '적용 불가'가 영구히 남는다).

`engine.strategy_slots`는 ParsedStrategy(컴파일된 DSL)만 보고 값 축과
NOT_APPLICABLE 일부를 판정한다. 나머지 두 파생 상태는 그 자리에서 알 수 없다:

- **INVALID** — 지표가 Registry에 없거나 엔진이 지원하지 않는다. ParsedStrategy는
  컴파일을 통과한 결과라 이 정보를 갖고 있지 않다.
- **CONFLICTED** — 조건 간 모순. 판정은 conflict_validator가 하고, 어느 슬롯인지는
  ValidationReport.conflicted_slots가 전달한다.

이 모듈은 검증 직후의 StrategySpec과 리포트를 읽어 슬롯 단위 오버라이드를 만든다.
**판정을 새로 하지 않는다** — 이미 검증기가 내린 판정을 필드에 붙이는 일만 한다
(같은 규칙의 두 번째 구현을 만들면 반드시 갈라진다 — strategy_slots 모듈 도입 배경).

오버라이드는 **파생 축에만** 적용되고 `filled`도 값 축도 바꾸지 않는다 — 되묻기 게이트·
백테스트 실행 버튼의 동작은 이 축 도입 전과 동일하다.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from engine.strategy_slots import ENTRY, EXIT, DerivedStatus
from strategy_conversation.registry.concept_ontology import (
    is_class_id,
    logger as ontology_logger,
)
from strategy_conversation.registry.indicator_registry import resolve

# 슬롯 필드 ← 조건 목록 속성. 조건 단위 판정이 롤업되는 두 슬롯이다.
_CONDITION_SLOTS = ((ENTRY, "entry_conditions"), (EXIT, "exit_conditions"))

# ETF 유니버스에서 쓸 수 없는 팩터 접두 — 여러 종목을 묶은 상품이라 개별 기업의
# 재무지표가 성립하지 않는다(capability_validator·engine/universe_capabilities와 동일
# 계약). 거래대금은 가격·거래량 파생이라 예외다.
_FUNDAMENTAL_PREFIX = "fundamental."
_ETF_ALLOWED_FUNDAMENTAL = "fundamental.trading_value"


def _condition_status(cond: Any, is_etf: bool) -> Optional[DerivedStatus]:
    """조건 하나의 상태. 정상이면 None(슬롯 기본 판정을 그대로 둔다)."""
    factor = getattr(cond, "factor", "") or ""
    if is_etf and factor.startswith(_FUNDAMENTAL_PREFIX) and factor != _ETF_ALLOWED_FUNDAMENTAL:
        # 지표 자체는 지원되지만 이 유니버스에서 성립하지 않는다 → 해당 없음.
        return DerivedStatus.NOT_APPLICABLE
    if is_class_id(factor):
        # 분류(클래스) 발화 — 구체 지표 선택 대기. INVALID(엔진 실행 불가)가 아니라
        # 값 대기와 같은 정상 축이다(되묻기에 답하면 해소 — INVALID/NOT_APPLICABLE
        # 판정 기준은 해결책이 있는가였다).
        ontology_logger.info("필드 상태 축 | 분류 발화 factor=%s → 정상(선택 대기)", factor)
        return None
    spec = resolve(factor)
    if spec is None or spec.supported == "UNSUPPORTED":
        # 엔진이 실행할 수 없는 조건이 값으로 남아 있다 → 유효하지 않음.
        return DerivedStatus.INVALID
    return None


def slot_status_overrides(strategy: Any, report: Any) -> Dict[str, DerivedStatus]:
    """검증 결과를 진행 골격 슬롯의 상태 오버라이드로 환산한다.

    strategy: 검증을 마친 StrategySpec(없으면 빈 dict). report: ValidationReport.
    반환 키는 engine.strategy_slots의 필드 이름이다.

    한 슬롯에 여러 조건이 있으면 가장 손이 필요한 상태가 이긴다 —
    CONFLICTED > INVALID > NOT_APPLICABLE. 모순은 조건 조합의 문제라 개별 조건의
    지원 여부보다 먼저 해결해야 한다.
    """
    overrides: Dict[str, DerivedStatus] = {}
    if strategy is None:
        return overrides

    universe = getattr(strategy, "universe", None)
    is_etf = "ETF" in (getattr(universe, "markets", None) or [])

    for slot, attr in _CONDITION_SLOTS:
        statuses = [
            s for s in (
                _condition_status(cond, is_etf)
                for cond in (getattr(strategy, attr, None) or [])
            ) if s is not None
        ]
        if not statuses:
            continue
        # 조건 전부가 해당 없음일 때만 슬롯이 해당 없음이다 — 하나라도 쓸 수 있는
        # 조건이 남아 있으면 그 슬롯은 여전히 유효한 매수/매도 규칙을 갖는다.
        total = len(getattr(strategy, attr, None) or [])
        if DerivedStatus.INVALID in statuses:
            overrides[slot] = DerivedStatus.INVALID
        elif len(statuses) == total:
            overrides[slot] = DerivedStatus.NOT_APPLICABLE

    # 모순은 개별 조건이 아니라 조합의 문제이므로 마지막에 덮어쓴다.
    for slot in (getattr(report, "conflicted_slots", None) or []):
        overrides[slot] = DerivedStatus.CONFLICTED

    return overrides
