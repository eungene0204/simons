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


def test_market_cap_skipped_when_fully_present(monkeypatch):
    # 전량 채워져 있으면 네트워크 조회 없이 no-op.
    def _boom(s):
        raise AssertionError("fetch_shares_outstanding must not be called")
    monkeypatch.setattr(bf, "fetch_shares_outstanding", _boom)
    df = _ohlcv(["2024-06-01"], close=50000.0, market_cap=[123.0])
    out = bf.add_market_cap(df, "005930")
    assert out["market_cap"].iloc[0] == pytest.approx(123.0)


def test_market_cap_gap_filled_on_appended_rows(monkeypatch):
    # 재발 회귀(2026-06-26 꼬리 공백 사고): 매일 sync가 null 재무 컬럼으로 붙인 새 봉 —
    # 기존 값은 보존하고 결측 행만 close×상장주식수로 채운다. 옛 가드('값이 하나라도
    # 있으면 통째로 스킵')는 이 케이스에서 영구 결측을 만들었다.
    monkeypatch.setattr(bf, "fetch_shares_outstanding", lambda s: 1_000_000)
    df = _ohlcv(["2026-06-25", "2026-06-26"], close=[50000.0, 60000.0],
                market_cap=[123.0, np.nan])
    out = bf.add_market_cap(df, "005930")
    assert out["market_cap"].iloc[0] == pytest.approx(123.0)  # kept
    assert out["market_cap"].iloc[1] == pytest.approx(600.0)  # 60000×1e6/1e8


def test_refresh_symbol_fills_pcr_on_appended_null_tail(monkeypatch):
    # 재발 회귀: 새 봉은 market_cap·pcr 모두 null로 붙는다. 한 번의 refresh 안에서
    # 시총이 먼저 채워지고 그 시총으로 PCR(=시총×1e8/영업CF)까지 계산돼야 한다
    # (순서가 반대면 PCR이 다음 refresh까지 하루 이상 비어 있다).
    funds = [{"year_end": "2025-12-31", "available_from": "2026-03-15",
              "roa": 7.0, "operating_cash_flow": 5e10}]
    monkeypatch.setattr(bf, "fetch_fundamentals", lambda s, use_cache=True: funds)
    monkeypatch.setattr(bf, "fetch_shares_outstanding", lambda s: 1_000_000)
    df = _ohlcv(["2026-06-25", "2026-06-26"], close=[50000.0, 60000.0],
                market_cap=[500.0, np.nan], pcr=[9.9, np.nan])
    out = bf.refresh_symbol(df, "005930")
    assert out["market_cap"].iloc[-1] == pytest.approx(600.0)
    assert out["pcr"].iloc[-1] == pytest.approx(600.0 * 1e8 / 5e10)  # 1.2
    assert out["pcr"].iloc[0] == pytest.approx(9.9)  # 기존 값 보존 (재계산 1.0으로 덮지 않음)


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


# ── apply_real_market_cap / recompute_pcr (실측 시총 재구축, 엔진 v13.0) ──

def test_real_market_cap_wins_and_uncovered_dates_keep_old():
    # 실측이 기존 근사를 덮어쓰고, 실측이 없는 날짜만 기존 값을 보존한다.
    df = _ohlcv(["2020-01-02", "2020-01-03"], market_cap=[100.0, 200.0])
    caps = pd.Series([150.0], index=pd.to_datetime(["2020-01-02"]))
    out = bf.apply_real_market_cap(df, caps)
    assert out["market_cap"].iloc[0] == pytest.approx(150.0)  # 실측 승
    assert out["market_cap"].iloc[1] == pytest.approx(200.0)  # 미커버 보존


def test_real_market_cap_drops_nonpositive_and_handles_missing_column():
    # 0/음수 실측은 '데이터 없음'(거래정지 등) — 버리고 기존 값 보존. 컬럼이 없으면 생성.
    df = _ohlcv(["2020-01-02", "2020-01-03"], market_cap=[100.0, np.nan])
    caps = pd.Series([0.0, 300.0], index=pd.to_datetime(["2020-01-02", "2020-01-03"]))
    out = bf.apply_real_market_cap(df, caps)
    assert out["market_cap"].iloc[0] == pytest.approx(100.0)  # 0 → 기존 보존
    assert out["market_cap"].iloc[1] == pytest.approx(300.0)

    no_col = _ohlcv(["2020-01-03"])
    out2 = bf.apply_real_market_cap(no_col, caps)
    assert out2["market_cap"].iloc[0] == pytest.approx(300.0)


