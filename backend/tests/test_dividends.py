"""Tests for the dividend total-return prototype (validation finding #8)."""
import numpy as np
import pandas as pd
import polars as pl
import pytest

from engine.dividends import total_return_index, dividend_adjust_factor
from engine.loader import DataLoader


def _series(vals):
    idx = pd.date_range("2020-01-01", periods=len(vals), freq="D")
    return pd.Series([float(v) for v in vals], index=idx)


def test_no_dividends_is_identity():
    close = _series([100, 110, 120])
    div = _series([0, 0, 0])
    tri = total_return_index(close, div)
    assert np.allclose(tri.to_numpy(), close.to_numpy())
    assert np.allclose(dividend_adjust_factor(close, div).to_numpy(), 1.0)


def test_total_return_includes_reinvested_dividend():
    # Flat price 100, a 5/share dividend on bar 1 -> total return that bar is
    # (100 + 5) / 100 = 5%. TRI rebased to 100 -> [100, 105, 105].
    close = _series([100, 100, 100])
    div = _series([0, 5, 0])
    tri = total_return_index(close, div)
    assert tri.iloc[0] == pytest.approx(100.0)
    assert tri.iloc[1] == pytest.approx(105.0)
    assert tri.iloc[2] == pytest.approx(105.0)


def test_total_return_beats_price_return_over_window():
    rng = np.random.default_rng(0)
    px = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 50)))
    close = _series(px)
    div = _series([0.0] * 50)
    div.iloc[10] = 2.0
    div.iloc[30] = 3.0
    tri = total_return_index(close, div)
    price_ret = close.iloc[-1] / close.iloc[0]
    total_ret = tri.iloc[-1] / tri.iloc[0]
    assert total_ret > price_ret  # dividends add to performance


def test_loader_opt_in_is_noop_without_dividend_column():
    """preprocess_data must be unchanged when no dividends column exists."""
    pdf = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=3, freq="D").astype(str),
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.0, 101.0, 102.0],
        "volume": [1000, 1000, 1000],
    })
    loader = DataLoader(data_dir="/nonexistent")
    df_pl = pl.from_pandas(pdf)
    base = loader.preprocess_data(df_pl, apply_dividends=False)
    opted = loader.preprocess_data(df_pl, apply_dividends=True)
    assert np.allclose(base["close"].to_numpy(), opted["close"].to_numpy())


def test_loader_applies_dividends_when_present():
    pdf = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=3, freq="D").astype(str),
        "open": [100.0, 100.0, 100.0],
        "high": [100.0, 100.0, 100.0],
        "low": [100.0, 100.0, 100.0],
        "close": [100.0, 100.0, 100.0],
        "volume": [1000, 1000, 1000],
        "dividends": [0.0, 5.0, 0.0],
    })
    loader = DataLoader(data_dir="/nonexistent")
    df_pl = pl.from_pandas(pdf)
    out = loader.preprocess_data(df_pl, apply_dividends=True)
    # Flat price + 5 dividend on bar 1 -> adjusted close steps up 5%.
    assert out["close"].iloc[0] == pytest.approx(100.0)
    assert out["close"].iloc[1] == pytest.approx(105.0)
    assert out["close"].iloc[2] == pytest.approx(105.0)
