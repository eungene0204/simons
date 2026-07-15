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


_TRADING_DAYS_PER_YEAR = 252


def trailing_dividend_yield(
    close: pd.Series, dividends: pd.Series, window: int = _TRADING_DAYS_PER_YEAR
) -> pd.Series:
    """배당수익률(%) = 최근 12개월(TTM) 주당 현금배당 합 ÷ 종가 × 100.

    ``dividends``는 ex-date별 주당 현금배당(그 외 0)이라, 롤링 합이 곧 TTM DPS다.
    전진충전이 아니라 롤링 합이므로, 배당을 멈춘 종목은 1년 안에 자연히 0으로 감쇠한다
    (전진충전 방식이 겪는 '무배당 연도를 직전 배당으로 오인'하는 문제를 피한다).

    Args:
        close: 종가(양수), dividends와 같은 인덱스.
        dividends: ex-date별 주당 현금배당(그 외 0), 분할조정 상태.
        window: TTM 창(거래일). 기본 252.

    Returns:
        배당수익률(%) 시리즈. 종가가 무효면 NaN, 최근 배당이 없으면 0.0.
    """
    ttm = dividends.fillna(0.0).rolling(window, min_periods=1).sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        y = ttm / close.replace(0.0, np.nan).astype(float) * 100.0
    return y.replace([np.inf, -np.inf], np.nan)


def dividend_growth_yoy(
    dividends: pd.Series, window: int = _TRADING_DAYS_PER_YEAR
) -> pd.Series:
    """배당성장률(%) = 최근 12개월(TTM) 주당배당 ÷ 직전 12개월 주당배당 − 1, × 100.

    ``dividends``는 ex-date별 주당 현금배당이라, 롤링 합(TTM)의 전년 대비 변화율이 곧
    배당 성장률이다. 배당을 처음 시작한 종목(직전 TTM=0)은 성장률이 정의되지 않아 NaN,
    배당을 멈춘 종목(현 TTM=0, 직전>0)은 −100%가 된다.

    Args:
        dividends: ex-date별 주당 현금배당(그 외 0), 분할조정 상태.
        window: TTM 창(거래일). 기본 252. 직전 TTM은 window만큼 shift.

    Returns:
        배당성장률(%) 시리즈. 직전 배당이 없으면(0 기준 성장 정의 불가) NaN.
    """
    ttm = dividends.fillna(0.0).rolling(window, min_periods=1).sum()
    ttm_prior = ttm.shift(window)
    with np.errstate(divide="ignore", invalid="ignore"):
        g = (ttm / ttm_prior.where(ttm_prior > 0) - 1.0) * 100.0
    return g.replace([np.inf, -np.inf], np.nan)


def dividend_payout_ratio(
    dividends: pd.Series, eps: pd.Series, window: int = _TRADING_DAYS_PER_YEAR
) -> pd.Series:
    """배당성향(%) = TTM 주당 현금배당 합 ÷ 주당순이익(EPS) × 100.

    EPS가 결측이거나 0 이하(적자)면 성향이 정의되지 않아 NaN을 반환한다.
    """
    ttm = dividends.fillna(0.0).rolling(window, min_periods=1).sum()
    eps_pos = eps.where(eps.astype(float) > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = ttm / eps_pos * 100.0
    return p.replace([np.inf, -np.inf], np.nan)


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
