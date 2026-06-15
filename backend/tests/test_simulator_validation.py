"""Validation regression tests — pin the Backtest Validation Agent's findings.

These lock in the engine guarantees verified during validation so a future change
that silently breaks them fails CI:

  - Hand-calculation: a trivial buy/sell matches a by-hand result exactly (#12).
  - Trading costs: fees + slippage are applied on BOTH entry and exit (#3).
  - Determinism: identical inputs -> identical output, every run (#11).
  - Execution timing: next_open fills at the FOLLOWING bar's open (#1/#2).
  - Cash sufficiency: position sizing never drives cash negative (#4).
  - No duplicate positions: a held symbol is not re-entered (#5).
"""
import pandas as pd
import numpy as np
import pytest

from engine.simulator import Simulator


@pytest.fixture
def simulator():
    return Simulator()


def _single_symbol(prices, exec_prices=None):
    idx = pd.date_range("2020-01-01", periods=len(prices), freq="D")
    close = pd.DataFrame({"A": [float(x) for x in prices]}, index=idx)
    execdf = close if exec_prices is None else pd.DataFrame(
        {"A": [float(x) for x in exec_prices]}, index=idx
    )
    entries = pd.DataFrame({"A": [False] * len(prices)}, index=idx)
    exits = pd.DataFrame({"A": [False] * len(prices)}, index=idx)
    return close, execdf, entries, exits


# ── #12 Hand-calculation ──────────────────────────────────────────────────────
def test_hand_calc_exact(simulator):
    """Buy@100 day0, sell@130 day3, no costs -> 10000 grows to exactly 13000."""
    close, execdf, entries, exits = _single_symbol([100, 110, 120, 130])
    entries.iloc[0, 0] = True
    exits.iloc[3, 0] = True
    risk = dict(init_cash=10000.0, position_size_pct=100.0,
                skip_position_setting=True, skip_risk_management=True)
    opts = dict(fee_rate=0.0, slippage_rate=0.0, execution_type="same_close")

    pf = simulator.run(close, execdf, entries, exits, risk, opts)
    assert float(pf.value().iloc[-1]) == pytest.approx(13000.0, abs=1e-6)


# ── #3 Trading costs on both sides ────────────────────────────────────────────
def test_costs_applied_both_sides(simulator):
    close, execdf, entries, exits = _single_symbol([100, 110, 120, 130])
    entries.iloc[0, 0] = True
    exits.iloc[3, 0] = True
    risk = dict(init_cash=10000.0, position_size_pct=100.0,
                skip_position_setting=True, skip_risk_management=True)

    gross = float(simulator.run(close, execdf, entries, exits, risk,
                                dict(fee_rate=0.0, slippage_rate=0.0,
                                     execution_type="same_close")).value().iloc[-1])
    pf = simulator.run(close, execdf, entries, exits, risk,
                       dict(fee_rate=0.0015, slippage_rate=0.0020,
                            execution_type="same_close"))
    net = float(pf.value().iloc[-1])

    # Net must be strictly worse than gross — costs are real.
    assert net < gross
    # Slippage moves the fill against us on both legs.
    tr = pf.trades.records_readable
    assert float(tr["Avg Entry Price"].iloc[0]) == pytest.approx(100.0 * 1.0020, rel=1e-6)
    assert float(tr["Avg Exit Price"].iloc[0]) == pytest.approx(130.0 * 0.9980, rel=1e-6)


# ── #11 Determinism ───────────────────────────────────────────────────────────
def test_determinism_identical_runs(simulator):
    close, execdf, entries, exits = _single_symbol([100, 110, 120, 130])
    entries.iloc[0, 0] = True
    exits.iloc[3, 0] = True
    risk = dict(init_cash=10000.0, position_size_pct=100.0,
                skip_position_setting=True, skip_risk_management=True)
    opts = dict(fee_rate=0.0015, slippage_rate=0.0020, execution_type="same_close")

    vals = [float(simulator.run(close, execdf, entries, exits, risk, opts).value().iloc[-1])
            for _ in range(5)]
    assert len(set(vals)) == 1


# ── #1/#2 Execution timing: next_open fills at the FOLLOWING bar's open ─────────
def test_next_open_fills_following_bar_open(simulator):
    idx = pd.date_range("2020-01-01", periods=5, freq="D")
    close = pd.DataFrame({"A": [100., 110., 120., 130., 140.]}, index=idx)
    opn = pd.DataFrame({"A": [101., 111., 121., 131., 141.]}, index=idx)
    # Decision at bar 1 / exit decision at bar 3, then shift(1) as the engine does.
    entries = pd.DataFrame({"A": [False, True, False, False, False]}, index=idx).shift(1, fill_value=False)
    exits = pd.DataFrame({"A": [False, False, False, True, False]}, index=idx).shift(1, fill_value=False)
    risk = dict(init_cash=10000.0, position_size_pct=100.0,
                skip_position_setting=True, skip_risk_management=True)

    pf = simulator.run(close, opn, entries, exits, risk,
                       dict(fee_rate=0.0, slippage_rate=0.0, execution_type="next_open"))
    tr = pf.trades.records_readable
    assert float(tr["Avg Entry Price"].iloc[0]) == pytest.approx(121.0)  # open[2]
    assert float(tr["Avg Exit Price"].iloc[0]) == pytest.approx(141.0)   # open[4]


# ── #4 Cash never negative ────────────────────────────────────────────────────
def test_cash_never_negative(simulator):
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    close = pd.DataFrame({"A": [100., 100., 100.], "B": [50., 50., 50.]}, index=idx)
    entries = pd.DataFrame({"A": [True, False, False], "B": [True, False, False]}, index=idx)
    exits = pd.DataFrame({"A": [False, False, True], "B": [False, False, True]}, index=idx)
    # Request 100% each but cap at 2 positions -> 50% each, never overspends.
    risk = dict(init_cash=10000.0, position_size_pct=100.0, max_positions=2,
                skip_risk_management=True)
    pf = simulator.run(close, close, entries, exits, risk,
                       dict(fee_rate=0.0, slippage_rate=0.0, execution_type="same_close"))
    assert float(pf.cash().min()) >= -1e-6


# ── #5 No duplicate positions ─────────────────────────────────────────────────
def test_no_duplicate_position(simulator):
    close, execdf, entries, exits = _single_symbol([100, 100, 100, 100, 100])
    # Repeated entry signals while already holding — must produce a single trade.
    entries.iloc[0, 0] = True
    entries.iloc[1, 0] = True
    entries.iloc[2, 0] = True
    exits.iloc[4, 0] = True
    risk = dict(init_cash=10000.0, position_size_pct=100.0, max_positions=1,
                skip_risk_management=True)
    pf = simulator.run(close, execdf, entries, exits, risk,
                       dict(fee_rate=0.0, slippage_rate=0.0, execution_type="same_close"))
    assert pf.trades.count() == 1
