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
    ANNUAL_FUNDAMENTAL_STATUS_KEYS,
    fetch_fundamentals,
    fetch_shares_outstanding,
    enrich_ohlcv_with_fundamentals,
)

# Annual statement metrics + the price-derived valuation ratios. market_cap is separate.
# 배당 메트릭(dividend_yield/payout_rate)은 dividends 컬럼에서 파생되며, 있으면 enrich가
# 계산한다 — 펀더멘털 refresh가 combine_first로 결측만 채우도록 목록에 포함(기존 값 보존).
FUND_COLS = ANNUAL_FUNDAMENTAL_KEYS + ANNUAL_FUNDAMENTAL_STATUS_KEYS + [
    "per", "pbr", "psr", "dividend_yield", "payout_rate", "dividend_growth",
]
# Sentinel proving the *comprehensive* fundamentals (not just the legacy
# eps/bps/roe/debt_ratio set) are present — used to skip already-processed parquets.
SENTINEL_COL = "roa"


def needs_backfill(pdf: pd.DataFrame) -> bool:
    """True if the comprehensive fundamentals (roa) are absent/empty."""
    return SENTINEL_COL not in pdf.columns or not pdf[SENTINEL_COL].notna().any()


def _fill_roe_from_eps_bps(out: pd.DataFrame) -> pd.DataFrame:
    """ROE = 당기순이익/자본총계 = EPS/BPS (exact). Fill gaps/zeros from EPS & BPS.
    BPS<=0(자본잠식)이면 이 유도식 자체가 무의미하므로 gap을 채우지 않는다(null 유지)."""
    roe_gap = out["roe_or_gpa"].isna() | (out["roe_or_gpa"] == 0.0)
    derivable = roe_gap & out["eps"].notna() & out["bps"].notna() & (out["bps"] > 0)
    out.loc[derivable, "roe_or_gpa"] = out.loc[derivable, "eps"] / out.loc[derivable, "bps"] * 100.0
    return out


def merge_fundamentals(pdf: pd.DataFrame, fundamentals: list[dict]) -> pd.DataFrame:
    """Return ``pdf`` with fundamental gaps filled from ``fundamentals`` (additive)."""
    if not fundamentals:
        return pdf
    enriched = enrich_ohlcv_with_fundamentals(pdf, fundamentals)
    out = pdf.copy()

    for col in FUND_COLS:
        dtype = object if col in ANNUAL_FUNDAMENTAL_STATUS_KEYS else float
        old = out[col] if col in out.columns else pd.Series(np.nan, index=out.index, dtype=dtype)
        new = enriched[col] if col in enriched.columns else pd.Series(np.nan, index=out.index, dtype=dtype)
        out[col] = old.combine_first(new)  # existing wins; fetched fills gaps

    out = _fill_roe_from_eps_bps(out)

    # PER/PBR/PSR: fill only the still-null rows from close ÷ denominator (keep existing).
    # PER/PBR은 분모(순이익/지배주주지분)가 음수면 금융적으로 무의미해 채우지 않는다
    # (PSR은 매출이 항상 양수라는 전제로 기존 방식 유지).
    close = out["close"].astype(float)
    for ratio, denom, positive_only in (("per", "eps", True), ("pbr", "bps", True), ("psr", "sps", False)):
        if denom not in out.columns:
            continue
        denom_ok = (out[denom] > 0) if positive_only else (out[denom] != 0)
        calc = (close / out[denom]).where(out[denom].notna() & denom_ok)
        out[ratio] = out[ratio].combine_first(calc.replace([np.inf, -np.inf], np.nan))
    return out


def rebuild_fundamental_columns(pdf: pd.DataFrame, fundamentals: list[dict]) -> pd.DataFrame:
    """available_from 교정 후 연간 재무 컬럼을 캐시 기준으로 **재구축**한다.

    merge_fundamentals(기존 parquet 값 우선)와 반대로 캐시 유래 시리즈가 이긴다 —
    잘못된 available_from(정정공시 접수일 오염)으로 엉뚱한 연도 값이 채워진 날들을
    고치는 용도다. 캐시가 커버하지 않는 날(초기 pykrx 이력 등)만 기존 값을 보존하고,
    PER/PBR/PSR은 최종 분모(eps/bps/sps)와 정합하도록 캐시 커버 구간에서 재계산한다.
    market_cap·배당 파생 컬럼은 available_from과 무관하므로 건드리지 않는다."""
    if not fundamentals:
        return pdf
    fresh = enrich_ohlcv_with_fundamentals(pdf, fundamentals)
    out = pdf.copy()

    for col in ANNUAL_FUNDAMENTAL_KEYS + ANNUAL_FUNDAMENTAL_STATUS_KEYS:
        if col not in fresh.columns:
            continue
        dtype = object if col in ANNUAL_FUNDAMENTAL_STATUS_KEYS else float
        old = out[col] if col in out.columns else pd.Series(np.nan, index=out.index, dtype=dtype)
        out[col] = fresh[col].combine_first(old)  # fetched wins; existing fills gaps

    out = _fill_roe_from_eps_bps(out)

    # 캐시가 분모를 아는 날은 fresh의 비율을 그대로 쓴다(분모<=0 → null 포함 — 기존
    # 값으로 되살리지 않는다). 분모를 모르는 날만 기존 비율을 보존한다.
    for ratio, denom in (("per", "eps"), ("pbr", "bps"), ("psr", "sps")):
        if ratio not in fresh.columns or denom not in fresh.columns:
            continue
        old = out[ratio] if ratio in out.columns else pd.Series(np.nan, index=out.index, dtype=float)
        out[ratio] = old.where(fresh[denom].isna(), fresh[ratio])
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
