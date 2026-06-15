"""Dividend total-return adjustment (prototype).

The OHLCV feed carries only split-adjusted prices, so backtests are price-return
and understate long-horizon performance (validation finding #8). This module
turns a raw close series + a per-share dividend series into a *total-return*
series via standard back-adjustment, so reinvested dividends are reflected in the
equity curve while bar-to-bar ratios stay correct.

Pure functions only (no vectorbt / polars) — unit-testable in isolation. Wiring
into the loader is opt-in and a no-op when no dividend data is present, so the
default engine behaviour is unchanged.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def total_return_index(close: pd.Series, dividends: pd.Series) -> pd.Series:
    """Total-return index from a price series and per-share dividends.

    On an ex-dividend bar the holder receives ``div`` per share, so the one-bar
    total return is ``(close_t + div_t) / close_{t-1}``. The returned series is
    rebased to ``close.iloc[0]`` so its scale matches the input prices.

    Args:
        close: positive close prices, datetime-indexed.
        dividends: per-share cash dividend on each ex-date (0 elsewhere),
            aligned to ``close`` (missing dates treated as 0).

    Returns:
        Total-return index, same index as ``close``.
    """
    if len(close) == 0:
        return close.astype(float).copy()
    div = dividends.reindex(close.index).fillna(0.0).to_numpy(dtype=float)
    px = close.to_numpy(dtype=float)
    ret = np.ones(len(px), dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ret[1:] = (px[1:] + div[1:]) / px[:-1]
    ret[~np.isfinite(ret)] = 1.0
    tri = px[0] * np.cumprod(ret)
    return pd.Series(tri, index=close.index)


def dividend_adjust_factor(close: pd.Series, dividends: pd.Series) -> pd.Series:
    """Per-bar back-adjustment factor mapping raw close onto the total-return index.

    ``factor = total_return_index / close``. Multiplying every OHLC column by this
    factor yields a dividend-adjusted (total-return) OHLC block whose ratios match
    reinvested-dividend performance, mirroring how split adjustment is applied.
    """
    tri = total_return_index(close, dividends)
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = tri / close.replace(0.0, np.nan)
    return factor.fillna(1.0)
