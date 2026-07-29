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
