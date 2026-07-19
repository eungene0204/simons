"""ETF 심볼은 기업 재무제표가 없어 DataLoader가 fundamental enrichment를 건너뛴다.

회귀 배경: ETF 백테스트마다 KIS financial-ratio 등 5개 엔드포인트가 매 종목 헛되이
실패(500)하며 로그 소음+지연이 발생하던 문제(2026-07-19, ETF 유니버스 E2E 검증 중 발견).
"""
import json
import os
import sys

import polars as pl
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine import universe_pit as u
from engine.loader import DataLoader


@pytest.fixture
def synthetic_etf_master(tmp_path, monkeypatch):
    etfs = [{"symbol": "069500", "name": "KODEX 200",
             "dataStart": "2014-01-29", "dataEnd": "2026-07-10", "hasOhlcv": True}]
    path = tmp_path / "etf-master.json"
    path.write_text(json.dumps({"etfs": etfs}), encoding="utf-8")
    monkeypatch.setattr(u, "_ETF_MASTER_PATH", path)
    u.reload_master()
    yield
    u.reload_master()


def _write_ohlcv(dir_path, symbol):
    df = pl.DataFrame({
        "date": ["2020-01-01", "2020-01-02"],
        "open": [100.0, 101.0], "high": [101.0, 102.0], "low": [99.0, 100.0],
        "close": [100.0, 101.0], "volume": [1000.0, 1000.0],
    })
    df.write_parquet(dir_path / f"{symbol}.parquet")


def test_is_etf_symbol(synthetic_etf_master):
    assert u.is_etf_symbol("069500") is True
    assert u.is_etf_symbol("005930") is False


def test_loader_skips_fundamental_enrichment_for_etf(tmp_path, synthetic_etf_master, monkeypatch):
    _write_ohlcv(tmp_path, "069500")
    _write_ohlcv(tmp_path, "005930")

    called = []
    monkeypatch.setattr(
        DataLoader, "_enrich_fundamentals",
        lambda self, symbol, df: called.append(symbol) or df,
    )

    loader = DataLoader(str(tmp_path))
    loader.load_symbol_data("069500")  # ETF — enrichment 스킵
    loader.load_symbol_data("005930")  # 주식 — 기존대로 시도

    assert called == ["005930"]
