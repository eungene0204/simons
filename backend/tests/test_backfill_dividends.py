"""Tests for scripts/backfill_dividends.py (dividend backfill, offline).

The pykrx provider needs network/KRX creds, so these tests inject a stub provider
and exercise the pure series-building logic + the parquet round-trip end to end.
"""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

# Load the script module by path (scripts/ is not a package).
_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_dividends.py"
_spec = importlib.util.spec_from_file_location("backfill_dividends", _SCRIPT)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)


# ── pure build_dividend_series ────────────────────────────────────────────────
def test_dividend_placed_on_last_trading_day_of_year():
    dates = pd.DatetimeIndex(pd.to_datetime([
        "2021-12-29", "2021-12-30", "2022-01-03", "2022-12-28", "2022-12-29",
    ]))
    series = bf.build_dividend_series(dates, {2021: 361.0, 2022: 1444.0})
    assert series.loc["2021-12-30"] == 361.0   # last 2021 trading day
    assert series.loc["2022-12-29"] == 1444.0  # last 2022 trading day
    assert series.loc["2021-12-29"] == 0.0
    assert series.loc["2022-01-03"] == 0.0
    assert series.sum() == pytest.approx(1805.0)


def test_skips_zero_and_missing_years():
    dates = pd.DatetimeIndex(pd.to_datetime(["2020-12-30", "2021-12-30"]))
    series = bf.build_dividend_series(dates, {2020: 0.0, 2021: 100.0, 2099: 500.0})
    assert series.sum() == pytest.approx(100.0)  # zero skipped, 2099 not in index


def test_empty_inputs():
    assert bf.build_dividend_series(pd.DatetimeIndex([]), {2021: 100.0}).empty
    dates = pd.DatetimeIndex(pd.to_datetime(["2021-12-30"]))
    assert bf.build_dividend_series(dates, {}).sum() == 0.0


def test_pykrx_provider_returns_empty_on_failure():
    # No network/creds in test env -> graceful empty dict, never raises.
    assert bf.annual_dps_from_pykrx("000000", "20200101", "20201231") == {}


# ── KIS provider parsing (pure, no network) ───────────────────────────────────
def test_parse_kis_dividends_sums_cash_per_year():
    records = [
        {"record_date": "20211230", "per_sto_divi_amt": "361"},   # 2021 기말
        {"record_date": "20210630", "per_sto_divi_amt": "361"},   # 2021 중간 -> 합산
        {"record_date": "20221230", "per_sto_divi_amt": "1,444"}, # 콤마 포함
        {"record_date": "20231230", "per_sto_divi_amt": "0"},     # 0 -> 제외
        {"record_date": "", "per_sto_divi_amt": "100"},            # 날짜 없음 -> 제외
    ]
    out = bf._parse_kis_dividends(records)
    assert out == {2021: 722.0, 2022: 1444.0}


def test_parse_kis_dividends_handles_empty():
    assert bf._parse_kis_dividends([]) == {}
    assert bf._parse_kis_dividends(None) == {}


def test_parse_kis_dividends_split_adjusts_via_face_val():
    # Samsung 50:1 split (face 5000 -> 100): pre-split DPS must be /50 to match
    # the split-adjusted parquet prices. 17700 * (100/5000) = 354.
    records = [
        {"record_date": "20171231", "per_sto_divi_amt": "21500", "face_val": "5000"},
        {"record_date": "20241231", "per_sto_divi_amt": "363", "face_val": "100"},
    ]
    out = bf._parse_kis_dividends(records)
    assert out[2017] == pytest.approx(430.0)   # 21500 * (100/5000), back-adjusted
    assert out[2024] == pytest.approx(363.0)   # current basis unchanged


def test_parse_kis_dividends_no_face_val_is_unadjusted():
    records = [{"record_date": "20211230", "per_sto_divi_amt": "1444"}]
    assert bf._parse_kis_dividends(records) == {2021: 1444.0}


def test_kis_provider_composes_parser_over_fetch(monkeypatch):
    # Offline: stub the network layer; verify annual_dps_from_kis parses it.
    monkeypatch.setattr(bf, "_kis_dividend_records", lambda sym, s, e: [
        {"record_date": "20211230", "per_sto_divi_amt": "1444"},
    ])
    assert bf.annual_dps_from_kis("005930", "20200101", "20231231") == {2021: 1444.0}


def test_kis_provider_graceful_when_fetch_empty(monkeypatch):
    monkeypatch.setattr(bf, "_kis_dividend_records", lambda sym, s, e: [])
    assert bf.annual_dps_from_kis("005930", "20200101", "20231231") == {}


def test_kis_is_default_provider():
    assert bf.PROVIDERS["kis"] is bf.annual_dps_from_kis


# ── end-to-end parquet round-trip with a stub provider ────────────────────────
def _make_parquet(tmp_path: Path) -> Path:
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", "2022-12-31", freq="B").astype(str),
        "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000,
    })
    p = tmp_path / "005930.parquet"
    df.to_parquet(p)
    return p


def test_dry_run_does_not_write(tmp_path):
    p = _make_parquet(tmp_path)
    stub = lambda sym, s, e: {2021: 361.0, 2022: 1444.0}  # noqa: E731
    stats = bf.backfill_file(p, stub, dry_run=True)
    assert stats["status"] == "dry-run"
    assert stats["events"] == 2
    # File on disk must be untouched (no dividends column persisted).
    assert "dividends" not in pd.read_parquet(p).columns


def test_write_adds_dividends_column(tmp_path):
    p = _make_parquet(tmp_path)
    stub = lambda sym, s, e: {2021: 361.0, 2022: 1444.0}  # noqa: E731
    stats = bf.backfill_file(p, stub, dry_run=False)
    assert stats["status"] == "written"
    out = pd.read_parquet(p)
    assert "dividends" in out.columns
    assert out["dividends"].sum() == pytest.approx(1805.0)
    assert (out["dividends"] > 0).sum() == 2


def test_backfilled_parquet_feeds_total_return_engine(tmp_path):
    """The backfilled column must be consumable by loader total-return path."""
    import polars as pl
    from engine.loader import DataLoader

    p = _make_parquet(tmp_path)
    bf.backfill_file(p, lambda sym, s, e: {2021: 5.0}, dry_run=False)

    loader = DataLoader(data_dir=str(tmp_path))
    out = loader.preprocess_data(pl.read_parquet(p), apply_dividends=True)
    # Flat 100 price + a 5/share dividend in 2021 -> total-return close steps up.
    assert float(out["close"].iloc[-1]) > 100.0
