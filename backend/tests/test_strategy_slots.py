"""engine.strategy_slots — 빈 슬롯 판정 단일 정본(SOT)의 계약 테스트.

이 판정이 네 곳에 복제돼 있던 시절 이음매마다 사고가 났다(2026-07-28 리밸런싱,
2026-07-29 매수 조건 ×2). 여기서 고정하는 것은 **모든 소비자가 같은 답을 얻는다**는
계약이다 — 소비자별 차이는 판정이 아니라 범위(fields)·provenance 유무로만 표현한다.
"""

from __future__ import annotations

from engine import strategy_slots as slots
from engine.nl_parser import ParsedStrategy


def _sig(kind: str, signal_type: str = "buy") -> dict:
    return {"indicator": kind, "signal_type": signal_type,
            "short_period": 5, "long_period": 20}


def _complete() -> ParsedStrategy:
    return ParsedStrategy(
        description="완성 전략",
        universe=["KOSPI"],
        entry_signals=[_sig("ma_crossover", "buy")],
        exit_signals=[_sig("ma_crossover", "sell")],
        max_positions=10,
        rebalancing_period="monthly",
        stop_loss_pct=10.0,
        take_profit_pct=20.0,
        backtest_period="5y",
        initial_capital=10_000_000,
    )


ALL_EXPLICIT = ["universe", "max_positions", "rebalancing",
                "backtest_period", "initial_capital"]


# ── 기본값 물질화 vs provenance ────────────────────────────────────────────────

def test_materialized_defaults_are_not_user_input():
    """값이 있어도 사용자가 말하지 않았으면 채워진 것이 아니다."""
    empty = ParsedStrategy(description="빈 전략")
    assert empty.universe and empty.max_positions  # 기본값이 실제로 있다
    assert slots.filled_slots(empty, require_explicit=True) == []
    # provenance를 보지 않는 레인(레거시 게이트)은 값 기준으로 판정한다.
    assert "유니버스" in slots.filled_slots(empty, require_explicit=False)


def test_explicit_fields_promote_slots_one_by_one():
    empty = ParsedStrategy(description="빈 전략")
    assert slots.filled_slots(
        empty, explicit_fields=["universe"], require_explicit=True) == ["유니버스"]
    assert slots.filled_slots(
        empty, explicit_fields=["universe", "initial_capital"],
        require_explicit=True) == ["유니버스", "초기 자본"]


# ── 슬롯 그룹(8칸)과 필드(9개) ────────────────────────────────────────────────

def test_risk_slot_needs_both_stop_and_take():
    """리스크 관리 슬롯은 손절·익절이 모두 있어야 충족 — 한쪽만 있으면 물을 것이 남았다."""
    parsed = _complete().model_copy(update={"take_profit_pct": None})
    filled = slots.filled_slots(parsed, explicit_fields=ALL_EXPLICIT, require_explicit=True)
    assert "리스크 관리" not in filled
    assert slots.next_missing(
        parsed, explicit_fields=ALL_EXPLICIT, require_explicit=True
    ).field == slots.TAKE_PROFIT


def test_complete_strategy_fills_every_slot():
    filled = slots.filled_slots(_complete(), explicit_fields=ALL_EXPLICIT,
                                require_explicit=True)
    assert filled == list(slots.SLOT_ORDER)
    assert slots.next_missing(_complete(), explicit_fields=ALL_EXPLICIT,
                              require_explicit=True) is None


def test_progress_order_is_the_skeleton_order():
    empty = ParsedStrategy(description="빈 전략")
    order = [s.field for s in slots.missing(empty, require_explicit=True)]
    assert order == list(slots.FIELD_ORDER)


# ── 대상 구성에 따른 면제 ──────────────────────────────────────────────────────

def test_single_symbol_is_exempt_from_rebalancing():
    single = _complete().model_copy(
        update={"target_symbols": ["005930"], "rebalancing_period": "none"})
    assert slots.next_missing(single, explicit_fields=ALL_EXPLICIT,
                              require_explicit=True) is None


def test_multi_symbol_theme_is_still_asked_for_rebalancing():
    """[회귀 2026-07-28 '모바일솔루션 관련주'] 지정 종목이 여럿이면 포트폴리오다."""
    theme = _complete().model_copy(
        update={"target_symbols": ["108860", "139670", "051160"],
                "rebalancing_period": "none"})
    assert slots.next_missing(
        theme, explicit_fields=ALL_EXPLICIT, require_explicit=True
    ).field == slots.REBALANCING


