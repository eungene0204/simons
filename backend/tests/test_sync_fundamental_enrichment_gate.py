"""scripts/sync_data.needs_fundamental_enrichment — 야간 보강 스킵 판정.

배경(2026-08-08): OHLCV 갱신이 새로 붙인 봉은 재무 컬럼이 null인데(pykrx 응답에 없어
기존 컬럼 기준으로 None을 채운다), 스킵 판정이 `roa.notna().any()`라 한 행이라도 값이
있으면 영구 스킵됐다. 그래서 새 봉의 null이 캐시 만료(90일) 전까지 채워지지 않았고,
최근 구간의 재무 필터·랭킹이 종목에 따라 통째로 비었다. 마지막 행 기준으로 바꾼다.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts import sync_data


def _write(tmp_path, roa_values):
    path = tmp_path / "005930.parquet"
    pd.DataFrame({
        "date": pd.to_datetime(["2026-08-05", "2026-08-06", "2026-08-07"]),
        "close": [70_000.0, 71_000.0, 72_000.0],
        "roa": roa_values,
    }).to_parquet(path)
    return str(path)


@pytest.fixture
def valid_cache(monkeypatch):
    monkeypatch.setattr(sync_data, "_read_cache", lambda symbol: [{"year_end": "2025-12-31"}])


def test_newly_appended_null_row_is_enriched(tmp_path, valid_cache):
    """오늘 붙은 봉이 null이면 보강한다 — 종전에는 영구 스킵됐다."""
    path = _write(tmp_path, [5.0, 5.0, None])
    assert sync_data.needs_fundamental_enrichment(path, "005930") is True


def test_fully_enriched_symbol_is_skipped(tmp_path, valid_cache):
    """마지막 행까지 채워져 있으면 건너뛴다(불필요한 재작업 방지)."""
    path = _write(tmp_path, [5.0, 5.0, 5.2])
    assert sync_data.needs_fundamental_enrichment(path, "005930") is False


def test_symbol_without_roa_column_is_enriched(tmp_path, valid_cache):
    """구버전 컬럼만 가진 종목은 신규 팩터를 받아야 한다(기존 계약 유지)."""
    path = tmp_path / "005930.parquet"
    pd.DataFrame({
        "date": pd.to_datetime(["2026-08-07"]), "close": [70_000.0],
    }).to_parquet(path)
    assert sync_data.needs_fundamental_enrichment(str(path), "005930") is True


def test_expired_cache_forces_enrichment(tmp_path, monkeypatch):
    """캐시가 만료되면 마지막 행이 차 있어도 다시 받아온다(기존 계약 유지)."""
    monkeypatch.setattr(sync_data, "_read_cache", lambda symbol: None)
    path = _write(tmp_path, [5.0, 5.0, 5.2])
    assert sync_data.needs_fundamental_enrichment(path, "005930") is True
