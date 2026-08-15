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


def test_frontend_prompt_fixture_is_current():
    """질문 문구·칩 픽스처가 정본과 동기 상태인지 확인한다.

    문구의 정본은 이 모듈 하나다(2026-08-16) — 프론트는 픽스처만 읽는다. 정본을
    고치고 픽스처를 안 갱신하면 화면에는 낡은 문구가 남으므로 여기서 깨뜨린다.
    갱신: python scripts/export_slot_prompts.py
    """
    import importlib.util
    import json
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    fixture_path = root / "app" / "analytics" / "new" / "__fixtures__" / "slot-prompts.json"
    assert fixture_path.exists(), "질문 픽스처가 없다 — export_slot_prompts.py 실행 필요"

    spec = importlib.util.spec_from_file_location(
        "export_slot_prompts", root / "scripts" / "export_slot_prompts.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        expected = module.build_fixture()
    finally:
        sys.modules.pop(spec.name, None)

    committed = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert committed == expected, (
        "질문 문구·칩이 바뀌었는데 프론트 픽스처가 낡았다 — "
        "python scripts/export_slot_prompts.py 로 갱신할 것"
    )


def test_builder_and_gate_share_one_question_source():
    """빌더와 되묻기 게이트가 같은 슬롯을 **같은 문구·같은 칩**으로 묻는다.

    2026-08-16 통합 이전에는 유니버스 질문 하나가 세 벌(빌더 5칩 / 게이트 4칩 /
    정본 2칩)로 갈려 있었고, 사용자가 어느 경로로 들어왔는지에 따라 다른 질문을 받았다.
    사본이 다시 생기면 여기서 깨진다.
    """
    from engine import strategy_slots
    from intent.strategy_builder import BuilderState, next_question

    momentum = dict(universe="KOSPI", strategy_type="momentum",
                    lookback_days=63, lookback_label="3개월")
    for builder_field, slot_field, variant, state in (
        ("universe", strategy_slots.UNIVERSE, None, BuilderState()),
        ("strategy_type", strategy_slots.ENTRY, None, BuilderState(universe="KOSPI")),
        ("holding_count", strategy_slots.MAX_POSITIONS, strategy_slots.VARIANT_RANKING,
         BuilderState(**momentum)),
        ("rebalance_cycle", strategy_slots.REBALANCING, None,
         BuilderState(**momentum, holding_count=10)),
    ):
        question, chips = next_question(state)
        slot_text, slot_chips = strategy_slots.slot_question(slot_field, variant)
        assert question.endswith(slot_text), builder_field
        assert chips == slot_chips, builder_field


def test_exit_chips_mirror_entry_chips():
    """매도 칩은 매수 칩을 뒤집은 것이다 — 같은 지표·같은 기간, 방향만 반대(2026-08-16 지시).

    문구만 맞추면 "반대 조건"이라는 설명이 거짓이 될 수 있으므로, 두 칩이 실제로 결속되는
    값을 대조해 지표·기간이 같고 매수/매도만 다른지 확인한다. 목록 순서도 나란히 읽히게
    맞춘다 — 사용자가 대응을 설명 없이 알아볼 수 있어야 한다.
    """
    from engine import strategy_slots
    from engine.nl_parser import ParsedStrategy, _apply_prompt_overrides

    def bound_signal(chip: str, role: str) -> dict:
        parsed = _apply_prompt_overrides(
            ParsedStrategy(description="x", universe=["KOSPI"]), chip,
            skip_signal_validation=True, preserve_universe=True,
        )
        signals = getattr(parsed, f"{role}_signals")
        assert signals, f"칩 '{chip}'이 {role} 신호에 결속되지 않는다"
        return signals[0].model_dump()

    entry_chips = strategy_slots.slot_question(strategy_slots.ENTRY)[1]
    exit_chips = strategy_slots.slot_question(strategy_slots.EXIT)[1]

    # 신호로 짝이 서는 만큼은 순서까지 나란하다. 매도 목록의 꼬리('20일 보유 후 청산')는
    # 대응하는 매수 조건이 없는 기간 기반 청산이라 짝 대조에서 제외한다.
    for buy_chip, sell_chip in zip(entry_chips, exit_chips):
        if sell_chip == "20일 보유 후 청산":
            break
        buy, sell = bound_signal(buy_chip, "entry"), bound_signal(sell_chip, "exit")
        assert buy["signal_type"] == "buy" and sell["signal_type"] == "sell"
        assert buy["indicator"] == sell["indicator"], f"{buy_chip} ↔ {sell_chip}"
        for param in ("short_period", "long_period", "lookback_period", "mode"):
            assert buy[param] == sell[param], f"{buy_chip} ↔ {sell_chip} / {param}"

    # 기간 기반 청산은 신호가 아니라 보유 기간에 결속된다.
    assert "20일 보유 후 청산" in exit_chips
    held = _apply_prompt_overrides(
        ParsedStrategy(description="x", universe=["KOSPI"]), "20일 보유 후 청산",
        skip_signal_validation=True, preserve_universe=True,
    )
    assert held.hold_period_days == 20


def test_exit_chips_are_all_bindable():
    """노출하는 매도 칩은 하나도 빠짐없이 값에 결속돼야 한다(칩=값 결속 계약).

    결속되지 않는 칩은 planner ask 경로에서 조용히 사라져 같은 슬롯이 경로마다 다른
    선택지를 보이게 된다 — 거래량(OBV) 매도 미러를 넣지 않은 이유가 이것이다(엔진은
    지원하지만 파서에 그 매도 표현이 없고, 어휘 추가는 대원칙 1이 금지한다).
    """
    from engine import strategy_slots
    from engine.nl_parser import ParsedStrategy, _apply_prompt_overrides
    from strategy_conversation.primary import _CHIP_BINDING_IGNORED_FIELDS

    base = ParsedStrategy(description="x", universe=["KOSPI"]).model_dump()
    for chip in strategy_slots.slot_question(strategy_slots.EXIT)[1]:
        after = _apply_prompt_overrides(
            ParsedStrategy.model_validate(base), chip,
            skip_signal_validation=True, preserve_universe=True,
        ).model_dump()
        patch = {k: v for k, v in after.items()
                 if k not in _CHIP_BINDING_IGNORED_FIELDS and base.get(k) != v}
        assert patch, f"칩 '{chip}'이 값에 결속되지 않는다 — 노출 대상이 아니다"


def test_every_entry_chip_is_consumable_by_the_builder():
    """정본 매수 조건 칩은 **하나도 빠짐없이** 빌더가 소화해야 한다.

    한쪽 레인이 읽지 못하는 칩을 내놓으면 클릭이 조용히 아무것도 하지 않거나 같은 질문이
    반복된다 — 통합 전 실측이 그랬다('PER 10 이하'·'ROE 15% 이상'이 어느 전략 유형에도
    걸리지 않아 무한 재질문). 게이트 레인의 같은 보증은 프론트
    `page.scroll.test.tsx::applies every suggested entry chip deterministically`가 한다.
    """
    from engine import strategy_slots
    from intent.strategy_builder import BuilderState, step

    for chip in strategy_slots.entry_chips(["KOSPI"]):
        result = step(BuilderState(universe="KOSPI"), chip)
        assert result.state.strategy_type is not None, chip
        # 같은 질문을 다시 내지 않는다(= 다음 단계로 넘어갔다).
        assert result.reply != strategy_slots.slot_question(strategy_slots.ENTRY)[0], chip


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


def test_single_symbol_makes_max_positions_not_applicable():
    """단독 종목(지정 1개)만 '최대 보유'가 해당 없음이다 — 포트폴리오 자체가 없다."""
    parsed = ParsedStrategy(description="단독 종목", target_symbols=["005930"])
    assert _derived(parsed, slots.MAX_POSITIONS) is slots.DerivedStatus.NOT_APPLICABLE


def test_multi_symbol_max_positions_is_applicable_and_confirmed():
    """다종목 지정(테마 유니버스 등)은 포트폴리오다 — 보유 수가 종목 수로 확정된
    완료이지 해당 없음이 아니다(2026-08-02 HBM 33곳 진행률 '해당 없음' 모순 회귀)."""
    parsed = ParsedStrategy(description="지정 종목", target_symbols=["005930", "000660"])
    assert _derived(parsed, slots.MAX_POSITIONS) is slots.DerivedStatus.APPLICABLE
    assert _value(parsed, slots.MAX_POSITIONS) is slots.ValueStatus.CONFIRMED


def test_status_only_not_applicable_does_not_change_filled():
    """표시 축이 되묻기 흐름을 바꾸면 안 된다 — MAX_POSITIONS는 filled 판정 불변."""
    parsed = ParsedStrategy(description="단독 종목", target_symbols=["005930"])
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


# ── 손절·익절 '안 함'(거부, 2026-08-10 사용자 지시) ────────────────────────────
# 손절·익절을 쓰지 않는 것도 정상적인 전략 설계인데, 거부를 표현할 방법이 없어 값을
# 넣어야만 실행 게이트를 통과할 수 있었다. 값(0)으로 표현하지 않는 이유는
# enforce_strategy_minimums가 "0%보다 커야 한다"로 이미 0을 거부하기 때문이다.

def test_declined_risk_slots_are_confirmed_and_not_asked_again():
    parsed = ParsedStrategy(description="손절 없이", universe=["KOSPI"])
    fields = [slots.STOP_LOSS, slots.TAKE_PROFIT]
    # 거부 전에는 둘 다 비어 있다.
    assert {s.field for s in slots.missing(parsed, fields=fields)} == set(fields)
    # 거부하면 값이 없어도 더 묻지 않고, 값 축은 사용자 확정이다.
    statuses = {
        s.field: s for s in slots.evaluate(
            parsed, fields=fields, declined_fields=[slots.STOP_LOSS, slots.TAKE_PROFIT])
    }
    for field in fields:
        assert statuses[field].filled is True
        assert statuses[field].value_status is slots.ValueStatus.CONFIRMED
        # 거부는 '해당 없음'이 아니다 — 물을 수 있었지만 사용자가 안 하기로 정한 것이다.
        assert statuses[field].derived_status is slots.DerivedStatus.APPLICABLE


def test_declined_field_does_not_override_an_existing_value():
    """거부 뒤에 값이 들어오면 값이 이긴다 — 화면의 값과 판정이 어긋나면 안 된다."""
    parsed = ParsedStrategy(description="손절 있음", universe=["KOSPI"], stop_loss_pct=10)
    status = next(s for s in slots.evaluate(
        parsed, fields=[slots.STOP_LOSS], declined_fields=[slots.STOP_LOSS]))
    assert status.filled is True
    assert status.value_status is slots.ValueStatus.CONFIRMED


def test_only_declinable_fields_accept_decline():
    """유니버스·매수 조건은 '안 함'이 성립하지 않는다 — 없으면 전략이 성립하지 않는다."""
    parsed = ParsedStrategy(description="빈 전략")
    status = next(s for s in slots.evaluate(
        parsed, fields=[slots.ENTRY], declined_fields=[slots.ENTRY]))
    assert status.filled is False
    assert slots.DECLINABLE_FIELDS == frozenset(
        {slots.REBALANCING, slots.STOP_LOSS, slots.TAKE_PROFIT})


def test_decline_chips_are_offered_on_risk_questions():
    """'안 함'을 고를 수 없으면 값을 넣어야만 게이트를 통과할 수 있다."""
    for field, chip in (
        (slots.STOP_LOSS, "손절 안 함"), (slots.TAKE_PROFIT, "익절 안 함"),
    ):
        status = next(s for s in slots.evaluate(
            ParsedStrategy(description="빈 전략"), fields=[field]))
        assert chip in status.suggestions
        assert slots.DECLINE_CHIP_FIELDS[chip] == field