def test_target_symbols_imply_universe_and_max_positions():
    parsed = ParsedStrategy(
        description="지정 종목", target_symbols=["005930"],
        entry_signals=[_sig("ma_crossover", "buy")],
        exit_signals=[_sig("ma_crossover", "sell")],
        stop_loss_pct=10.0, take_profit_pct=20.0,
    )
    filled = slots.filled_slots(parsed, explicit_fields=[], require_explicit=True)
    assert "유니버스" in filled and "최대 보유" in filled


def test_declined_rebalancing_is_not_reasked_in_either_lane():
    """'안 함'은 사용자의 결정 — provenance를 보지 않는 레인에서도 되묻지 않는다.
    (이 판정을 provenance 쪽에 두면 레거시 게이트가 무시해 무한 반복된다.)"""
    parsed = _complete().model_copy(update={"rebalancing_period": "none"})
    for require_explicit in (False, True):
        remaining = [s.field for s in slots.missing(
            parsed, explicit_fields=ALL_EXPLICIT, require_explicit=require_explicit,
            rebalancing_declined=True)]
        assert slots.REBALANCING not in remaining


# ── 소비자별 범위 ─────────────────────────────────────────────────────────────

def test_ranking_fills_entry_slot():
    """랭킹 전략은 진입 신호가 없어도 매수 조건이 채워진 것이다."""
    parsed = ParsedStrategy(description="모멘텀", universe=["KOSPI"],
                            ranking_metric="return", ranking_lookback_days=60)
    assert "매수 조건" in slots.filled_slots(parsed, explicit_fields=["universe"],
                                            require_explicit=True)


def test_rebalancing_fills_exit_slot():
    """정기 리밸런싱은 청산 경로다 — 매도 신호가 없어도 매도 조건 슬롯을 채운다."""
    parsed = ParsedStrategy(description="리밸런싱", universe=["KOSPI"],
                            rebalancing_period="monthly")
    filled = slots.filled_slots(parsed, explicit_fields=["universe", "rebalancing"],
                                require_explicit=True)
    assert "매도 조건" in filled and "리밸런싱" in filled


def test_backend_gate_scope_excludes_provenance_only_fields():
    """레거시 게이트는 최대 보유·기간·초기 자본을 묻지 않는다 — provenance 없이는
    기본값과 사용자 입력을 구분할 수 없어서다(그 셋은 provenance를 가진 레인 소관)."""
    from engine.nl_parser import _GATE_FIELDS

    assert slots.MAX_POSITIONS not in _GATE_FIELDS
    assert slots.BACKTEST_PERIOD not in _GATE_FIELDS
    assert slots.INITIAL_CAPITAL not in _GATE_FIELDS


def test_gate_questions_come_from_the_same_source():
    """되묻기 문구도 SOT에서 온다 — 판정과 질문이 떨어져 있으면 한쪽만 갱신된다."""
    from engine.nl_parser import detect_incomplete_backtest_conditions

    parsed = ParsedStrategy(description="빈 전략")
    question, chips = detect_incomplete_backtest_conditions(parsed)
    expected = slots.next_missing(parsed, fields=(slots.UNIVERSE, slots.ENTRY))
    assert question == expected.question
    assert chips == list(expected.suggestions)


def test_frontend_parity_fixture_is_current():
    """프론트 고정용 계약 픽스처가 정본과 동기 상태인지 확인한다.

    프론트는 칩 답변을 백엔드 왕복 없이 적용해야 해서 같은 판정을 로컬에도 둔다 —
    구현이 둘이면 어긋나므로 정본이 생성한 픽스처로 프론트를 고정하고
    (`app/analytics/new/backtestReadiness.parity.test.ts`), 정본이 바뀌었는데
    픽스처를 안 갱신하면 여기서 깨진다. 갱신: python scripts/export_slot_judgments.py
    """
    import importlib.util
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    fixture_path = root / "app" / "analytics" / "new" / "__fixtures__" / "slot-judgments.json"
    assert fixture_path.exists(), "계약 픽스처가 없다 — export_slot_judgments.py 실행 필요"

    spec = importlib.util.spec_from_file_location(
        "export_slot_judgments", root / "scripts" / "export_slot_judgments.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        expected = module.build_fixture()
    finally:
        sys.modules.pop(spec.name, None)

    committed = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert committed == expected, (
        "빈 슬롯 판정이 바뀌었는데 프론트 계약 픽스처가 낡았다 — "
        "python scripts/export_slot_judgments.py 로 갱신하고 프론트 parity 테스트를 확인할 것"
    )


# ─── 시스템이 확정한 값의 재질문 금지 (FR-STR-073 ⑥, 2026-07-29) ──────────────

def _cohort_strategy():
    """신규 상장 코호트 전략 — 백테스트 창이 상장일 하한으로 확정된 상태."""
    from engine.nl_parser import (
        FundamentalFilter, ParsedStrategy, TechnicalSignal, enforce_strategy_minimums,
    )

    parsed = ParsedStrategy(
        description="2026년 신규 상장 종목 투자 전략",
        universe=["KOSPI", "KOSDAQ"], new_listing_only=True,
        listing_from="2026-01-01", listing_to="2026-12-31",
        fundamental_filters=[FundamentalFilter(metric="per", operator="<=", value=10)],
        exit_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="sell",
                                      short_period=5, long_period=20)],
        max_positions=10, rebalancing_period="none",
        stop_loss_pct=15.0, take_profit_pct=30.0,
    )
    enforce_strategy_minimums(parsed)
    return parsed


