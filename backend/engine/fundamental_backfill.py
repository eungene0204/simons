"""Shared, non-destructive fundamental refresh — used by both the one-shot backfill
script (scripts/backfill_fundamentals.py) and the daily scheduler sync (sync_data.py
→ enrich_existing_parquet).

"Non-destructive" = existing parquet values are kept; freshly fetched data only fills
gaps (``combine_first``). debt_ratio/roa/유동비율/성장률 등은 채워지고, market_cap은
close × 상장주식수로 더해진다. ROE는 EPS/BPS에서 유도(=당기순이익/자본총계).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .fundamental_fetcher import (
    ANNUAL_FUNDAMENTAL_KEYS,
    fetch_fundamentals,
    fetch_shares_outstanding,
    enrich_ohlcv_with_fundamentals,
)

# Annual statement metrics + the price-derived valuation ratios. market_cap is separate.
FUND_COLS = ANNUAL_FUNDAMENTAL_KEYS + ["per", "pbr", "psr"]
# Sentinel proving the *comprehensive* fundamentals (not just the legacy
# eps/bps/roe/debt_ratio set) are present — used to skip already-processed parquets.
SENTINEL_COL = "roa"


def needs_backfill(pdf: pd.DataFrame) -> bool:
    """True if the comprehensive fundamentals (roa) are absent/empty."""
    return SENTINEL_COL not in pdf.columns or not pdf[SENTINEL_COL].notna().any()


def merge_fundamentals(pdf: pd.DataFrame, fundamentals: list[dict]) -> pd.DataFrame:
    """Return ``pdf`` with fundamental gaps filled from ``fundamentals`` (additive)."""
    if not fundamentals:
        return pdf
    enriched = enrich_ohlcv_with_fundamentals(pdf, fundamentals)
    out = pdf.copy()

    for col in FUND_COLS:
        old = out[col] if col in out.columns else pd.Series(np.nan, index=out.index, dtype=float)
        new = enriched[col] if col in enriched.columns else pd.Series(np.nan, index=out.index, dtype=float)
        out[col] = old.combine_first(new)  # existing wins; fetched fills gaps

    # ROE = 당기순이익/자본총계 = EPS/BPS (exact). Fill remaining gaps from EPS & BPS.
    roe_gap = out["roe_or_gpa"].isna() | (out["roe_or_gpa"] == 0.0)
    derivable = roe_gap & out["eps"].notna() & out["bps"].notna() & (out["bps"] != 0)
    out.loc[derivable, "roe_or_gpa"] = out.loc[derivable, "eps"] / out.loc[derivable, "bps"] * 100.0

    # PER/PBR/PSR: fill only the still-null rows from close ÷ denominator (keep existing).
    close = out["close"].astype(float)
    for ratio, denom in (("per", "eps"), ("pbr", "bps"), ("psr", "sps")):
        if denom not in out.columns:
            continue
        calc = (close / out[denom]).where(out[denom].notna() & (out[denom] != 0))
        out[ratio] = out[ratio].combine_first(calc.replace([np.inf, -np.inf], np.nan))
    return out


def add_market_cap(out: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Fill a market_cap (억원) column from close × 상장주식수 where currently null."""
    if "market_cap" in out.columns and out["market_cap"].notna().any():
        return out
    shares = fetch_shares_outstanding(symbol)
    if not shares or shares <= 0:
        return out
    out = out.copy()
    out["market_cap"] = out["close"].astype(float) * shares / 1e8
    return out


def refresh_symbol(pdf: pd.DataFrame, symbol: str, *, use_cache: bool = True) -> pd.DataFrame:
    """Fetch + non-destructively merge fundamentals + market_cap for one symbol's OHLCV."""
    fundamentals = fetch_fundamentals(symbol, use_cache=use_cache)
    merged = merge_fundamentals(pdf, fundamentals) if fundamentals else pdf
    return add_market_cap(merged, symbol)
