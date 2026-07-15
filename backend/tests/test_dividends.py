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


def test_trailing_dividend_yield_ttm_and_decay():
    from engine.dividends import trailing_dividend_yield
    # 252 거래일 창. 3년치 일별, 각 연말 마지막 봉에 300원 배당, 종가 10000 고정.
    idx = pd.bdate_range("2021-01-01", "2023-12-31")
    close = pd.Series(10000.0, index=idx)
    div = pd.Series(0.0, index=idx)
    for yr in (2021, 2022, 2023):
        div.loc[idx[idx.year == yr].max()] = 300.0
    y = trailing_dividend_yield(close, div)
    # 배당 이전 = 0, 첫 ex-date 이후 1년 내 = 3.0%
    assert y.iloc[10] == pytest.approx(0.0)
    mid_2022 = idx[idx.year == 2022][30]
    assert y.loc[mid_2022] == pytest.approx(3.0)


def test_trailing_dividend_yield_decays_when_payment_stops():
    from engine.dividends import trailing_dividend_yield
    idx = pd.bdate_range("2021-01-01", "2023-12-31")
    close = pd.Series(10000.0, index=idx)
    div = pd.Series(0.0, index=idx)
    # 2021년만 배당, 이후 중단 → 2023년엔 TTM 롤오프로 0으로 감쇠(전진충전 방식의 오인 없음)
    div.loc[idx[idx.year == 2021].max()] = 300.0
    y = trailing_dividend_yield(close, div)
    assert y.loc[idx[idx.year == 2023][100]] == pytest.approx(0.0)


def test_dividend_payout_ratio_and_loss_years():
    from engine.dividends import dividend_payout_ratio
    idx = pd.bdate_range("2022-01-01", "2022-12-31")
    div = pd.Series(0.0, index=idx)
    div.iloc[5] = 300.0
    eps = pd.Series(1000.0, index=idx)
    p = dividend_payout_ratio(div, eps)
    assert p.iloc[100] == pytest.approx(30.0)
    # 적자(EPS<=0)면 배당성향 정의 불가 → NaN
    eps_loss = pd.Series(-500.0, index=idx)
    p_loss = dividend_payout_ratio(div, eps_loss)
    assert p_loss.iloc[100] != p_loss.iloc[100]  # NaN


def test_dividend_growth_yoy():
    from engine.dividends import dividend_growth_yoy
    # 2021: 100원, 2022: 120원(+20%). 스크리닝 값은 '가장 최근 확정 연배당'의 전년비이므로
    # 2023년 내내 안정적으로 20%를 보인다(2022 배당이 2021 대비 +20%).
    idx = pd.bdate_range("2021-01-01", "2023-12-31")
    div = pd.Series(0.0, index=idx)
    div.loc[idx[idx.year == 2021].max()] = 100.0
    div.loc[idx[idx.year == 2022].max()] = 120.0
    g = dividend_growth_yoy(div)
    mid_2023 = idx[idx.year == 2023][120]
    assert g.loc[mid_2023] == pytest.approx(20.0)


def test_dividend_growth_first_payer_is_nan():
    from engine.dividends import dividend_growth_yoy
    idx = pd.bdate_range("2021-01-01", "2022-12-31")
    div = pd.Series(0.0, index=idx)
    # 2022년 첫 배당 — 직전(2021) TTM=0 → 성장률 정의 불가 → NaN
    div.loc[idx[idx.year == 2022].max()] = 100.0
    g = dividend_growth_yoy(div)
    mid_2022 = g[idx.year == 2022].iloc[len(g[idx.year == 2022]) // 2]
    assert mid_2022 != mid_2022  # NaN


def test_dividend_growth_cut_is_negative():
    from engine.dividends import dividend_growth_yoy
    idx = pd.bdate_range("2021-01-01", "2023-12-31")
    div = pd.Series(0.0, index=idx)
    div.loc[idx[idx.year == 2021].max()] = 100.0  # 이후 배당 중단
    g = dividend_growth_yoy(div)
    # 2023년: 현 TTM=0, 직전 TTM=100 → -100% (배당 삭감이 명확히 드러남)
    assert g.loc[idx[idx.year == 2023][120]] == pytest.approx(-100.0)
