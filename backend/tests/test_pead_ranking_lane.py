"""실적 서프라이즈 랭킹·유니버스 사전 필터의 해석 레인 관통(엔진 v16.19).

계산 자체는 `test_earnings_factor.py`가 고정한다. 여기서는 사용자가 말한 값이 해석 →
검증 → 컴파일 → 정본 DSL·엔진 요청까지 **그대로** 도착하는지, 말하지 않은 값이 지어내지지
않는지, 범위 밖 값이 기본값으로 바꿔치기되지 않고 되묻는지를 본다(잔차 반전과 같은 계약).
"""

from __future__ import annotations

import pytest

from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


def _compile(*, ranking=None, universe=None, portfolio=None):
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI"], **(universe or {})},
        "ranking": [ranking or {"metric": "ranking.pead", "entry_delay_days": 2, "expiry_days": 60}],
        "portfolio": {"selection_count": 50, "rebalance_frequency": "daily", **(portfolio or {})},
    }))
    return compile_partial(intent, report, "실적 서프라이즈 상위 50종목")[0], report


# ── 랭킹 ────────────────────────────────────────────────────────────────────

def test_pead_ranking_reaches_engine_request_and_canonical_dsl():
    parsed, report = _compile()

    assert report.errors == []
    assert parsed.ranking_metric == "pead"
    assert (parsed.ranking_entry_delay_days, parsed.ranking_expiry_days) == (2, 60)
    dsl = to_canonical_strategy_dsl(parsed)
    assert dsl["ranking_entry_delay_days"] == 2 and dsl["ranking_expiry_days"] == 60
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["ranking_metric"] == "pead"
    assert (risk["ranking_entry_delay_days"], risk["ranking_expiry_days"]) == (2, 60)


def test_unspoken_window_falls_back_to_defaults_without_asking():
    """말하지 않은 자격 창은 기본값(2·60)으로 확정한다 — 잔차 반전과 같은 사용자 결정."""
    parsed, report = _compile(ranking={"metric": "ranking.pead"})

    assert (parsed.ranking_entry_delay_days, parsed.ranking_expiry_days) == (2, 60)
    assert not [q for q in report.clarification_questions if "ranking" in (q.field or "")]


def test_out_of_range_window_is_asked_not_silently_replaced():
    parsed, report = _compile(ranking={"metric": "ranking.pead", "expiry_days": 9999})

    assert parsed.ranking_expiry_days is None          # 기본값으로 바꿔치지 않는다
    assert any("제외까지의 기간" in message for message in report.errors)
    assert any(q.field.endswith("expiry_days") for q in report.clarification_questions)


def test_entry_delay_must_be_shorter_than_expiry():
    _parsed, report = _compile(
        ranking={"metric": "ranking.pead", "entry_delay_days": 20, "expiry_days": 5})

    assert any("짧아야 합니다" in message for message in report.errors)


def test_pead_round_trips_through_decompiler():
    parsed, _report = _compile()
    spec = decompile_strategy(parsed)

    assert spec.ranking[0].metric == "ranking.pead"
    assert (spec.ranking[0].entry_delay_days, spec.ranking[0].expiry_days) == (2, 60)


def test_pead_cannot_be_combined_with_another_ranking():
    """복합 순위 합산 대상이 아니다 — 조용히 합산하지 않고 알린 뒤 뺀다."""
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI"]},
        "ranking": [{"metric": "ranking.pead"}, {"metric": "fundamental.per", "direction": "bottom"}],
        "portfolio": {"selection_count": 20},
    }))

    assert [r.metric for r in intent.strategy.ranking] == ["fundamental.per"]
    assert any("합산할 수 없습니다" in message for message in report.errors)


def test_pead_is_rejected_for_etf_universe():
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["ETF"], "etf_theme": "반도체"},
        "ranking": [{"metric": "ranking.pead"}],
        "portfolio": {"selection_count": 5},
    }))

    assert intent.strategy.ranking == []
    assert any("분기 실적" in message for message in report.errors)


# ── 유니버스 사전 필터 ──────────────────────────────────────────────────────

def test_universe_filters_reach_engine_request():
    parsed, report = _compile(universe={
        "market_cap_top_n": 500,
        "liquidity_exclude_bottom_percent": 20,
        "liquidity_lookback_days": 20,
    })

    assert report.errors == []
    assert parsed.universe_market_cap_top_n == 500
    assert parsed.universe_liquidity_exclude_bottom_pct == 20
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["universe_market_cap_top_n"] == 500
    assert risk["universe_liquidity_exclude_bottom_pct"] == 20
    assert risk["universe_liquidity_lookback_days"] == 20


def test_universe_filters_round_trip_through_decompiler():
    parsed, _report = _compile(universe={"market_cap_top_n": 500})

    assert decompile_strategy(parsed).universe.market_cap_top_n == 500


def test_absent_universe_filters_leave_keys_out_of_canonical_dsl():
    """말하지 않으면 정본 DSL에 키가 남지 않는다(기존 전략 해시 불변)."""
    parsed, _report = _compile()
    dsl = to_canonical_strategy_dsl(parsed)

    assert "universe_market_cap_top_n" not in dsl
    assert "universe_liquidity_exclude_bottom_pct" not in dsl


def test_sector_cap_and_universe_filters_coexist():
    parsed, report = _compile(
        universe={"market_cap_top_n": 500, "liquidity_exclude_bottom_percent": 20},
        portfolio={"max_sector_weight_percent": 25},
    )

    assert report.errors == []
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["max_sector_weight_pct"] == 25
    assert risk["universe_market_cap_top_n"] == 500
    assert risk["ranking_metric"] == "pead"
