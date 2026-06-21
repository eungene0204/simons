"""Value template: fundamental filters (PBR/PER/ROE) + periodic rebalance."""

from __future__ import annotations

from typing import Dict, List

from engine.nl_parser import FundamentalFilter, ParsedStrategy

NAME = "value"

PARAM_GRID: List[Dict[str, float]] = [
    {"pbr_max": 1.0, "per_max": 10.0, "roe_min": 10.0, "hold_days": 252},
    {"pbr_max": 0.8, "per_max": 8.0, "roe_min": 15.0, "hold_days": 252},
    {"pbr_max": 1.2, "per_max": 12.0, "roe_min": 8.0, "hold_days": 126},
]


def build(params: Dict[str, float], universe: List[str]) -> ParsedStrategy:
    return ParsedStrategy(
        description=(
            f"[AGENT] value PBR<{params['pbr_max']} PER<{params['per_max']} ROE>{params['roe_min']}"
        ),
        universe=list(universe),
        fundamental_filters=[
            FundamentalFilter(metric="pbr", operator="<=", value=float(params["pbr_max"])),
            FundamentalFilter(metric="per", operator="<=", value=float(params["per_max"])),
            FundamentalFilter(metric="roe_or_gpa", operator=">=", value=float(params["roe_min"])),
        ],
        entry_signals=[],
        exit_signals=[],
        max_positions=params.get("max_positions", 10),
        hold_period_days=int(params["hold_days"]),
        rebalancing_period="none",
        stop_loss_pct=None,
        take_profit_pct=None,
        trailing_stop_pct=None,
        max_mdd_limit_pct=None,
        backtest_period="3y",
        initial_capital=10_000_000.0,
        execution_timing="next_open",
        fee_rate=0.015,
        slippage_rate=0.05,
    )
