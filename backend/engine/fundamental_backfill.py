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
    fill_psr_from_market_cap,
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


def cache_coverage_start(fundamentals: list[dict]) -> pd.Timestamp | None:
    """캐시가 지배하기 시작하는 날 = 가장 이른 공개일(available_from, 없으면 결산일+90일)."""
    starts = []
    for r in fundamentals or []:
        af = pd.to_datetime(r.get("available_from"), errors="coerce")
        if pd.isna(af):
            ye = pd.to_datetime(r.get("year_end"), errors="coerce")
            if pd.isna(ye):
                continue
            af = ye + pd.Timedelta(days=90)
        starts.append(af)
    return min(starts) if starts else None


def rebuild_fundamental_columns(pdf: pd.DataFrame, fundamentals: list[dict]) -> pd.DataFrame:
    """연간 재무 컬럼을 캐시 기준으로 **재구축**한다.

    merge_fundamentals(기존 parquet 값 우선)와 반대로, **캐시가 지배하는 구간(가장 이른
    공개일부터)은 캐시로 만든 시리즈가 NaN까지 포함해 통째로 이긴다** — 잘못된 available_from
    (정정공시 접수일 오염)으로 엉뚱한 연도 값이 채워진 날, 자리표시자를 걷어내 비게 된 연도,
    forward-fill 상한(FUNDAMENTAL_FILL_MAX_MONTHS)을 넘겨 stale하게 남은 날을 전부 캐시대로
    되돌리기 위해서다. 종전의 '값이 있는 날만 덮고 나머지는 보존'은 마지막 두 경우에 옛 값을
    되살렸다(2026-08-17). 캐시가 지배하기 전 날(초기 pykrx 이력 등)만 기존 값을 보존하고,
    PER/PBR/PSR도 같은 규칙으로 갈아 끼운 뒤 PSR 폴백(시총÷매출)을 빈 날에 채운다.
    market_cap·배당 파생 컬럼은 available_from과 무관하므로 건드리지 않는다."""
    if not fundamentals:
        return pdf
    fresh = enrich_ohlcv_with_fundamentals(pdf, fundamentals)
    out = pdf.copy()
    start = cache_coverage_start(fundamentals)
    governed = pd.to_datetime(out["date"]) >= start if start is not None else pd.Series(False, index=out.index)

    for col in ANNUAL_FUNDAMENTAL_KEYS + ANNUAL_FUNDAMENTAL_STATUS_KEYS + ["per", "pbr", "psr"]:
        if col not in fresh.columns:
            continue
        dtype = object if col in ANNUAL_FUNDAMENTAL_STATUS_KEYS else float
        old = out[col] if col in out.columns else pd.Series(np.nan, index=out.index, dtype=dtype)
        out[col] = fresh[col].where(governed, old)  # 지배 구간은 캐시(NaN 포함), 그 전은 기존 값

    out = _fill_roe_from_eps_bps(out)
    # PSR 폴백(시가총액 ÷ 매출액, FR-BT-052k): 지배 구간 밖(기존 값 보존 구간)에서 psr이 비어
    # 있고 revenue가 있는 날을 enrich와 같은 단일 정의로 채운다(SPS로 만든 psr은 불변).
    return fill_psr_from_market_cap(out)


def add_market_cap(out: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Fill a market_cap (억원) column from close × 상장주식수 where currently null.

    결측 행만 채우고 기존 값은 보존한다. 매일 sync가 pykrx 봉을 재무 컬럼 전부 null로
    붙이므로(scripts/sync_data.py) 꼬리 결측은 정상 상태다 — '값이 하나라도 있으면
    통째로 건너뛰기'로 되돌리면 새 봉의 market_cap(→PCR)이 영구 결측이 된다
    (2026-06-26부터 전 종목 꼬리 공백 사고, 2026-08-10 수정).
    """
    if "market_cap" in out.columns and out["market_cap"].notna().all():
        return out
    shares = fetch_shares_outstanding(symbol)
    if not shares or shares <= 0:
        return out
    out = out.copy()
    calc = out["close"].astype(float) * shares / 1e8
    if "market_cap" in out.columns:
        out["market_cap"] = out["market_cap"].combine_first(calc)
    else:
        out["market_cap"] = calc
    return out


def apply_real_market_cap(pdf: pd.DataFrame, caps_eok: pd.Series) -> pd.DataFrame:
    """실측 일별 시가총액(억원, 날짜 인덱스 Series)을 market_cap 컬럼에 병합한다.

    실측이 이긴다 — 기존 값(종가×현재 주식수 근사)을 덮어쓰고, 실측이 없는 날짜만
    기존 값을 보존한다. 0/음수는 '데이터 없음'으로 버린다(상장 종목 시총은 0일 수
    없다 — KRX가 거래정지 등에서 0을 줄 수 있다).
    """
    if caps_eok is None or caps_eok.empty:
        return pdf
    caps = caps_eok[caps_eok > 0]
    caps = caps[~caps.index.duplicated(keep="last")]
    if caps.empty:
        return pdf
    out = pdf.copy()
    dates = pd.to_datetime(out["date"]).dt.normalize()
    mapped = dates.map(caps)
    if "market_cap" in out.columns:
        out["market_cap"] = mapped.combine_first(out["market_cap"].astype(float))
    else:
        out["market_cap"] = mapped
    return out


def refresh_symbol(pdf: pd.DataFrame, symbol: str, *, use_cache: bool = True) -> pd.DataFrame:
    """Fetch + non-destructively merge fundamentals + market_cap for one symbol's OHLCV.

    market_cap을 merge보다 먼저 채운다 — PCR(=시총/영업CF)은 enrich가 market_cap
    컬럼을 보고 계산하므로, 순서가 반대면 새 봉의 PCR이 다음 refresh까지 비어 있다.
    """
    fundamentals = fetch_fundamentals(symbol, use_cache=use_cache)
    withcap = add_market_cap(pdf, symbol)
    return merge_fundamentals(withcap, fundamentals) if fundamentals else withcap
