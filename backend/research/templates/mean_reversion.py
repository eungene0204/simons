"""Mean-reversion template: RSI oversold buy + RSI overbought sell."""

from __future__ import annotations

from typing import Dict, List

from engine.nl_parser import ParsedStrategy, TechnicalSignal

NAME = "mean_reversion"

PARAM_GRID: List[Dict[str, float]] = [
    {"period": 14, "buy_th": 30, "sell_th": 70},
    {"period": 14, "buy_th": 25, "sell_th": 75},
    {"period": 10, "buy_th": 30, "sell_th": 70},
    {"period": 21, "buy_th": 30, "sell_th": 70},
]


def build(params: Dict[str, float], universe: List[str]) -> ParsedStrategy:
    period = int(params.get("period", 14))
    buy_th = float(params.get("buy_th", 30))
    sell_th = float(params.get("sell_th", 70))

    return ParsedStrategy(
        description=f"[AGENT] RSI({period}) mean-reversion {buy_th}/{sell_th}",
        universe=list(universe),
        fundamental_filters=[],
        entry_signals=[
            TechnicalSignal(
                indicator="rsi",
                signal_type="buy",
                period=period,
                operator="<=",
                value=buy_th,
            )
        ],
        exit_signals=[
            TechnicalSignal(
                indicator="rsi",
                signal_type="sell",
                period=period,
                operator=">=",
                value=sell_th,
            )
        ],
        max_positions=params.get("max_positions", 10),
        hold_period_days=None,
        rebalancing_period="none",
        stop_loss_pct=float(params.get("stop_loss_pct", 10.0)),
        take_profit_pct=float(params.get("take_profit_pct", 20.0)),
        trailing_stop_pct=None,
        max_mdd_limit_pct=None,
        backtest_period="3y",
        initial_capital=10_000_000.0,
        execution_timing="next_open",
        fee_rate=0.015,
        slippage_rate=0.05,
    )
