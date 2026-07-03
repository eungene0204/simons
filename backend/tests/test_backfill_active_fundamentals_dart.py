"""Tests for scripts/backfill_active_fundamentals_dart.py's gap-year detection.

Regression: a parquet with no ``bps`` column at all (never enriched — e.g. REITs like
롯데리츠/한화리츠 whose Naver page has no EPS/BPS table) was treated as "no gap" and
silently skipped, when every year is actually missing.
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "backfill_active_fundamentals_dart.py"
)


@pytest.fixture(scope="module")
def bfa():
    spec = importlib.util.spec_from_file_location("backfill_active_fundamentals_dart", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ohlcv(dates: list[str], **cols) -> pd.DataFrame:
    df = pd.DataFrame({"date": pd.to_datetime(dates), "close": 100.0})
    for k, v in cols.items():
        df[k] = v
    return df


def test_gap_years_missing_bps_column_is_a_full_gap(bfa):
    # bps 컬럼 자체가 없음 (REITs 등 한 번도 enrich된 적 없는 종목).
    df = _ohlcv(["2020-01-02", "2023-06-01"])
    gaps = bfa._gap_years(df)
    assert 2020 in gaps
    assert 2023 in gaps


def test_gap_years_before_dart_floor_excluded(bfa):
    # DART 표준 API는 2015년 이전 데이터를 제공하지 않으므로 그 이전 연도는 갭 목록에서 제외.
    df = _ohlcv(["2010-01-02", "2023-06-01"])
    gaps = bfa._gap_years(df)
    assert 2010 not in gaps
    assert 2023 in gaps


def test_gap_years_partial_null_only_missing_years(bfa):
    # bps가 일부 연도만 채워져 있으면 채워지지 않은 연도만 갭으로 반환.
    df = _ohlcv(
        ["2020-06-01", "2021-06-01", "2022-06-01"],
        bps=[None, 5000.0, None],
    )
    gaps = bfa._gap_years(df)
    assert gaps == [2020, 2022]


def test_gap_years_fully_filled_no_gap(bfa):
    df = _ohlcv(["2020-06-01", "2021-06-01"], bps=[5000.0, 5500.0])
    assert bfa._gap_years(df) == []


def test_gap_years_empty_dataframe(bfa):
    df = pd.DataFrame({"date": pd.to_datetime([]), "close": []})
    assert bfa._gap_years(df) == []