def test_recompute_pcr_follows_market_cap_basis():
    # PCR은 (억원×1e8)/영업CF(raw 원), OCF<=0은 null — enrich와 같은 단일 정의.
    from engine.fundamental_fetcher import recompute_pcr
    df = _ohlcv(
        ["2020-01-02", "2020-01-03", "2020-01-06"],
        market_cap=[500.0, 500.0, np.nan],
        operating_cash_flow=[1e10, -1e10, 1e10],
        pcr=[99.0, 99.0, 99.0],
    )
    out = recompute_pcr(df)
    assert out["pcr"].iloc[0] == pytest.approx(500.0 * 1e8 / 1e10)  # 5.0
    assert pd.isna(out["pcr"].iloc[1])  # OCF 음수 → null (99.0 되살리지 않음)
    assert pd.isna(out["pcr"].iloc[2])  # 시총 결측 → null


# ── rebuild_fundamental_columns (available_from 교정 후 재구축) ──

def test_rebuild_overwrites_stale_values_in_cache_covered_window():
    # 오염된 available_from(정정일) 탓에 낡은 연도 값이 채워졌던 날들 — 교정 캐시로
    # 재구축하면 캐시 값이 이긴다(merge_fundamentals의 기존값 우선과 반대).
    df = _ohlcv(["2022-02-03"], eps=[100.0], per=[1.0])  # stale FY2017 값이 남은 상태
    funds = [{"year_end": "2020-12-31", "available_from": "2021-03-15", "eps": 200.0}]
    out = bf.rebuild_fundamental_columns(df, funds)
    assert out["eps"].iloc[0] == pytest.approx(200.0)
    assert out["per"].iloc[0] == pytest.approx(100.0 / 200.0)  # close/eps 재계산


def test_rebuild_preserves_history_outside_cache_coverage():
    # 캐시 최초 available_from 이전 날들(초기 pykrx 이력)은 기존 값을 보존한다.
    df = _ohlcv(["2020-06-01"], eps=[100.0], per=[1.0])
    funds = [{"year_end": "2020-12-31", "available_from": "2021-03-15", "eps": 200.0}]
    out = bf.rebuild_fundamental_columns(df, funds)
    assert out["eps"].iloc[0] == pytest.approx(100.0)
    assert out["per"].iloc[0] == pytest.approx(1.0)


def test_rebuild_nulls_per_for_nonpositive_eps_instead_of_resurrecting_old():
    # 캐시가 적자(eps<=0)를 아는 날은 PER=null이 최종값 — 기존 값으로 되살리지 않는다.
    df = _ohlcv(["2022-02-03"], eps=[100.0], per=[1.0])
    funds = [{"year_end": "2020-12-31", "available_from": "2021-03-15", "eps": -50.0}]
    out = bf.rebuild_fundamental_columns(df, funds)
    assert out["eps"].iloc[0] == pytest.approx(-50.0)
    assert pd.isna(out["per"].iloc[0])


# ── PSR 폴백(시가총액 ÷ 매출액, FR-BT-052k) — SPS를 모르는 날만 채우고 SPS 기반 값은 불변 ──

def test_rebuild_fills_psr_from_market_cap_only_where_sps_unknown():
    # KIS SPS가 0 자리표시자라 캐시에 sps가 없는 회사 — 종전엔 psr null 영구 공백.
    df = _ohlcv(["2022-04-01", "2022-04-04"], market_cap=[3000.0, 3300.0], psr=[np.nan, np.nan])
    funds = [{"year_end": "2021-12-31", "available_from": "2022-03-15", "eps": 1000.0, "revenue": 1500.0}]
    out = bf.rebuild_fundamental_columns(df, funds)
    assert out["revenue"].iloc[0] == pytest.approx(1500.0)
    assert out["psr"].iloc[0] == pytest.approx(2.0)   # 3000 / 1500
    assert out["psr"].iloc[1] == pytest.approx(2.2)


def test_rebuild_keeps_sps_based_psr_over_fallback():
    # SPS를 아는 날은 종가÷SPS가 정의 — 매출 폴백이 덮어쓰지 않는다.
    df = _ohlcv(["2022-04-01"], market_cap=[3000.0], psr=[np.nan])
    funds = [{"year_end": "2021-12-31", "available_from": "2022-03-15", "sps": 50.0, "revenue": 1500.0}]
    out = bf.rebuild_fundamental_columns(df, funds)
    assert out["psr"].iloc[0] == pytest.approx(100.0 / 50.0)  # close/sps, not 3000/1500


def test_rebuild_psr_fallback_skips_nonpositive_revenue():
    df = _ohlcv(["2022-04-01"], market_cap=[3000.0], psr=[np.nan])
    funds = [{"year_end": "2021-12-31", "available_from": "2022-03-15", "revenue": 0.0}]
    out = bf.rebuild_fundamental_columns(df, funds)
    assert pd.isna(out["psr"].iloc[0])
