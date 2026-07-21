"""Tests for the shared fundamental backfill logic (engine.fundamental_backfill).

The KIS/Naver fetcher needs network, so these tests exercise the pure merge logic:
debt_ratio gets populated where it was null, existing values are never overwritten,
and ROE is derived from EPS/BPS where the API leaves it missing. The same logic powers
both the one-shot backfill script and the daily scheduler sync.
"""
import numpy as np
import pandas as pd
import pytest

import engine.fundamental_backfill as bf

# Test helpers use the same private names the old script exposed.
bf._needs_backfill = bf.needs_backfill


def _ohlcv(dates: list[str], **cols) -> pd.DataFrame:
    df = pd.DataFrame({"date": pd.to_datetime(dates), "close": 100.0})
    for k, v in cols.items():
        df[k] = v
    return df


def test_debt_ratio_filled_where_previously_null():
    # 부채비율 컬럼이 전부 null이던 종목 — fetch 결과로 채워져야 한다.
    df = _ohlcv(["2024-06-01", "2024-06-02"], debt_ratio=[np.nan, np.nan])
    funds = [{"year_end": "2023-12-31", "eps": 1000.0, "bps": 5000.0,
              "roe_or_gpa": 20.0, "debt_ratio": 42.0}]
    out = bf.merge_fundamentals(df, funds)
    # 2023 결산 + 90일 공시지연 후 적용 → 2024-06 행에 반영
    assert out["debt_ratio"].notna().all()
    assert out["debt_ratio"].iloc[-1] == pytest.approx(42.0)


def test_existing_values_never_overwritten():
    # 기존 per/roe 값이 있으면 fetch 값으로 덮어쓰지 않는다 (가산).
    df = _ohlcv(["2024-06-01"], per=[7.5], roe_or_gpa=[11.0], eps=[2000.0], bps=[3000.0])
    funds = [{"year_end": "2023-12-31", "eps": 9999.0, "bps": 9999.0,
              "roe_or_gpa": 99.0, "debt_ratio": 30.0}]
    out = bf.merge_fundamentals(df, funds)
    assert out["per"].iloc[0] == pytest.approx(7.5)        # kept
    assert out["roe_or_gpa"].iloc[0] == pytest.approx(11.0)  # kept
    assert out["eps"].iloc[0] == pytest.approx(2000.0)     # kept
    assert out["debt_ratio"].iloc[0] == pytest.approx(30.0)  # newly added


def test_roe_derived_from_eps_bps_when_api_missing_or_zero():
    # API가 ROE=0으로 주거나 비어도 EPS/BPS가 있으면 ROE=EPS/BPS*100로 유도.
    df = _ohlcv(["2024-06-01"], debt_ratio=[np.nan])
    funds = [{"year_end": "2023-12-31", "eps": 1500.0, "bps": 5000.0,
              "roe_or_gpa": 0.0, "debt_ratio": 50.0}]
    out = bf.merge_fundamentals(df, funds)
    assert out["roe_or_gpa"].iloc[0] == pytest.approx(30.0)  # 1500/5000*100


def test_roe_not_derived_when_bps_nonpositive():
    # 자본잠식(BPS<=0)이면 EPS/BPS 유도식 자체가 무의미하므로 ROE를 채우지 않는다.
    df = _ohlcv(["2024-06-01"], debt_ratio=[np.nan])
    funds = [{"year_end": "2023-12-31", "eps": 1500.0, "bps": -5000.0,
              "roe_or_gpa": 0.0, "debt_ratio": 50.0}]
    out = bf.merge_fundamentals(df, funds)
    assert pd.isna(out["roe_or_gpa"].iloc[0])


def test_per_pbr_gap_fill_skips_negative_denominator():
    # gap-fill 경로(per/pbr 컬럼이 아예 없던 경우)도 분모<=0이면 채우지 않는다.
    df = _ohlcv(["2024-06-01"], close=50000.0)
    funds = [{"year_end": "2023-12-31", "eps": -1000.0, "bps": -5000.0}]
    out = bf.merge_fundamentals(df, funds)
    assert pd.isna(out["per"].iloc[0])
    assert pd.isna(out["pbr"].iloc[0])


def test_needs_backfill_detects_missing_sentinel():
    # 종합 펀더멘털 유무는 sentinel 컬럼(roa)으로 판단 — debt_ratio만 있으면 부족.
    assert bf._needs_backfill(_ohlcv(["2024-01-01"]))  # no column
    assert bf._needs_backfill(_ohlcv(["2024-01-01"], debt_ratio=[42.0]))  # old set only
    assert bf._needs_backfill(_ohlcv(["2024-01-01"], roa=[np.nan]))  # all null
    assert not bf._needs_backfill(_ohlcv(["2024-01-01"], roa=[8.0]))  # comprehensive present


def test_new_factors_and_psr_populated():
    # 신규 연간 팩터(roa/유동비율/성장률 등)와 파생 PSR이 채워진다.
    df = _ohlcv(["2024-06-01"], close=100.0)
    funds = [{"year_end": "2023-12-31", "roa": 8.5, "current_ratio": 250.0,
              "revenue_growth": 12.0, "sps": 50.0}]
    out = bf.merge_fundamentals(df, funds)
    assert out["roa"].iloc[-1] == pytest.approx(8.5)
    assert out["current_ratio"].iloc[-1] == pytest.approx(250.0)
    assert out["revenue_growth"].iloc[-1] == pytest.approx(12.0)
    assert out["psr"].iloc[-1] == pytest.approx(100.0 / 50.0)  # close/sps


def test_market_cap_from_shares(monkeypatch):
    monkeypatch.setattr(bf, "fetch_shares_outstanding", lambda s: 1_000_000)
    df = _ohlcv(["2024-06-01"], close=50000.0)
    out = bf.add_market_cap(df, "005930")
    # 50000 × 1,000,000 / 1e8 = 500 (억원)
    assert out["market_cap"].iloc[0] == pytest.approx(500.0)


def test_market_cap_skipped_when_already_present():
    df = _ohlcv(["2024-06-01"], close=50000.0, market_cap=[123.0])
    out = bf.add_market_cap(df, "005930")  # fetch_shares not called
    assert out["market_cap"].iloc[0] == pytest.approx(123.0)


def test_empty_fundamentals_leaves_frame_unchanged():
    df = _ohlcv(["2024-06-01"], per=[7.5])
    out = bf.merge_fundamentals(df, [])
    assert out["per"].iloc[0] == pytest.approx(7.5)


def test_refresh_symbol_merges_and_adds_market_cap(monkeypatch):
    # 일일 스케줄러 sync가 쓰는 공유 진입점 — fetch+merge+market_cap을 한 번에.
    funds = [{"year_end": "2023-12-31", "roa": 7.0, "debt_ratio": 40.0,
              "eps": 1000.0, "bps": 5000.0}]
    monkeypatch.setattr(bf, "fetch_fundamentals", lambda s, use_cache=True: funds)
    monkeypatch.setattr(bf, "fetch_shares_outstanding", lambda s: 1_000_000)
    df = _ohlcv(["2024-06-01"], close=50000.0)
    out = bf.refresh_symbol(df, "005930")
    assert out["roa"].iloc[-1] == pytest.approx(7.0)
    assert out["debt_ratio"].iloc[-1] == pytest.approx(40.0)
    assert out["market_cap"].iloc[-1] == pytest.approx(500.0)  # 50000×1e6/1e8
