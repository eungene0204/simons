"""필드 상태 축 오버라이드(설계 스펙 § 5) — 검증 판정을 슬롯 상태로 환산한다.

여기서 고정하는 계약: 이 모듈은 **판정을 새로 하지 않는다**. 이미 검증기가 내린
판정(미지원 지표·ETF 비호환·조건 모순)을 슬롯에 붙이는 일만 한다 — 같은 규칙의 두
번째 구현을 만들면 반드시 갈라진다(strategy_slots 모듈이 생긴 이유).
"""

from __future__ import annotations

from engine.strategy_slots import ENTRY, EXIT, FieldStatus
from strategy_conversation.interpreter.models import (
    StrategyCondition,
    StrategySpec,
    UniverseSpec,
    ValidationReport,
)
from strategy_conversation.validation.field_state import slot_status_overrides


def _cond(factor: str, operator: str = "<=", value: float = 10.0) -> StrategyCondition:
    return StrategyCondition(factor=factor, operator=operator, value=value)


def test_no_findings_leaves_slots_untouched():
    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        entry_conditions=[_cond("fundamental.per")],
    )
    assert slot_status_overrides(spec, ValidationReport()) == {}


def test_missing_strategy_is_not_an_error():
    assert slot_status_overrides(None, ValidationReport()) == {}


def test_unknown_indicator_marks_slot_invalid():
    """Registry에 없는 지표가 값으로 남아 있으면 그 슬롯은 실행할 수 없다."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        entry_conditions=[_cond("완전히.없는지표")],
    )
    assert slot_status_overrides(spec, ValidationReport())[ENTRY] is FieldStatus.INVALID


def test_etf_universe_marks_fundamental_conditions_not_applicable():
    """ETF는 여러 종목을 묶은 상품이라 기업 재무지표가 성립하지 않는다.

    지표 자체는 지원되므로 INVALID가 아니라 NOT_APPLICABLE이다 — 둘의 구분이
    '지표를 바꿔라'와 '유니버스를 바꿔라'라는 서로 다른 해결책을 가리킨다.
    """
    spec = StrategySpec(
        universe=UniverseSpec(markets=["ETF"]),
        entry_conditions=[_cond("fundamental.per")],
    )
    assert slot_status_overrides(spec, ValidationReport())[ENTRY] is (
        FieldStatus.NOT_APPLICABLE
    )


def test_etf_trading_value_is_allowed():
    """거래대금은 가격·거래량 파생이라 ETF에서도 쓸 수 있다(capability_validator와 동일)."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["ETF"]),
        entry_conditions=[_cond("fundamental.trading_value", ">=", 2_000_000_000)],
    )
    assert ENTRY not in slot_status_overrides(spec, ValidationReport())


def test_partial_incompatibility_leaves_slot_usable():
    """쓸 수 있는 조건이 하나라도 남으면 그 슬롯은 여전히 유효한 규칙을 갖는다."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["ETF"]),
        entry_conditions=[
            _cond("fundamental.per"),
            _cond("fundamental.trading_value", ">=", 2_000_000_000),
        ],
    )
    assert ENTRY not in slot_status_overrides(spec, ValidationReport())


def test_conflicted_slot_wins_over_condition_level_findings():
    """모순은 조건 조합의 문제라 개별 조건의 지원 여부보다 먼저 해결해야 한다."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["ETF"]),
        entry_conditions=[_cond("fundamental.per")],
    )
    report = ValidationReport(conflicted_slots=[ENTRY])
    assert slot_status_overrides(spec, report)[ENTRY] is FieldStatus.CONFLICTED


def test_exit_slot_is_evaluated_independently():
    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        entry_conditions=[_cond("fundamental.per")],
        exit_conditions=[_cond("완전히.없는지표")],
    )
    overrides = slot_status_overrides(spec, ValidationReport())
    assert overrides == {EXIT: FieldStatus.INVALID}


# ── 모순 앵커 (conflict_validator → report.conflicted_slots) ────────────────────
# 오류 문장만으로는 어느 필드가 모순인지 알 수 없어 CONFLICTED를 붙일 수 없다.
# 판정한 자리에서 슬롯을 함께 기록하는 것이 계약이다.


def test_conflict_validator_anchors_contradiction_to_its_slot():
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.conflict_validator import validate_conflicts

    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        # PER <= 5 AND PER >= 20 — 만족하는 종목이 없다
        entry_conditions=[
            _cond("fundamental.per", "<=", 5.0),
            _cond("fundamental.per", ">=", 20.0),
        ],
    )
    errors, _warnings, conflicted = validate_conflicts(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    )
    assert errors
    assert conflicted == [ENTRY]


def test_crossover_period_order_conflict_is_anchored():
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.conflict_validator import validate_conflicts

    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        exit_conditions=[
            StrategyCondition(
                factor="technical.ma_crossover",
                operator="crosses_below",
                parameters={"short_period": 60, "long_period": 20},
            )
        ],
    )
    _errors, _warnings, conflicted = validate_conflicts(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    )
    assert conflicted == [EXIT]


def test_no_conflict_reports_no_slots():
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.conflict_validator import validate_conflicts

    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        entry_conditions=[_cond("fundamental.per", "<=", 10.0)],
    )
    _errors, _warnings, conflicted = validate_conflicts(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    )
    assert conflicted == []
