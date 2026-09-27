"""Regression coverage for four silent omissions in the Korean example strategies."""

import pytest

from engine.strategy_converter import to_backtest_request
from strategy_conversation.compiler.strategy_compiler import compile_partial, compile_strategy
from strategy_conversation.interpreter.condition_recall import (
    recover_market_cap_bounds,
    recover_ranking_selection_percent,
)
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


def _intent(*, entry_conditions=None, ranking=None, portfolio=None):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY",
        "strategy": {
            "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": []},
            "entry_conditions": entry_conditions or [],
            "exit_conditions": [],
            "ranking": ranking or [],
            "portfolio": portfolio or {"selection_count": 12},
            "risk_management": {"stop_loss": 8},
            "backtest": {},
        },
    })


def test_vague_liquidity_exclusion_remains_pending_instead_of_disappearing():
    intent = _intent(entry_conditions=[
        {"factor": "fundamental.pbr", "operator": "<=", "value": 1},
        {"factor": "fundamental.trading_value", "operator": ">=", "value": None,
         "source_text": "거래가 너무 없는 종목은 제외"},
    ])
    validated, report = run_validation(intent)
    assert "strategy.entry_conditions[1].value" in report.missing_fields
    parsed, _dropped, pending = compile_partial(validated, report, "원문")
    assert [(item["role"], item["source_text"]) for item in pending] == [
        ("entry", "거래가 너무 없는 종목은 제외")
    ]
    assert [(f.metric, f.value) for f in parsed.fundamental_filters] == [("pbr", 1.0)]


def test_market_cap_range_keeps_both_explicit_billion_won_bounds():
    intent = _intent(entry_conditions=[
        {"factor": "fundamental.market_cap", "operator": ">=", "value": 3000,
         "source_text": "시가총액 3000억 원 이상"},
        {"factor": "fundamental.market_cap", "operator": "<=", "value": 30000,
         "source_text": "3조 원 이하"},
    ])
    validated, report = run_validation(intent)
    assert report.is_valid, (report.errors, report.missing_fields)
    parsed = compile_strategy(validated, report, "원문")
    assert [(f.metric, f.operator, f.value) for f in parsed.fundamental_filters] == [
        ("market_cap", ">=", 3000.0), ("market_cap", "<=", 30000.0)
    ]
    request = to_backtest_request(parsed, resolve_symbols=False)
    bounds = [item["params"] for item in request["entry"]["conditions"]
              if item["id"] == "market_cap"]
    assert bounds == [{"operator": ">=", "value": 3000.0},
                      {"operator": "<=", "value": 30000.0}]


def test_quoted_pending_market_cap_range_recovers_both_bounds():
    prompt = "시가총액 3000억 원 이상 3조 원 이하 중형주"
    intent = _intent(entry_conditions=[
        {"factor": "fundamental.market_cap", "operator": None, "value": None,
         "source_text": "시가총액 3000억 원 이상"},
    ])
    calls = []

    def chat(system, user, **kwargs):
        calls.append((system, user))
        return '{"lower":"시가총액 3000억 원 이상","upper":"3조 원 이하"}'

    assert recover_market_cap_bounds(intent, prompt, chat) == [">=3000", "<=30000"]
    assert len(calls) == 1
    assert all(c.value_source == "USER_PROVIDED" for c in intent.strategy.entry_conditions)
    validated, report = run_validation(intent)
    assert report.is_valid, (report.errors, report.missing_fields)
    parsed = compile_strategy(validated, report, prompt)
    assert [(f.operator, f.value) for f in parsed.fundamental_filters] == [
        (">=", 3000.0), ("<=", 30000.0)
    ]


def test_market_cap_recall_rejects_quote_not_in_input():
    intent = _intent(entry_conditions=[
        {"factor": "fundamental.market_cap", "operator": None, "value": None,
         "source_text": "시가총액 3000억 원 이상"},
    ])
    def chat(*_args, **_kwargs):
        return '{"lower":"시가총액 5000억 원 이상","upper":"3조 원 이하"}'

    assert recover_market_cap_bounds(intent, "시가총액 3000억 원 이상", chat) == []
    assert len(intent.strategy.entry_conditions) == 1
    assert intent.strategy.entry_conditions[0].value is None


@pytest.mark.parametrize("lookback,percent", [(120, 15), (60, 30)])
def test_missing_rank_percent_recovers_from_independent_quoted_evidence(lookback, percent):
    prompt = f"최근 {lookback}거래일 상대강도 상위 {percent}% 종목 중 최대 12종목"
    intent = _intent(
        ranking=[{"metric": "ranking.relative_return", "lookback_days": lookback}],
        portfolio={"selection_count": 12, "rebalance_frequency": "monthly"},
    )
    def chat(*_args, **_kwargs):
        return (f'{{"percent":{percent},'
                f'"quote":"최근 {lookback}거래일 상대강도 상위 {percent}%"}}')

    assert recover_ranking_selection_percent(intent, prompt, chat, [f"{percent}%"]) == percent
    assert intent.strategy.portfolio.selection_percent == percent


def test_rank_percent_recall_rejects_other_percent_or_unquoted_value():
    intent = _intent(
        ranking=[{"metric": "ranking.relative_return", "lookback_days": 60}],
        portfolio={"selection_count": 12},
    )
    def chat(*_args, **_kwargs):
        return '{"percent":8,"quote":"손절 -8%"}'

    assert recover_ranking_selection_percent(
        intent, "상대강도 상위 30%, 손절 -8%", chat, ["30%"]
    ) is None
    assert intent.strategy.portfolio.selection_percent is None


@pytest.mark.parametrize("lookback,percent", [(120, 15), (60, 30)])
def test_relative_strength_percent_and_count_both_reach_backtest(lookback, percent):
    intent = _intent(
        ranking=[{"metric": "ranking.relative_return", "lookback_days": lookback}],
        portfolio={"selection_percent": percent, "selection_count": 12,
                   "rebalance_frequency": "monthly"},
    )
    validated, report = run_validation(intent)
    assert report.is_valid, (report.errors, report.missing_fields)
    parsed = compile_strategy(validated, report, "원문")
    assert (parsed.ranking_lookback_days, parsed.max_positions_pct,
            parsed.max_positions, parsed.max_positions_explicit) == (
                lookback, percent, 12, True)
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert (risk["ranking_lookback_days"], risk["max_positions_pct"],
            risk["max_positions"], risk["max_positions_explicit"]) == (
                lookback, percent, 12, True)
