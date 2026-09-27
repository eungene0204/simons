"""The converter preserves whether a count cap was explicitly requested."""

from engine.nl_parser import ParsedStrategy
from engine.strategy_converter import to_backtest_request


def _request(*, explicit: bool):
    strategy = ParsedStrategy(
        description="Select the top 15% of 120-day returns, up to 12 stocks",
        universe=["KOSPI"],
        ranking_metric="return",
        ranking_lookback_days=120,
        max_positions=12,
        max_positions_explicit=explicit,
        max_positions_pct=15,
    )
    return to_backtest_request(strategy, resolve_symbols=False)


def test_percent_and_explicit_count_reach_the_engine_together():
    risk = _request(explicit=True)["risk"]
    assert risk["max_positions_pct"] == 15
    assert risk["max_positions"] == 12
    assert risk["max_positions_explicit"] is True


def test_percent_only_does_not_turn_the_default_count_into_a_cap():
    risk = _request(explicit=False)["risk"]
    assert risk["max_positions_pct"] == 15
    assert "max_positions_explicit" not in risk


def test_explicit_cap_has_distinct_strategy_identity_from_percent_only():
    capped = _request(explicit=True)
    percent_only = _request(explicit=False)
    assert capped["strategy_id"] != percent_only["strategy_id"]
    assert capped["canonical_strategy_dsl"]["max_positions_explicit"] is True
    assert "max_positions_explicit" not in percent_only["canonical_strategy_dsl"]
