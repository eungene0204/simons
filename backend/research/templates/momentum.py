"""Momentum template: MA crossover entry + MA deadcross exit."""

from __future__ import annotations

from typing import Dict, List

from engine.nl_parser import ParsedStrategy, TechnicalSignal

NAME = "momentum"

PARAM_GRID: List[Dict[str, int]] = [
    {"short_period": 5, "long_period": 20},
    {"short_period": 5, "long_period": 60},
    {"short_period": 10, "long_period": 30},
    {"short_period": 10, "long_period": 60},
    {"short_period": 20, "long_period": 60},
    {"short_period": 20, "long_period": 120},
]


def build(params: Dict[str, int], universe: List[str]) -> ParsedStrategy:
    short = int(params.get("short_period", 5))
    long = int(params.get("long_period", 20))
    if short >= long:
        raise ValueError(f"momentum: short_period {short} >= long_period {long}")

    return ParsedStrategy(
        description=f"[AGENT] momentum MA{short}/{long} crossover",
        universe=list(universe),
        fundamental_filters=[],
        entry_signals=[
            TechnicalSignal(
                indicator="ma_crossover",
                signal_type="buy",
                short_period=short,
                long_period=long,
            )
        ],
        exit_signals=[
            TechnicalSignal(
                indicator="ma_crossover",
                signal_type="sell",
                short_period=short,
                long_period=long,
            )
        ],
        max_positions=params.get("max_positions", 10),
        hold_period_days=None,
        rebalancing_period="none",
        stop_loss_pct=float(params.get("stop_loss_pct", 10.0)),
        take_profit_pct=float(params.get("take_profit_pct", 25.0)),
        trailing_stop_pct=None,
        max_mdd_limit_pct=None,
        backtest_period="3y",
        initial_capital=10_000_000.0,
        execution_timing="next_open",
        fee_rate=0.015,
        slippage_rate=0.05,
    )
