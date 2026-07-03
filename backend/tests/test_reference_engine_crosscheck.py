"""Reference-engine cross-validation (#13): our Simulator vs backtrader.

Runs the *same* deterministic single-symbol strategy through both engines and
asserts they agree on entry/exit dates, fill prices, share count, and final
portfolio value. This independently confirms our vectorbt-based execution model
matches a second, unrelated backtesting engine.

Convention pinned: a decision on bar k executes at the FOLLOWING bar's open
(next_open) in both engines — backtrader's default broker fills market orders at
the next bar's open, matching our engine's shift+open path.
"""
import backtrader as bt
import numpy as np
import pandas as pd
import pytest

from engine.simulator import Simulator

# Synthetic OHLC: distinct opens so fill prices are unambiguous.
_OPENS = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0]
_DATES = pd.bdate_range("2021-01-04", periods=len(_OPENS))
_SHARES = 1000
_ENTRY_FILL_BAR = 2   # decision at bar 1 -> fills open[2] = 102
_EXIT_FILL_BAR = 6    # decision at bar 5 -> fills open[6] = 106
_INIT_CASH = _OPENS[_ENTRY_FILL_BAR] * _SHARES  # 102000 -> 100% buys exactly 1000 sh


def _ohlc_df():
    close = [o + 0.5 for o in _OPENS]  # close != open; irrelevant after full exit
    return pd.DataFrame(
        {"open": _OPENS, "high": [c + 1 for c in close],
         "low": [o - 1 for o in _OPENS], "close": close, "volume": 10000},
        index=_DATES,
    )


def _run_our_engine():
    df = _ohlc_df()
    close = df[["close"]].rename(columns={"close": "A"})
    opn = df[["open"]].rename(columns={"open": "A"})
    entries = pd.DataFrame({"A": [False] * len(_OPENS)}, index=_DATES)
    exits = pd.DataFrame({"A": [False] * len(_OPENS)}, index=_DATES)
    entries.iloc[_ENTRY_FILL_BAR, 0] = True
    exits.iloc[_EXIT_FILL_BAR, 0] = True
    risk = dict(init_cash=_INIT_CASH, position_size_pct=100.0,
                skip_position_setting=True, skip_risk_management=True)
    pf = Simulator().run(close, opn, entries, exits, risk,
                         dict(fee_rate=0.0, slippage_rate=0.0, sell_tax_rate=0.0,
                              execution_type="next_open"))
    tr = pf.trades.records_readable.iloc[0]
    return dict(
        entry_price=float(tr["Avg Entry Price"]),
        exit_price=float(tr["Avg Exit Price"]),
        shares=float(tr["Size"]),
        final_value=float(pf.value().iloc[-1]),
        entry_date=pd.Timestamp(tr["Entry Timestamp"]),
        exit_date=pd.Timestamp(tr["Exit Timestamp"]),
    )


class _FixedStrategy(bt.Strategy):
    """Buy on the entry-decision bar, close on the exit-decision bar."""
    def __init__(self):
        self.entry_decision = _ENTRY_FILL_BAR - 1  # next-open fill
        self.exit_decision = _EXIT_FILL_BAR - 1
        self.fills = []

    def notify_order(self, order):
        if order.status == order.Completed:
            self.fills.append((bt.num2date(order.executed.dt), order.executed.price,
                               order.executed.size))

    def next(self):
        i = len(self) - 1
        if i == self.entry_decision:
            self.buy(size=_SHARES)
        elif i == self.exit_decision:
            self.close()


def _run_backtrader():
    df = _ohlc_df()
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(_INIT_CASH)
    cerebro.broker.setcommission(commission=0.0)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(_FixedStrategy)
    strat = cerebro.run()[0]
    final_value = cerebro.broker.getvalue()
    (edt, eprice, esize), (xdt, xprice, xsize) = strat.fills[0], strat.fills[1]
    return dict(
        entry_price=float(eprice),
        exit_price=float(xprice),
        shares=float(esize),
        final_value=float(final_value),
        entry_date=pd.Timestamp(edt.date()),
        exit_date=pd.Timestamp(xdt.date()),
    )


def test_simulator_matches_backtrader():
    ours = _run_our_engine()
    ref = _run_backtrader()

    assert ours["entry_date"] == ref["entry_date"] == _DATES[_ENTRY_FILL_BAR]
    assert ours["exit_date"] == ref["exit_date"] == _DATES[_EXIT_FILL_BAR]
    assert ours["entry_price"] == pytest.approx(ref["entry_price"]) == pytest.approx(_OPENS[_ENTRY_FILL_BAR])
    assert ours["exit_price"] == pytest.approx(ref["exit_price"]) == pytest.approx(_OPENS[_EXIT_FILL_BAR])
    assert ours["shares"] == pytest.approx(ref["shares"]) == pytest.approx(_SHARES)
    assert ours["final_value"] == pytest.approx(ref["final_value"], rel=1e-9)
    # Sanity: hand result = 1000 * 106 = 106000
    assert ours["final_value"] == pytest.approx(106000.0)


def test_simulator_matches_backtrader_with_costs():
    """Agreement must hold once commission is applied on both sides."""
    fee = 0.001
    df = _ohlc_df()

    close = df[["close"]].rename(columns={"close": "A"})
    opn = df[["open"]].rename(columns={"open": "A"})
    entries = pd.DataFrame({"A": [False] * len(_OPENS)}, index=_DATES)
    exits = pd.DataFrame({"A": [False] * len(_OPENS)}, index=_DATES)
    entries.iloc[_ENTRY_FILL_BAR, 0] = True
    exits.iloc[_EXIT_FILL_BAR, 0] = True
    # Use 50% sizing so vbt's fractional percent-fill leaves a cash buffer —
    # otherwise backtrader margin-rejects an order that consumes ~100% of cash.
    risk = dict(init_cash=_INIT_CASH, position_size_pct=50.0,
                skip_position_setting=True, skip_risk_management=True)
    # backtrader 비교는 대칭 수수료만 모델링하므로 한국 거래세는 제외하고 비교한다.
    pf = Simulator().run(close, opn, entries, exits, risk,
                         dict(fee_rate=fee, slippage_rate=0.0, sell_tax_rate=0.0,
                              execution_type="next_open"))
    # Feed backtrader vbt's exact realised share count so both trade identically.
    shares = float(pf.trades.records_readable.iloc[0]["Size"])

    class _CostStrat(_FixedStrategy):
        def next(self):
            i = len(self) - 1
            if i == self.entry_decision:
                self.buy(size=shares)
            elif i == self.exit_decision:
                self.close()

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(_INIT_CASH)
    cerebro.broker.setcommission(commission=fee)
    cerebro.adddata(bt.feeds.PandasData(dataname=df))
    cerebro.addstrategy(_CostStrat)
    cerebro.run()
    ref_final = float(cerebro.broker.getvalue())

    assert float(pf.value().iloc[-1]) == pytest.approx(ref_final, rel=1e-6)
