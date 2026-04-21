"""Volume-breakout template: N-day high breakout confirmed by volume spike."""

from __future__ import annotations

from typing import Dict, List

from engine.nl_parser import ParsedStrategy, TechnicalSignal

NAME = "volume_breakout"

PARAM_GRID: List[Dict[str, int]] = [
    {"lookback": 60, "vol_period": 20},
    {"lookback": 120, "vol_period": 20},
    {"lookback": 252, "vol_period": 20},
]


def build(params: Dict[str, int], universe: List[str]) -> ParsedStrategy:
    lookback = int(params["lookback"])
    vol_period = int(params.get("vol_period", 20))

    return ParsedStrategy(
        description=f"[AGENT] {lookback}-day breakout + volume spike",
        universe=list(universe),
        fundamental_filters=[],
        entry_signals=[
            TechnicalSignal(
                indicator="breakout",
                signal_type="buy",
                lookback_period=lookback,
            ),
            TechnicalSignal(
                indicator="volume_spike",
                signal_type="buy",
                period=vol_period,
            ),
        ],
        exit_signals=[],  # risk-managed exit only
        max_positions=params.get("max_positions", 10),
        hold_period_days=params.get("hold_days", 21),
        rebalancing_period="none",
        stop_loss_pct=float(params.get("stop_loss_pct", 8.0)),
        take_profit_pct=float(params.get("take_profit_pct", 25.0)),
        trailing_stop_pct=float(params.get("trailing_stop_pct", 10.0)),
        max_mdd_limit_pct=None,
        backtest_period="3y",
        initial_capital=10_000_000.0,
        execution_timing="next_open",
        fee_rate=0.015,
        slippage_rate=0.05,
    )
