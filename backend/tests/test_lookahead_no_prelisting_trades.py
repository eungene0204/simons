"""Look-ahead guard: bfill() of prices must never let a symbol trade before it
listed (validation finding — back-filled pre-listing prices).

backtest_engine ffill/bfills the price grid so VectorBT sees no NaN, which pulls a
symbol's first listing price *backward* into its pre-listing slots. This test runs
the full engine on a symbol that lists mid-window and asserts it never trades
before its first real data date — proving the available_df masking neutralises the
back-fill leak.
"""
from pathlib import Path

import pandas as pd
import pytest

from backtest_engine import BacktestEngine

_EARLY = pd.bdate_range("2024-01-02", "2024-02-29")   # full-window symbol
_LATE_START = pd.Timestamp("2024-02-01")
_LATE = pd.bdate_range(_LATE_START, "2024-02-29")     # lists 2024-02-01


def _write_parquet(path: Path, dates: pd.DatetimeIndex):
    n = len(dates)
    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.0 + i for i in range(n)],
        "volume": [1_000_000] * n,
        "roe_or_gpa": [0.1] * n,   # present -> no network fundamental enrichment
        "pbr": [1.0] * n,
        "per": [10.0] * n,
    })
    df.to_parquet(path)


@pytest.fixture
def data_dir(tmp_path):
    _write_parquet(tmp_path / "AAAAAA.parquet", _EARLY)
    _write_parquet(tmp_path / "BBBBBB.parquet", _LATE)
    return tmp_path


def test_no_trade_before_listing(data_dir):
    engine = BacktestEngine(data_dir=str(data_dir))
    req = {
        "symbols": ["AAAAAA", "BBBBBB"],
        "universe_id": None,                       # custom set -> no PIT re-resolution
        "period": "FULL",
        "entry": {"logic": "OR", "conditions": [
            {"id": "price", "type": "signal", "params": {"operator": ">", "value": 0}},
        ]},
        "exit": {"logic": "OR", "conditions": []},
        "risk_params": {"init_cash": 10_000_000.0, "max_positions": 2,
                        "allocation_type": "equal", "skip_risk_management": True},
        "options": {"execution_type": "next_open"},
    }
    result = engine.run_backtest(req)

    late_buys = [s for s in result["signals"]
                 if s["symbol"] == "BBBBBB" and s["type"] == "buy"]
    assert late_buys, "expected the late-listing symbol to trade at some point"
    earliest = min(pd.Timestamp(s["date"]) for s in late_buys)
    # The leak would surface as a buy dated before the symbol's first real bar.
    assert earliest >= _LATE_START, (
        f"BBBBBB traded on {earliest} — before its {_LATE_START.date()} listing "
        f"(back-fill look-ahead leak)"
    )


def _base_req(extra_options=None):
    return {
        "symbols": ["AAAAAA", "BBBBBB"],
        "universe_id": None,
        "period": "FULL",
        "entry": {"logic": "OR", "conditions": [
            {"id": "price", "type": "signal", "params": {"operator": ">", "value": 0}},
        ]},
        "exit": {"logic": "OR", "conditions": []},
        "risk_params": {"init_cash": 10_000_000.0, "max_positions": 2,
                        "allocation_type": "equal", "skip_risk_management": True},
        "options": {"execution_type": "next_open", **(extra_options or {})},
    }


def test_same_close_emits_lookahead_warning(data_dir):
    engine = BacktestEngine(data_dir=str(data_dir))
    res = engine.run_backtest(_base_req({"execution_type": "same_close"}))
    assert any("same_close" in w and "룩어헤드" in w for w in res["warnings"]), \
        f"expected same_close look-ahead warning, got: {res['warnings']}"


def test_next_open_has_no_lookahead_warning(data_dir):
    engine = BacktestEngine(data_dir=str(data_dir))
    res = engine.run_backtest(_base_req({"execution_type": "next_open"}))
    assert not any("룩어헤드" in w for w in res["warnings"])