_COHORT_KWARGS = dict(
    explicit_fields=["universe", "max_positions", "rebalancing"],
    require_explicit=True,
    rebalancing_declined=True,
)


def test_new_listing_cohort_does_not_reask_backtest_period():
    # [회귀] 요약 카드엔 "2026-01-01 ~ 현재"가 떠 있는데 "어느 기간의 과거 데이터로
    # 백테스트할까요?"를 다시 묻던 사고. 창은 상장일 하한으로 확정돼 다른 답이 성립하지
    # 않는다 — provenance("사용자가 말했나")로는 표현할 수 없어 _decided가 맡는다.
    parsed = _cohort_strategy()
    assert parsed.backtest_start_date == "2026-01-01"
    status = {s.field: s.filled for s in slots.evaluate(parsed, **_COHORT_KWARGS)}
    assert status[slots.BACKTEST_PERIOD] is True
    assert slots.next_missing(parsed, **_COHORT_KWARGS).field == \
        slots.INITIAL_CAPITAL


def test_backtest_period_value_judgment_matches_provenance_fields():
    # 값 판정(_has_value)과 provenance(explicit_fields_from_spec)는 같은 필드 집합을 봐야
    # 한다 — 두 축이 서로 다른 필드를 보는 상태를 남겨두지 않는다는 계약. ParsedStrategy는
    # backtest_period 기본값("5y")을 물질화하므로 이 세 필드가 모두 비는 일은 실제로는
    # 없고(방어적 일관성), 아래는 그 계약을 직접 고정한다.
    from engine.nl_parser import ParsedStrategy

    parsed = ParsedStrategy(
        description="명시 날짜가 있는 전략", universe=["KOSPI"],
        backtest_start_date="2020-01-01", backtest_end_date="2024-12-31",
    )
    assert slots._has_value(parsed, slots.BACKTEST_PERIOD) is True
    parsed.backtest_period = None      # 스키마상 도달 불가 — 계약만 확인한다
    parsed.backtest_end_date = None
    assert slots._has_value(parsed, slots.BACKTEST_PERIOD) is True
    parsed.backtest_start_date = None
    assert slots._has_value(parsed, slots.BACKTEST_PERIOD) is False


def test_non_cohort_strategy_still_asks_backtest_period():
    # 확정 근거(listing_from)가 없으면 종전대로 묻는다 — 가드가 전역으로 새지 않는다.
    parsed = _cohort_strategy()
    parsed.new_listing_only = False
    parsed.listing_from = None
    parsed.listing_to = None
    parsed.backtest_start_date = None
    assert slots.next_missing(parsed, **_COHORT_KWARGS).field == \
        slots.BACKTEST_PERIOD


# ── 상태 축 (설계 스펙 § 5) ────────────────────────────────────────────────────
# `filled` 불리언이 뭉개던 정보를 되살린 축이다. 핵심 계약은 두 가지:
#   ① 상태를 추가해도 filled 판정은 바뀌지 않는다(되묻기·실행 게이트 동작 불변)
#   ② '해당 없음'과 '완료'가 더는 같은 값으로 보이지 않는다


def _value(parsed, field, **kwargs):
    return next(s for s in slots.evaluate(parsed, **kwargs) if s.field == field).value_status


def _derived(parsed, field, **kwargs):
    return next(s for s in slots.evaluate(parsed, **kwargs) if s.field == field).derived_status


def test_single_symbol_rebalancing_is_not_applicable_not_complete():
    """단독 종목은 교체가 없다 — 이전에는 filled=True 하나뿐이라 '완료'로 보였다."""
    parsed = ParsedStrategy(description="단일 종목", target_symbols=["005930"])
    assert _derived(parsed, slots.REBALANCING) is slots.DerivedStatus.NOT_APPLICABLE
    # filled 판정은 그대로다(더 묻지 않는다).
    assert next(s for s in slots.evaluate(parsed) if s.field == slots.REBALANCING).filled


