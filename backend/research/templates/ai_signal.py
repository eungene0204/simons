"""AI-signal template: ai_model entry + ai_drop_model exit.

Note: AIModelLeakGuard (safeguards.py) must validate that the backtest period
does NOT overlap with the AI model's training window before this template is
evaluated.
"""

from __future__ import annotations

from typing import Dict, List

from engine.nl_parser import ParsedStrategy, TechnicalSignal

NAME = "ai_signal"

PARAM_GRID: List[Dict[str, float]] = [
    {"buy_th": 65, "drop_th": 65},
    {"buy_th": 70, "drop_th": 70},
    {"buy_th": 75, "drop_th": 75},
]


def build(params: Dict[str, float], universe: List[str]) -> ParsedStrategy:
    return ParsedStrategy(
        description=f"[AGENT] AI buy>{params['buy_th']}%, sell drop>{params['drop_th']}%",
        universe=list(universe),
        fundamental_filters=[],
        entry_signals=[
            TechnicalSignal(
                indicator="ai_model",
                signal_type="buy",
                threshold=float(params["buy_th"]),
            )
        ],
        exit_signals=[
            TechnicalSignal(
                indicator="ai_drop_model",
                signal_type="sell",
                threshold=float(params["drop_th"]),
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
