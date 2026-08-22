"""backfill_us_stocks.py — 순수 변환 로직 검증 (네트워크 불필요)."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_us_stocks.py"
_spec = importlib.util.spec_from_file_location("simons_backfill_us", _PATH)
us = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(us)

_KR_SAMPLE = Path(__file__).resolve().parents[2] / "data" / "ohlcv" / "005070.parquet"


@pytest.mark.skipif(not _KR_SAMPLE.exists(), reason="한국 파케이 미러 없음")
def test_columns_match_korean_schema():
    kr_cols = list(pd.read_parquet(_KR_SAMPLE).columns)
    assert us.COLUMNS == kr_cols


def test_split_adjust_factor_applies_only_before_split():
    # 2020-08-31에 4:1 분할 → 그 이전 시점 주식수는 ×4, 이후는 ×1
    splits = pd.Series([4.0], index=pd.DatetimeIndex(["2020-08-31"]))
    at = pd.DatetimeIndex(["2019-01-01", "2020-08-31", "2021-01-01"])
    f = us.split_adjust_factor(splits, at)
    assert f.tolist() == [4.0, 1.0, 1.0]


def test_split_adjust_factor_compounds_multiple_splits():
    splits = pd.Series([2.0, 4.0], index=pd.DatetimeIndex(["2014-06-09", "2020-08-31"]))
    at = pd.DatetimeIndex(["2010-01-01", "2015-01-01", "2021-01-01"])
    f = us.split_adjust_factor(splits, at)
    assert f.tolist() == [8.0, 4.0, 1.0]


def test_ttm_sum_requires_four_quarters():
    q = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0],
                  index=pd.date_range("2024-03-31", periods=5, freq="QE"))
    ttm = us.ttm_sum(q)
    assert np.isnan(ttm.iloc[2])
    assert ttm.iloc[3] == 10.0
    assert ttm.iloc[4] == 14.0


def test_apply_with_lag_defers_and_caps_staleness():
    dates = pd.date_range("2024-01-01", "2026-01-01", freq="D")
    qdf = pd.DataFrame({"v": [7.0]}, index=pd.DatetimeIndex(["2024-03-31"]))
    daily = us.apply_with_lag(dates, qdf, lag_days=60, stale_cap_days=456)
    avail = pd.Timestamp("2024-03-31") + pd.Timedelta(days=60)
    assert np.isnan(daily.loc[avail - pd.Timedelta(days=1), "v"])   # 공시 전 룩어헤드 없음
    assert daily.loc[avail, "v"] == 7.0
    stale = avail + pd.Timedelta(days=456)
    assert daily.loc[stale, "v"] == 7.0
    assert np.isnan(daily.loc[stale + pd.Timedelta(days=1), "v"])   # 15개월 cap


def test_safe_div_masks_nonpositive_denominator():
    num = pd.Series([10.0, 10.0, 10.0])
    den = pd.Series([2.0, 0.0, -5.0])
    out = us.safe_div(num, den)
    assert out.iloc[0] == 5.0
    assert np.isnan(out.iloc[1]) and np.isnan(out.iloc[2])


def _fake_hist(n=300, split_on=None):
    # yfinance history 인덱스는 tz-aware이고 이름이 "Date"다 — 이름 유실 회귀(date=NaT) 방지
    idx = pd.date_range("2023-01-02", periods=n, freq="B", tz="America/New_York", name="Date")
    close = pd.Series(np.linspace(100, 130, n), index=idx)
    hist = pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": 1e6, "Dividends": 0.0, "Stock Splits": 0.0,
    }, index=idx)
    if split_on is not None:
        hist.loc[hist.index[split_on], "Stock Splits"] = 2.0
    return hist


def test_build_daily_frame_market_cap_split_adjusted():
    hist = _fake_hist(n=300, split_on=200)
    split_date = hist.index[200]
    # 실제 주식수: 분할 전 1M, 분할 후 2M (실측이 그대로 들어오는 상황)
    shares = pd.Series([1_000_000.0, 2_000_000.0],
                       index=pd.DatetimeIndex([hist.index[0], split_date]))
    df = us.build_daily_frame(hist, pd.DataFrame(), shares, "Information Technology")
    df = df.set_index("date")
    pre = df.iloc[100]
    post = df.iloc[250]
    # 분할 보정: 분할 전 시총 = close × (1M × 2), 분할 후 = close × 2M → 연속적
    assert pre["market_cap"] == pytest.approx(pre["close"] * 2_000_000 / 1e8)
    assert post["market_cap"] == pytest.approx(post["close"] * 2_000_000 / 1e8)


def test_build_daily_frame_schema_and_change():
    hist = _fake_hist(n=50)
    df = us.build_daily_frame(hist, pd.DataFrame(), pd.Series(dtype=float), "Energy")
    assert list(df.columns) == us.COLUMNS
    assert str(df["date"].dtype) == "datetime64[us]"
    assert df["date"].notna().all()  # 인덱스명 불일치로 date가 전부 NaT였던 회귀
    assert df["sector"].iloc[0] == "Energy"
    expected = (df["close"].iloc[1] / df["close"].iloc[0] - 1) * 100
    assert df["change"].iloc[1] == pytest.approx(expected)
    assert np.isnan(df["change"].iloc[0])
    assert df["eps"].isna().all()  # 재무 없음 → NaN, 크래시 없음


def test_build_quarterly_ratios():
    cols = pd.DatetimeIndex(["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31"])
    inc = pd.DataFrame({c: [100.0, 10.0, 2.0] for c in cols},
                       index=["Total Revenue", "Net Income", "Basic EPS"])
    bs = pd.DataFrame({c: [50.0, 200.0, 150.0, 5.0] for c in cols},
                      index=["Stockholders Equity", "Total Assets",
                             "Total Liabilities Net Minority Interest", "Ordinary Shares Number"])
    cf = pd.DataFrame({c: [20.0] for c in cols}, index=["Operating Cash Flow"])
    q = us.build_quarterly(inc, bs, cf)
    last = q.iloc[-1]
    assert last["revenue_ttm"] == 400.0
    assert last["ni_ttm"] == 40.0
    assert last["eps_ttm"] == 8.0
    assert last["roe"] == pytest.approx(80.0)          # 40/50
    assert last["debt_ratio"] == pytest.approx(300.0)  # 150/50
    assert last["net_margin"] == pytest.approx(10.0)
    assert np.isnan(q.iloc[0]["revenue_ttm"])          # 4분기 미만


def test_split_day_duplicate_stale_shares_glitch_smoothed():
    """분할 당일 Yahoo가 신·구 기준 주식수를 함께 내려줘도(스테일 관측) 시총이 불연속되지 않는다.

    실제 사고: AAPL 2020-08-31 4:1 분할 — 17.1B와 4.28B(구기준)가 같은 날 관측되고
    keep-last가 구기준을 집어 이후 두 달간 시총이 4배 낮게 기록됐다.
    """
    hist = _fake_hist(n=300, split_on=200)
    hist.loc[hist.index[200], "Stock Splits"] = 4.0
    split_date = hist.index[200].tz_localize(None).normalize()
    pre_date = hist.index[100].tz_localize(None).normalize()
    post_date = hist.index[250].tz_localize(None).normalize()
    # 관측: 분할 전 1M → 분할 당일 [4M(신), 1M(스테일 구기준)] → 이후 4M
    shares = pd.Series(
        [1_000_000.0, 4_000_000.0, 1_000_000.0, 4_000_000.0],
        index=pd.DatetimeIndex([pre_date, split_date, split_date, post_date]),
    )
    df = us.build_daily_frame(hist, pd.DataFrame(), shares, "IT").set_index("date")
    for d in (df.index[150], split_date, df.index[220], post_date):
        row = df.loc[d]
        assert row["market_cap"] == pytest.approx(row["close"] * 4_000_000 / 1e8), d


def test_share_class_mismatch_uses_market_shares_for_per_share():
    """BRK-B형: 재무제표 주식수(A 기준)가 시세(B 기준)와 어긋나도 주당지표는 실측 주식수 기준."""
    hist = _fake_hist(n=300)
    dates = hist.index.tz_localize(None).normalize()
    cols = pd.DatetimeIndex(["2022-06-30", "2022-09-30", "2022-12-31", "2023-03-31"])
    inc = pd.DataFrame({c: [1_000_000.0, 100_000.0] for c in cols},
                       index=["Total Revenue", "Net Income"])
    bs = pd.DataFrame({c: [2_000_000.0, 1_000.0] for c in cols},  # A 기준 주식수 1,000주
                      index=["Stockholders Equity", "Ordinary Shares Number"])
    cf = pd.DataFrame({c: [50_000.0] for c in cols}, index=["Operating Cash Flow"])
    qdf = us.build_quarterly(inc, bs, cf)
    shares = pd.Series([1_500_000.0], index=pd.DatetimeIndex([dates[0]]))  # B 기준 실측
    df = us.build_daily_frame(hist, qdf, shares, "Financials").set_index("date")
    last = df.iloc[-1]
    assert last["bps"] == pytest.approx(2_000_000.0 / 1_500_000.0)  # A 기준 1,000주가 아니라 실측
    assert 0 < last["pbr"] < 200_000  # 클래스 불일치였다면 pbr ≈ 0
    assert last["market_cap"] == pytest.approx(last["close"] * 1_500_000 / 1e8)


def test_roe_excludes_minority_interest():
    """비지배지분이 큰 회사(ARES형)에서 ROE가 부풀려지지 않는다.

    분모 Stockholders Equity가 비지배지분을 제외하므로 분자도 지배주주 순이익이어야 한다.
    총 순이익을 쓰면 ROE가 실제의 4배 이상으로 나온다.
    """
    cols = pd.DatetimeIndex(["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"])
    inc = pd.DataFrame({c: [100.0, 25.0, 400.0] for c in cols},
                       index=["Net Income", "Net Income Common Stockholders", "Total Revenue"])
    bs = pd.DataFrame({c: [1_000.0, 2_000.0] for c in cols},
                      index=["Stockholders Equity", "Total Assets"])
    cf = pd.DataFrame({c: [50.0] for c in cols}, index=["Operating Cash Flow"])
    q = us.build_quarterly(inc, bs, cf)
    last = q.iloc[-1]
    assert last["roe"] == pytest.approx(10.0)   # 지배주주 100 / 자본 1,000
    assert last["roa"] == pytest.approx(20.0)   # 전사 400 / 총자산 2,000 (레벨 일치)


def _quarterly_stub(ocf=20_000.0, equity=1_000.0, capex=-5_000.0, fcf=15_000.0):
    cols = pd.DatetimeIndex(["2022-06-30", "2022-09-30", "2022-12-31", "2023-03-31"])
    inc = pd.DataFrame({c: [100_000.0, 10_000.0] for c in cols},
                       index=["Total Revenue", "Net Income"])
    bs = pd.DataFrame({c: [equity, 5_000.0] for c in cols},
                      index=["Stockholders Equity", "Ordinary Shares Number"])
    cf = pd.DataFrame({c: [ocf, -8_000.0, -3_000.0, capex, fcf] for c in cols},
                      index=["Operating Cash Flow", "Investing Cash Flow",
                             "Financing Cash Flow", "Capital Expenditure", "Free Cash Flow"])
    return us.build_quarterly(inc, bs, cf)


def test_cash_flow_amount_columns_populated_in_eok():
    """엔진이 조건으로 읽는 *_cf_amount(억 단위)가 채워진다 — 비면 조건이 조용히 통과된다."""
    hist = _fake_hist(n=300)
    qdf = _quarterly_stub()
    df = us.build_daily_frame(hist, qdf, pd.Series([5_000.0], index=[hist.index[0].tz_localize(None).normalize()]), "IT")
    last = df.iloc[-1]
    for raw_col, eok_col, ttm in [
        ("operating_cash_flow", "operating_cf_amount", 80_000.0),
        ("investing_cash_flow", "investing_cf_amount", -32_000.0),
        ("financing_cash_flow", "financing_cf_amount", -12_000.0),
    ]:
        assert last[raw_col] == pytest.approx(ttm), raw_col          # raw 통화
        assert last[eok_col] == pytest.approx(ttm / 1e8), eok_col    # 억 단위
        assert not np.isnan(last[eok_col])


def test_amount_column_units_match_korean_convention():
    """한국 파케이의 컬럼별 단위 규약(억 vs raw)을 그대로 따른다."""
    hist = _fake_hist(n=300)
    qdf = _quarterly_stub(equity=2_000.0, capex=-5_000.0, fcf=15_000.0)
    df = us.build_daily_frame(hist, qdf, pd.Series([5_000.0], index=[hist.index[0].tz_localize(None).normalize()]), "IT")
    last = df.iloc[-1]
    # raw 통화 그대로인 컬럼
    assert last["total_equity"] == pytest.approx(2_000.0)
    assert last["capex"] == pytest.approx(20_000.0)    # TTM, 양수 규모(KR 규약)
    assert last["fcf"] == pytest.approx(60_000.0)      # TTM
    # 억 단위인 컬럼
    assert last["net_income"] == pytest.approx(40_000.0 / 1e8)
    assert last["revenue"] == pytest.approx(400_000.0 / 1e8)


def test_dividends_are_ex_date_events_not_ttm():
    """dividends는 배당락일에만 값이 있어야 한다 — 엔진이 롤링 합으로 TTM을 만들기 때문."""
    hist = _fake_hist(n=300)
    ex_dates = [hist.index[50], hist.index[113], hist.index[176], hist.index[239]]
    for d in ex_dates:
        hist.loc[d, "Dividends"] = 0.25
    df = us.build_daily_frame(hist, pd.DataFrame(), pd.Series(dtype=float), "IT").set_index("date")
    nonzero = df[df["dividends"] > 0]
    assert len(nonzero) == 4                                  # 매일 TTM이 아니라 이벤트 4건
    assert nonzero["dividends"].tolist() == pytest.approx([0.25] * 4)
    # dividend_yield는 TTM 기준 — 4회 누적 후 1.0달러
    last = df.iloc[-1]
    assert last["dividend_yield"] == pytest.approx(1.0 / last["close"] * 100.0)


def test_annual_growth_and_status_from_annual_statements():
    """성장률은 연간표 YoY로 채우고, 부호 전환은 값 대신 상태코드로 남긴다."""
    cols = pd.DatetimeIndex(["2022-12-31", "2023-12-31", "2024-12-31"])
    inc = pd.DataFrame(
        {cols[0]: [100.0, 10.0], cols[1]: [120.0, -5.0], cols[2]: [150.0, 8.0]},
        index=["Total Revenue", "Net Income"])
    cf = pd.DataFrame({c: [50.0] for c in cols}, index=["Operating Cash Flow"])
    adf = us.build_annual_growth(inc, cf)
    assert adf.loc[cols[1], "revenue_growth"] == pytest.approx(20.0)
    assert adf.loc[cols[2], "revenue_growth"] == pytest.approx(25.0)
    # 흑자(10) → 적자(-5) → 흑자(8): 값 대신 상태코드, 값과 상태는 상호배타
    assert np.isnan(adf.loc[cols[1], "net_income_growth"])
    assert adf.loc[cols[1], "net_income_growth_status"] == "LOSS_TRANSITION"
    assert adf.loc[cols[2], "net_income_growth_status"] == "TURNAROUND"
    assert adf.loc[cols[0], "net_income_growth_status"] is None  # 첫 해 = MISSING_DATA 아님


def test_annual_growth_applied_with_90day_lag():
    """연간 성장률은 회계연도 종료 + 90일부터 반영된다(10-K 제출 기한 보수 가정)."""
    hist = _fake_hist(n=700)
    cols = pd.DatetimeIndex(["2022-12-31", "2023-12-31"])
    inc = pd.DataFrame({cols[0]: [100.0], cols[1]: [120.0]}, index=["Total Revenue"])
    cf = pd.DataFrame({c: [50.0] for c in cols}, index=["Operating Cash Flow"])
    adf = us.build_annual_growth(inc, cf)
    df = us.build_daily_frame(hist, pd.DataFrame(), pd.Series(dtype=float), "IT", adf).set_index("date")
    avail = pd.Timestamp("2023-12-31") + pd.Timedelta(days=us.ANNUAL_LAG_DAYS)
    before = df[df.index < avail]["revenue_growth"]
    after = df[df.index >= avail]["revenue_growth"]
    assert (before != pytest.approx(20.0)).all() or before.isna().all()
    assert after.iloc[0] == pytest.approx(20.0)


def test_capex_stored_as_positive_magnitude():
    """capex는 한국 파케이 규약대로 양수 규모 — yfinance는 현금유출이라 음수로 준다."""
    hist = _fake_hist(n=300)
    qdf = _quarterly_stub(capex=-5_000.0)
    df = us.build_daily_frame(hist, qdf, pd.Series([5_000.0], index=[hist.index[0].tz_localize(None).normalize()]), "IT")
    assert df["capex"].iloc[-1] == pytest.approx(20_000.0)   # |TTM|
    # 투자·재무 현금흐름은 반대로 부호를 살려 둔다(engine/signals.py 계약)
    assert df["investing_cf_amount"].iloc[-1] < 0


def test_status_columns_are_string_typed_even_when_all_null():
    """상태 컬럼은 값이 없어도 문자열 타입이어야 한다 — Null 타입은 한국 스키마와 어긋난다."""
    hist = _fake_hist(n=50)
    df = us.build_daily_frame(hist, pd.DataFrame(), pd.Series(dtype=float), "IT")
    for c in us.STATUS_COLUMNS:
        assert df[c].isna().all()
        assert pd.api.types.is_string_dtype(df[c]), c


def test_merge_share_sources_prefers_yfinance_in_overlap():
    """겹치는 구간은 더 촘촘한 yfinance, 그 이전만 EDGAR로 소급한다."""
    edgar = pd.Series(
        [100.0, 110.0, 120.0, 130.0],
        index=pd.DatetimeIndex(["2009-07-22", "2012-01-15", "2016-04-20", "2018-08-01"]),
    )
    yf = pd.Series([125.0, 135.0], index=pd.DatetimeIndex(["2015-10-28", "2018-07-30"]))
    merged = us.merge_share_sources(yf, edgar)
    assert merged.index.tolist() == pd.DatetimeIndex(
        ["2009-07-22", "2012-01-15", "2015-10-28", "2018-07-30"]).tolist()
    assert merged.tolist() == [100.0, 110.0, 125.0, 135.0]  # 겹침 구간 EDGAR 값 배제


def test_merge_share_sources_handles_missing_side():
    edgar = pd.Series([100.0], index=pd.DatetimeIndex(["2009-07-22"]))
    yf = pd.Series([125.0], index=pd.DatetimeIndex(["2015-10-28"]))
    assert us.merge_share_sources(pd.Series(dtype=float), edgar).tolist() == [100.0]
    assert us.merge_share_sources(yf, pd.Series(dtype=float)).tolist() == [125.0]
    assert us.merge_share_sources(None, None).empty


def test_market_cap_not_backfilled_before_first_observation():
    """최초 실측 이전 시총은 NaN — 후대 주식수로 과거를 지어내지 않는다."""
    hist = _fake_hist(n=300)
    first_obs = hist.index[200].tz_localize(None).normalize()
    shares = pd.Series([1_000_000.0], index=pd.DatetimeIndex([first_obs]))
    df = us.build_daily_frame(hist, pd.DataFrame(), shares, "IT").set_index("date")
    assert df.loc[df.index < first_obs, "market_cap"].isna().all()
    assert df.loc[first_obs, "market_cap"] == pytest.approx(df.loc[first_obs, "close"] * 1_000_000 / 1e8)
    assert df.loc[df.index >= first_obs, "market_cap"].notna().all()


def test_fetch_edgar_shares_merges_concepts(monkeypatch):
    """companyfacts에서 개념을 병합한다 — 기업마다 쓰는 개념이 달라 하나만 보면 커버리지를 잃는다."""
    import types

    payload = {"facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"filed": "2012-05-01", "val": 100.0}]}}},
        "us-gaap": {
            "CommonStockSharesOutstanding": {"units": {"shares": [
                {"filed": "2010-05-06", "val": 90.0},   # dei에 없는 더 이른 관측
                {"filed": "2012-05-01", "val": 999.0},  # 같은 날 → dei 우선
            ]}},
            # 발행총수는 자기주식 포함이라 시총을 부풀린다 — 절대 쓰지 않는다
            "CommonStockSharesIssued": {"units": {"shares": [
                {"filed": "2009-01-01", "val": 7_040.0}]}},
        },
    }}

    monkeypatch.setitem(
        __import__("sys").modules, "requests",
        types.SimpleNamespace(get=lambda url, **kw: types.SimpleNamespace(
            status_code=200, json=lambda: payload)))
    out = us.fetch_edgar_shares("0000021344")
    assert out.index.tolist() == pd.DatetimeIndex(["2010-05-06", "2012-05-01"]).tolist()
    assert out.tolist() == [90.0, 100.0]        # 같은 날은 표지(dei) 값 채택
    assert 7_040.0 not in out.tolist()          # 발행총수(Issued) 미사용


def test_fetch_edgar_shares_empty_on_error(monkeypatch):
    """EDGAR가 404·예외를 내도 빈 시리즈만 돌려주고 백필은 계속된다."""
    import types

    monkeypatch.setitem(
        __import__("sys").modules, "requests",
        types.SimpleNamespace(get=lambda url, **kw: types.SimpleNamespace(
            status_code=404, json=dict)))
    assert us.fetch_edgar_shares("0000000000").empty


def test_rows_without_price_are_dropped():
    """OHLC가 전부 비어 있는 날(Yahoo의 구멍)은 거래일이 아니므로 제외한다."""
    hist = _fake_hist(n=100)
    hole = hist.index[40]
    hist.loc[hole, ["Open", "High", "Low", "Close"]] = np.nan
    hist.loc[hole, "Volume"] = 0.0
    df = us.build_daily_frame(hist, pd.DataFrame(), pd.Series(dtype=float), "IT")
    assert len(df) == 99
    assert df["close"].notna().all()
    assert hole.tz_localize(None).normalize() not in set(df["date"])
    # 구멍 다음 날 등락률은 직전 유효 종가 대비로 이어진다
    after = df[df["date"] == hist.index[41].tz_localize(None).normalize()].iloc[0]
    before_close = hist.loc[hist.index[39], "Close"]
    assert after["change"] == pytest.approx((after["close"] / before_close - 1) * 100)


def test_filter_common_stocks_excludes_non_common():
    """ETF·테스트종목·워런트·권리·SPAC 유닛·우선주·채권 제외, 보통주와 MLP 보통유닛은 유지."""
    listed = pd.DataFrame([
        {"symbol": "AAPL", "name": "Apple Inc. - Common Stock"},
        {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "etf": "Y"},
        {"symbol": "ZZZT", "name": "NASDAQ TEST STOCK", "test_issue": "Y"},
        {"symbol": "AACOW", "name": "Abony Acquisition Corp. I - Warrants"},
        {"symbol": "AACPR", "name": "Apogee Acquisition Corp - Rights"},
        {"symbol": "ALDFU", "name": "Aldel Financial II Inc. - Units"},   # SPAC 유닛
        {"symbol": "BAC$B", "name": "Bank of America - Preferred"},
        {"symbol": "XYZN", "name": "XYZ Inc - 5.5% Notes due 2030"},
        {"symbol": "BABA", "name": "Alibaba - American Depositary Shares"},
        {"symbol": "ARLP", "name": "Alliance Resource Partners, L.P. - Common Units Representing Limited Partnership Interests"},
        {"symbol": "ET", "name": "Energy Transfer LP Common Units"},
        {"symbol": "AB", "name": "AllianceBernstein Holding L.P.  Units"},
        {"symbol": "AAPL", "name": "Apple Inc. - Common Stock"},          # 중복
    ])
    listed["etf"] = listed.get("etf", pd.Series()).fillna("N")
    listed["test_issue"] = listed.get("test_issue", pd.Series()).fillna("N")
    listed["market"] = "NASDAQ"
    out = us.filter_common_stocks(listed)
    assert out["symbol"].tolist() == ["AAPL", "AB", "ARLP", "BABA", "ET"]


def test_yahoo_sector_maps_to_gics_vocabulary():
    """Yahoo 섹터 어휘를 GICS 정본으로 정규화한다 — 섞이면 섹터 필터가 반쪽만 잡는다."""
    # 위키 S&P 500 표가 쓰는 GICS 11섹터를 모두 덮는다
    gics = set(us.YAHOO_TO_GICS.values())
    assert gics == {
        "Information Technology", "Financials", "Health Care", "Consumer Discretionary",
        "Consumer Staples", "Materials", "Industrials", "Energy", "Real Estate",
        "Utilities", "Communication Services",
    }
    assert us.YAHOO_TO_GICS["Technology"] == "Information Technology"
    assert us.YAHOO_TO_GICS["Financial Services"] == "Financials"
    assert us.YAHOO_TO_GICS["Consumer Cyclical"] == "Consumer Discretionary"
    # 매핑에 없는 값은 빈 문자열로 떨어진다(어휘 오염 방지)
    assert us.YAHOO_TO_GICS.get("Shell Companies", "") == ""


def test_to_usd_converts_with_rate_at_each_date():
    """현지 통화 금액을 시점별 환율로 달러 환산 — 환율 없는 시점은 NaN."""
    fx = pd.Series([30.0, 32.0], index=pd.DatetimeIndex(["2024-01-01", "2024-07-01"]))
    values = pd.Series(
        [3_000.0, 3_200.0, 3_200.0],
        index=pd.DatetimeIndex(["2024-03-31", "2024-09-30", "2023-06-30"]),
    )
    out = us.to_usd(values, fx)
    assert out.loc[pd.Timestamp("2024-03-31")] == pytest.approx(100.0)   # 30.0 적용
    assert out.loc[pd.Timestamp("2024-09-30")] == pytest.approx(100.0)   # 32.0 적용
    assert np.isnan(out.loc[pd.Timestamp("2023-06-30")])                 # 환율 이전 → NaN
    assert us.to_usd(values, pd.Series(dtype=float)).isna().all()        # 환율 없음 → 전부 NaN


def test_convert_quarterly_leaves_shares_and_ratios_untouched():
    """금액만 환산하고 주식수·무단위 비율은 건드리지 않는다."""
    cols = pd.DatetimeIndex(["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31"])
    inc = pd.DataFrame({c: [3_000.0, 300.0] for c in cols}, index=["Total Revenue", "Net Income"])
    bs = pd.DataFrame({c: [6_000.0, 100.0] for c in cols},
                      index=["Stockholders Equity", "Ordinary Shares Number"])
    cf = pd.DataFrame({c: [900.0] for c in cols}, index=["Operating Cash Flow"])
    q = us.build_quarterly(inc, bs, cf)
    fx = pd.Series([30.0], index=pd.DatetimeIndex(["2020-01-01"]))
    out = us.convert_quarterly_to_usd(q, fx)
    last_local, last_usd = q.iloc[-1], out.iloc[-1]
    assert last_usd["revenue_ttm"] == pytest.approx(last_local["revenue_ttm"] / 30.0)
    assert last_usd["equity"] == pytest.approx(last_local["equity"] / 30.0)
    assert last_usd["shares_bs"] == pytest.approx(last_local["shares_bs"])   # 주식수 불변
    assert last_usd["net_margin"] == pytest.approx(last_local["net_margin"]) # 비율 불변
    assert last_usd["roe"] == pytest.approx(last_local["roe"])


def test_foreign_issuer_per_is_sane_after_conversion():
    """TSM형 회귀: 달러 주가 ÷ 현지통화 EPS로 PER이 30배 낮게 나오던 문제."""
    hist = _fake_hist(n=300)
    cols = pd.DatetimeIndex(["2022-06-30", "2022-09-30", "2022-12-31", "2023-03-31"])
    # 현지 통화(TWD) 기준: 순이익 3,000, 자본 24,000, 주식수 100주
    inc = pd.DataFrame({c: [30_000.0, 3_000.0] for c in cols}, index=["Total Revenue", "Net Income"])
    bs = pd.DataFrame({c: [24_000.0, 100.0] for c in cols},
                      index=["Stockholders Equity", "Ordinary Shares Number"])
    cf = pd.DataFrame({c: [5_000.0] for c in cols}, index=["Operating Cash Flow"])
    q = us.build_quarterly(inc, bs, cf)
    shares = pd.Series([100.0], index=pd.DatetimeIndex([hist.index[0].tz_localize(None).normalize()]))
    fx = pd.Series([30.0], index=pd.DatetimeIndex(["2020-01-01"]))  # 1 USD = 30 TWD

    local = us.build_daily_frame(hist, q, shares, "IT").iloc[-1]
    usd = us.build_daily_frame(hist, us.convert_quarterly_to_usd(q, fx), shares, "IT").iloc[-1]
    # 환산 전에는 PER이 30배 낮게(=EPS가 30배 크게) 나온다
    assert usd["eps"] == pytest.approx(local["eps"] / 30.0)
    assert usd["per"] == pytest.approx(local["per"] * 30.0)
    assert usd["pbr"] == pytest.approx(local["pbr"] * 30.0)
    assert usd["net_income"] == pytest.approx(local["net_income"] / 30.0)


def test_na_ticker_is_not_parsed_as_missing():
    """Nano Labs의 티커 'NA'가 결측으로 읽혀 심볼이 'nan'이 되던 회귀."""
    import io as _io

    raw = "Symbol|Security Name|ETF|Test Issue\nNA|Nano Labs Ltd - Common Stock|N|N\n"
    df = pd.read_csv(_io.StringIO(raw), sep="|", keep_default_na=False)
    assert df["Symbol"].iloc[0] == "NA"
    df = df.rename(columns={"Security Name": "name", "ETF": "etf", "Test Issue": "test_issue"})
    df["symbol"] = df["Symbol"]
    df["market"] = "NASDAQ"
    assert us.filter_common_stocks(df)["symbol"].tolist() == ["NA"]


def test_growth_is_computed_in_usd_not_local_currency():
    """성장률도 달러 기준 — 통화 가치 하락을 성장으로 세면 성장 스크리닝이 깨진다.

    현지통화로는 매출이 2배로 늘었지만 통화가 절반으로 떨어진 경우(아르헨티나형),
    달러 기준 성장률은 0%여야 한다.
    """
    cols = pd.DatetimeIndex(["2023-12-31", "2024-12-31"])
    inc = pd.DataFrame({cols[0]: [100.0], cols[1]: [200.0]}, index=["Total Revenue"])
    cf = pd.DataFrame({c: [10.0] for c in cols}, index=["Operating Cash Flow"])
    # 환율이 10 → 20 (현지통화 가치 절반)
    fx = pd.Series([10.0, 20.0], index=cols)

    local = us.build_annual_growth(inc, cf)
    assert local.loc[cols[1], "revenue_growth"] == pytest.approx(100.0)   # 현지통화 +100%

    usd = us.build_annual_growth(inc, cf, fx)
    assert usd.loc[cols[1], "revenue_growth"] == pytest.approx(0.0)       # 달러 기준 0%


def test_growth_unchanged_for_usd_reporters():
    """USD 보고 기업은 fx=None이라 성장률이 그대로다."""
    cols = pd.DatetimeIndex(["2023-12-31", "2024-12-31"])
    inc = pd.DataFrame({cols[0]: [100.0], cols[1]: [120.0]}, index=["Total Revenue"])
    cf = pd.DataFrame({c: [10.0] for c in cols}, index=["Operating Cash Flow"])
    out = us.build_annual_growth(inc, cf, None)
    assert out.loc[cols[1], "revenue_growth"] == pytest.approx(20.0)