def test_declined_rebalancing_is_confirmed_not_not_applicable():
    """사용자가 '안 함'을 고른 것은 확정값이다 — 구성상 무의미한 것과 다르다."""
    parsed = ParsedStrategy(description="리밸런싱 거부", universe=["KOSPI"])
    assert _value(
        parsed, slots.REBALANCING, rebalancing_declined=True
    ) is slots.ValueStatus.CONFIRMED


def test_materialized_default_is_provisional_not_confirmed():
    """값은 있으나 사용자가 말한 적 없다 — 확정값과 구분된다."""
    empty = ParsedStrategy(description="빈 전략")
    assert empty.max_positions  # 기본값이 물질화돼 있다
    assert _value(empty, slots.MAX_POSITIONS) is slots.ValueStatus.PROVISIONAL


def test_user_provided_value_is_confirmed():
    parsed = _complete()
    assert _value(
        parsed, slots.MAX_POSITIONS, explicit_fields=ALL_EXPLICIT
    ) is slots.ValueStatus.CONFIRMED


def test_absent_value_is_unknown():
    parsed = ParsedStrategy(description="진입 없음", universe=["KOSPI"])
    assert _value(parsed, slots.ENTRY) is slots.ValueStatus.UNKNOWN


def test_specified_symbols_make_max_positions_not_applicable():
    """지정 종목 모드는 보유 수가 종목 수로 확정된다 — 물을 대상이 아니다."""
    parsed = ParsedStrategy(description="지정 종목", target_symbols=["005930", "000660"])
    assert _derived(parsed, slots.MAX_POSITIONS) is slots.DerivedStatus.NOT_APPLICABLE


def test_status_only_not_applicable_does_not_change_filled():
    """표시 축이 되묻기 흐름을 바꾸면 안 된다 — MAX_POSITIONS는 filled 판정 불변."""
    parsed = ParsedStrategy(description="지정 종목", target_symbols=["005930", "000660"])
    before = next(s for s in slots.evaluate(parsed) if s.field == slots.MAX_POSITIONS)
    assert before.filled is slots._has_value(parsed, slots.MAX_POSITIONS)


def test_listing_cohort_backtest_window_is_confirmed():
    """신규 상장 코호트의 창은 시스템이 확정한다 — 추천값(PROVISIONAL)이 아니다."""
    parsed = ParsedStrategy(
        description="신규 상장", universe=["KOSPI"],
        new_listing_only=True, listing_from="2024-01-01",
    )
    assert _value(parsed, slots.BACKTEST_PERIOD) is slots.ValueStatus.CONFIRMED


def test_overrides_apply_to_status_only():
    """상위 검증 판정(INVALID·CONFLICTED)은 상태만 덮고 filled는 건드리지 않는다."""
    parsed = _complete()
    entry = next(s for s in slots.evaluate(
        parsed, explicit_fields=ALL_EXPLICIT,
        status_overrides={slots.ENTRY: slots.DerivedStatus.CONFLICTED},
    ) if s.field == slots.ENTRY)
    assert entry.derived_status is slots.DerivedStatus.CONFLICTED
    # 값 축은 덮이지 않는다 — 모순은 값의 출처를 바꾸지 않는다.
    assert entry.value_status is slots.ValueStatus.CONFIRMED
    assert entry.filled is True


def test_overrides_do_not_resurrect_empty_fields():
    """값이 없는 필드는 모순일 수 없다 — UNKNOWN은 덮이지 않는다."""
    parsed = ParsedStrategy(description="진입 없음", universe=["KOSPI"])
    assert _derived(
        parsed, slots.ENTRY, status_overrides={slots.ENTRY: slots.DerivedStatus.INVALID}
    ) is slots.DerivedStatus.APPLICABLE


def test_slot_statuses_rolls_up_risk_slot():
    """리스크 관리는 손절·익절 둘을 묶는다 — 한쪽만 있으면 아직 물을 것이 남았다."""
    parsed = _complete().model_copy(update={"take_profit_pct": None})
    assert slot_status_of(parsed, "리스크 관리").value_status is slots.ValueStatus.UNKNOWN
    assert slot_status_of(_complete(), "리스크 관리").value_status is slots.ValueStatus.CONFIRMED


def slot_status_of(parsed, slot, **kwargs):
    return slots.slot_statuses(parsed, explicit_fields=ALL_EXPLICIT, **kwargs)[slot]


def test_slot_statuses_covers_eight_slots():
    assert list(slots.slot_statuses(_complete(), explicit_fields=ALL_EXPLICIT)) == list(
        slots.SLOT_ORDER
    )
