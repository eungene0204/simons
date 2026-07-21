"""backfill_delisted_fundamentals 모듈 유닛 테스트.

DART 네트워크 호출 없이 순수 계산 로직(_num, _fundamentals_for)만 검증한다.
자본잠식(equity<=0)이어도 이 스크립트는 원시 부호 그대로(bps=equity/shares 음수 가능)
값을 만들어 낼 뿐이며, PER/PBR/ROE의 null 처리는 이 값을 소비하는
enrich_ohlcv_with_fundamentals(engine/fundamental_fetcher.py)가 담당한다 —
test_fundamental_fetcher.py::test_enrich_capital_impairment_produces_nan_pbr_and_roe 참고.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pandas as pd
import polars as pl
import pytest

from scripts.backfill_delisted_fundamentals import _enrich_parquet, _num, _fundamentals_for


def test_num_parses_comma_separated():
    assert _num("1,234,567") == 1234567.0


def test_num_none_for_invalid():
    assert _num("N/A") is None
    assert _num(None) is None


def test_fundamentals_for_computes_bps_eps_roe_from_dart_financials(monkeypatch):
    import scripts.backfill_delisted_fundamentals as mod

    monkeypatch.setattr(mod, "_fetch_year", lambda corp_code, year: {
        "equity": 1_000_000.0, "debt": 500_000.0, "income": 200_000.0,
    })
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    result = _fundamentals_for("00000000", shares=1000.0, start_year=2020, end_year=2020)

    assert result == [{
        "year_end": "2020-12-31",
        "bps": 1000.0,       # 1,000,000 / 1000
        "eps": 200.0,        # 200,000 / 1000
        "roe_or_gpa": 20.0,  # 200,000 / 1,000,000 * 100
        "debt_ratio": 50.0,  # 500,000 / 1,000,000 * 100
    }]


def test_fundamentals_for_preserves_negative_sign_on_capital_impairment(monkeypatch):
    """자본잠식(equity<0)이어도 이 함수는 원시 부호를 그대로 보존한다 — null 처리는
    이 값을 넘겨받는 enrich_ohlcv_with_fundamentals가 담당하므로 여기서 걸러내지 않는다."""
    import scripts.backfill_delisted_fundamentals as mod

    monkeypatch.setattr(mod, "_fetch_year", lambda corp_code, year: {
        "equity": -500_000.0, "debt": 800_000.0, "income": -300_000.0,
    })
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    result = _fundamentals_for("00000000", shares=1000.0, start_year=2020, end_year=2020)

    assert result[0]["bps"] == pytest.approx(-500.0)
    assert result[0]["eps"] == pytest.approx(-300.0)
    assert result[0]["roe_or_gpa"] == pytest.approx(60.0)  # -300,000/-500,000*100 (raw, 왜곡됨)


def test_fundamentals_for_skips_year_without_equity(monkeypatch):
    import scripts.backfill_delisted_fundamentals as mod

    monkeypatch.setattr(mod, "_fetch_year", lambda corp_code, year: None)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)

    assert _fundamentals_for("00000000", shares=1000.0, start_year=2020, end_year=2020) == []


def test_enrich_parquet_nulls_pbr_roe_for_capital_impaired_delisted_stock(tmp_path, monkeypatch):
    """이 스크립트가 만든 원시(부호 왜곡) bps/roe_or_gpa라도, enrich_ohlcv_with_fundamentals를
    거치면 자본잠식 기간의 PBR/ROE가 null로 정정된다(엔드투엔드 확인)."""
    import scripts.backfill_delisted_fundamentals as mod

    monkeypatch.setattr(mod, "_OHLCV_DIR", tmp_path)
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    pl.from_pandas(pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0,
    })).write_parquet(tmp_path / "DELISTED1.parquet")

    fundamentals = [{
        "year_end": "2023-12-31", "bps": -500.0, "eps": -300.0, "roe_or_gpa": 60.0,
    }]

    _enrich_parquet("DELISTED1", fundamentals)

    result = pl.read_parquet(tmp_path / "DELISTED1.parquet").to_pandas()
    assert result["pbr"].isna().all()
    assert result["roe_or_gpa"].isna().all()
