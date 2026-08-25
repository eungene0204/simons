"""backfill_us_etf.py — 카탈로그·프레임 계약 검증 (네트워크 불필요)."""

import importlib.util
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_us_etf.py"
_spec = importlib.util.spec_from_file_location("simons_backfill_us_etf", _PATH)
etf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(etf)

# toss_us.is_us_symbol과 같은 형식 — 실시간 레인이 이 형식으로 미국 티커를 판별한다
_US_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def test_catalog_symbols_unique_and_us_format():
    symbols = [c["symbol"] for c in etf.CATALOG]
    assert len(set(symbols)) == len(symbols)
    for s in symbols:
        assert _US_SYMBOL_RE.fullmatch(s), s


def test_catalog_entries_have_required_fields():
    for c in etf.CATALOG:
        for key in ("symbol", "name", "name_kr", "category"):
            assert c.get(key), (c.get("symbol"), key)


def _synthetic_hist(days: int = 400) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=days, freq="B", tz="America/New_York")
    close = pd.Series(np.linspace(100.0, 120.0, days), index=idx)
    hist = pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": 1_000_000.0, "Dividends": 0.0, "Stock Splits": 0.0,
    })
    # 분기 배당락 4회 — dividends는 배당락일에만 찍혀야 한다
    for i in (60, 120, 180, 240):
        if i < days:
            hist.iloc[i, hist.columns.get_loc("Dividends")] = 0.5
    return hist


def test_etf_frame_matches_schema_and_leaves_financials_nan():
    df = etf.build_etf_frame(_synthetic_hist(), shares=None)
    assert list(df.columns) == etf.stocks.COLUMNS

    # 기업 재무 컬럼은 전부 NaN — ETF에 재무 지표를 노출하지 않는 계약의 데이터 단계
    for col in ("per", "pbr", "roe_or_gpa", "debt_ratio", "eps", "revenue",
                "net_income", "operating_cf_amount", "ev"):
        assert df[col].isna().all(), col
    # 주식수 실측이 없으면 시총도 NaN(후대 값으로 지어내지 않는다)
    assert df["market_cap"].isna().all()

    # 가격·배당 파생은 채워진다
    assert df["close"].notna().all()
    assert df["dividends"].sum() == pytest.approx(2.0)
    assert (df["dividends"] > 0).sum() == 4  # 배당락일에만
    ttm_full = df.index[df["date"] >= df["date"].iloc[0] + pd.Timedelta(days=365)]
    assert df.loc[ttm_full, "dividend_yield"].notna().all()


def test_etf_frame_market_cap_from_shares():
    hist = _synthetic_hist(days=30)
    dates = pd.DatetimeIndex(hist.index.tz_localize(None)).normalize()
    shares = pd.Series([1e9], index=dates[:1])
    df = etf.build_etf_frame(hist, shares=shares)
    expected = df["close"] * 1e9 / 1e8  # 억달러
    assert np.allclose(df["market_cap"], expected)


def test_refresh_master_reads_parquet_coverage(tmp_path):
    hist = _synthetic_hist(days=30)
    etf.build_etf_frame(hist, shares=None).to_parquet(tmp_path / "SPY.parquet", index=False)

    master = etf.refresh_master(
        [{"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "name_kr": "S&P500", "category": "지수"},
         {"symbol": "QQQ", "name": "Invesco QQQ Trust", "name_kr": "나스닥100", "category": "지수"}],
        data_dir=tmp_path,
    )
    assert master["counts"] == {"total": 2, "hasOhlcv": 1}
    spy, qqq = master["etfs"]
    assert spy["hasOhlcv"] is True and spy["dataStart"] == "2024-01-02"
    assert qqq["hasOhlcv"] is False and qqq["dataStart"] is None
