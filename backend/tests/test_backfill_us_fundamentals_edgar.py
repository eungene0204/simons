"""backfill_us_fundamentals_edgar.py — 분기화·병합 로직 (네트워크 불필요)."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_us_fundamentals_edgar.py"
_spec = importlib.util.spec_from_file_location("simons_edgar_fund", _PATH)
edgar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(edgar)


def _pt(start, end, val, filed="2024-01-01"):
    p = {"end": end, "val": val, "filed": filed}
    if start:
        p["start"] = start
    return p


def test_quarterly_direct_90day_periods():
    s = edgar.quarterly_from_durations([
        _pt("2023-01-01", "2023-03-31", 10.0),
        _pt("2023-04-01", "2023-06-30", 12.0),
    ])
    assert s.tolist() == [10.0, 12.0]


def test_quarterly_ytd_differencing_derives_quarters():
    # YTD 보고(현금흐름 흔한 패턴): 3M, 6M, 9M, FY — 차분으로 Q2·Q3·Q4 유도
    s = edgar.quarterly_from_durations([
        _pt("2023-01-01", "2023-03-31", 10.0),
        _pt("2023-01-01", "2023-06-30", 25.0),
        _pt("2023-01-01", "2023-09-30", 45.0),
        _pt("2023-01-01", "2023-12-31", 70.0),
    ])
    assert s[pd.Timestamp("2023-06-30")] == 15.0
    assert s[pd.Timestamp("2023-09-30")] == 20.0
    assert s[pd.Timestamp("2023-12-31")] == 25.0  # Q4 = FY − 9M


def test_quarterly_direct_wins_over_derived_and_latest_filed_wins():
    s = edgar.quarterly_from_durations([
        _pt("2023-01-01", "2023-06-30", 25.0),
        _pt("2023-01-01", "2023-03-31", 10.0),
        _pt("2023-04-01", "2023-06-30", 14.0),                      # 직접 보고 우선
        _pt("2023-04-01", "2023-06-30", 14.5, filed="2024-06-01"),  # 최신 filed 우선
    ])
    assert s[pd.Timestamp("2023-06-30")] == 14.5


def test_annual_takes_only_fy_windows():
    s = edgar.annual_from_durations([
        _pt("2023-01-01", "2023-12-31", 100.0),
        _pt("2023-01-01", "2023-03-31", 10.0),  # 분기 — 제외
    ])
    assert s.tolist() == [100.0]


def test_instant_series_ignores_durations_and_dedupes():
    s = edgar.instant_series([
        _pt(None, "2023-12-31", 50.0),
        _pt(None, "2023-12-31", 51.0, filed="2024-06-01"),
        _pt("2023-01-01", "2023-12-31", 999.0),  # duration — 제외
    ])
    assert s.tolist() == [51.0]


def test_merged_series_unions_concept_histories():
    # 회사가 보고 개념을 갈아탄 경우(AAPL 매출 사례): 앞 개념이 겹침에서 우선,
    # 뒤 개념이 과거 이력을 채운다
    facts = {"us-gaap": {
        "NewConcept": {"units": {"USD": [_pt("2020-01-01", "2020-03-31", 200.0)]}},
        "OldConcept": {"units": {"USD": [
            _pt("2010-01-01", "2010-03-31", 90.0),
            _pt("2020-01-01", "2020-03-31", 999.0),
        ]}},
    }}
    s = edgar._merged_series(facts, ["NewConcept", "OldConcept"], edgar.quarterly_from_durations)
    assert s[pd.Timestamp("2010-03-31")] == 90.0
    assert s[pd.Timestamp("2020-03-31")] == 200.0


def _synthetic_stored(days=900):
    idx = pd.date_range("2020-01-02", periods=days, freq="B", tz="America/New_York")
    close = pd.Series(np.full(days, 50.0), index=idx)
    hist = pd.DataFrame({
        "Open": close, "High": close, "Low": close, "Close": close,
        "Volume": 1e6, "Dividends": 0.0, "Stock Splits": 0.0,
    })
    shares = pd.Series([1e9], index=pd.DatetimeIndex([idx[0].tz_localize(None).normalize()]))
    return edgar.stocks.build_daily_frame(hist, pd.DataFrame(), shares, "Tech", None)


def test_rebuild_financials_extends_history_and_keeps_prices():
    stored = _synthetic_stored()
    # 2020년 4개 분기 순이익·자본 — TTM이 2021년부터 성립
    ni = [_pt(f"2020-{m:02d}-01", e, 1e9) for m, e in
          [(1, "2020-03-31"), (4, "2020-06-30"), (7, "2020-09-30"), (10, "2020-12-31")]]
    eq = [_pt(None, e, 2e10) for e in ["2020-03-31", "2020-06-30", "2020-09-30", "2020-12-31"]]
    facts = {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": ni}},
        "StockholdersEquity": {"units": {"USD": eq}},
    }}
    merged = edgar.rebuild_financials(stored, facts)
    assert merged is not None and len(merged) == len(stored)
    # 가격·시총은 그대로
    pd.testing.assert_series_equal(merged["close"], stored["close"])
    pd.testing.assert_series_equal(merged["market_cap"], stored["market_cap"])
    # 재무가 생겼다: 2021년(4분기 TTM + 공시 lag 이후) ROE = 1e9*4 / 2e10 = 20%
    row = merged.set_index("date").loc["2021-06-01"]
    assert abs(row["roe_or_gpa"] - 20.0) < 0.5
    assert abs(row["per"] - 50.0 / (4e9 / 1e9)) < 0.5  # PER = 50 / EPS 4


def test_rebuild_financials_returns_none_without_usable_facts():
    stored = _synthetic_stored(days=30)
    assert edgar.rebuild_financials(stored, {"us-gaap": {}}) is None
