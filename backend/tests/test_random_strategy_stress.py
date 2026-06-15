"""Random-strategy stress harness (#14).

Generates many random but valid Simulator configurations (random signals, risk
params, costs, execution modes, rebalancing) over synthetic multi-symbol price
data and asserts the engine stays well-behaved:

  - no exceptions / crashes,
  - terminates (pytest will fail on hang — no silent infinite loops),
  - final NAV is finite and non-negative (long-only can't go below zero),
  - cash never goes negative,
  - the result is deterministic for a given seed.

Run a larger sweep ad hoc:  N_STRESS=5000 pytest tests/test_random_strategy_stress.py
"""
import os
import numpy as np
import pandas as pd
import pytest

from engine.simulator import Simulator

_N = int(os.environ.get("N_STRESS", "300"))


def _random_case(rng: np.random.Generator):
    """Build one random (price, exec, entries, exits, risk, options) case."""
    days = int(rng.integers(20, 120))
    syms = int(rng.integers(1, 6))
    idx = pd.date_range("2018-01-01", periods=days, freq="D")
    cols = [f"S{i}" for i in range(syms)]

    # Geometric random walk, strictly positive prices.
    steps = rng.normal(0.0, 0.02, size=(days, syms))
    close = 100.0 * np.exp(np.cumsum(steps, axis=0))
    close_df = pd.DataFrame(close, index=idx, columns=cols)
    # Open within a small band of close, kept positive.
    open_df = (close_df * (1.0 + rng.normal(0.0, 0.005, size=(days, syms)))).clip(lower=1e-3)

    entries = pd.DataFrame(rng.random((days, syms)) < 0.15, index=idx, columns=cols)
    exits = pd.DataFrame(rng.random((days, syms)) < 0.15, index=idx, columns=cols)

    risk = dict(
        init_cash=float(rng.choice([1e6, 1e7, 5e7])),
        position_size_pct=float(rng.choice([10, 25, 50, 100])),
        max_positions=int(rng.integers(1, syms + 1)),
        stop_loss_pct=float(rng.choice([0, 0, 5, 10])),
        take_profit_pct=float(rng.choice([0, 0, 15, 30])),
        trailing_stop_pct=float(rng.choice([0, 0, 8])),
        max_holding_days=int(rng.choice([0, 0, 5, 20])),
        rebalancing_period=str(rng.choice(["none", "none", "weekly", "monthly"])),
        skip_risk_management=bool(rng.random() < 0.2),
        skip_position_setting=bool(rng.random() < 0.1),
        allocation_type=str(rng.choice(["", "equal"])),
    )
    options = dict(
        fee_rate=float(rng.choice([0.0, 0.0015, 0.003])),
        slippage_rate=float(rng.choice([0.0, 0.002, 0.005])),
        execution_type=str(rng.choice(["same_close", "next_open"])),
    )
    return close_df, open_df, entries, exits, risk, options


def _assert_invariants(pf):
    final = float(pf.value().iloc[-1])
    assert np.isfinite(final), "final NAV is not finite"
    assert final >= -1e-6, "long-only NAV went negative"
    assert float(pf.cash().min()) >= -1e-6, "cash went negative"


def test_random_strategy_stress():
    sim = Simulator()
    failures = []
    for n in range(_N):
        rng = np.random.default_rng(n)  # seeded -> reproducible
        close_df, open_df, entries, exits, risk, options = _random_case(rng)
        try:
            pf = sim.run(close_df, open_df, entries, exits, risk, options)
            _assert_invariants(pf)
        except AssertionError:
            raise
        except Exception as e:  # noqa: BLE001 — surface the exact failing seed
            failures.append((n, repr(e)))
    assert not failures, f"{len(failures)}/{_N} random strategies raised: {failures[:5]}"


def test_random_case_is_deterministic():
    """Same seed -> identical NAV across independent runs."""
    sim = Simulator()
    rng_args = _random_case(np.random.default_rng(12345))
    v1 = float(sim.run(*rng_args).value().iloc[-1])
    v2 = float(sim.run(*rng_args).value().iloc[-1])
    assert v1 == v2
