"""시장지수 저장소·로더(engine/market_index) — 종목 프레임에 지수 종가를 붙이는 계약.

2026-09-13: "최근 3개월 동안 시장보다 덜 떨어진 종목"을 정확히 표현하려면 지수 레벨
시계열이 필요했다(벤치마크는 ETF 가격이라 지수 자체는 없었다). 이 파일은
① 저장 위치(OHLCV의 형제 data/index) ② 종목→지수 시장 매핑 ③ 날짜 조인+전진 충전
④ 지수가 없을 때 null 컬럼(fail-closed, 0으로 위장 금지) ⑤ mtime 캐시 무효화를 고정한다.
"""

from __future__ import annotations

import datetime as dt
import os
import time

import polars as pl
import pytest

from engine import market_index as mi


def _index_parquet(tmp_path, market: str, closes: dict[str, float]) -> str:
    index_dir = tmp_path / "index"
    index_dir.mkdir(exist_ok=True)
    df = pl.DataFrame({
        "date": [dt.datetime.fromisoformat(d) for d in closes],
        "open": list(closes.values()), "high": list(closes.values()),
        "low": list(closes.values()), "close": list(closes.values()),
        "volume": [1.0] * len(closes), "source": ["toss"] * len(closes),
    }).with_columns(pl.col("date").cast(pl.Datetime("us")))
    df.write_parquet(index_dir / f"{market}.parquet")
    return str(tmp_path / "ohlcv")


def _stock(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame({
        "date": [dt.datetime.fromisoformat(d) for d in dates],
        "close": [100.0 + i for i in range(len(dates))],
    }).with_columns(pl.col("date").cast(pl.Datetime("us")))


_COND = [{"id": "relative_return", "params": {"period": 2}}]


@pytest.fixture(autouse=True)
def _clear_caches():
    mi._load_cached.cache_clear()
    mi._market_by_symbol.cache_clear()
    yield
    mi._load_cached.cache_clear()
    mi._market_by_symbol.cache_clear()


def test_index_dir_is_sibling_of_ohlcv_dir(tmp_path):
    assert mi.index_dir_for(tmp_path / "ohlcv") == tmp_path / "index"
    assert mi.index_path("KOSPI", str(tmp_path / "ohlcv")) == tmp_path / "index" / "KOSPI.parquet"


def test_market_for_symbol_uses_master_then_etf_then_none(monkeypatch):
    from engine import universe_pit
    monkeypatch.setattr(universe_pit, "_load_master", lambda: [
        {"symbol": "005930", "market": "KOSPI"}, {"symbol": "247540", "market": "KOSDAQ"},
    ])
    monkeypatch.setattr(universe_pit, "is_etf_symbol", lambda s: s == "069500")
    assert mi.market_for_symbol("005930") == "KOSPI"
    assert mi.market_for_symbol("247540") == "KOSDAQ"
    assert mi.market_for_symbol("069500") == "KOSPI"       # 마스터 밖 ETF → 코스피
    assert mi.market_for_symbol("AAPL") is None            # 미국 종목 → 지수 없음
    assert mi.market_for_symbol("999999") is None          # 알 수 없는 종목


def test_attach_joins_index_close_and_forward_fills_gaps(tmp_path, monkeypatch):
    data_dir = _index_parquet(tmp_path, "KOSPI", {
        "2024-01-02": 2500.0, "2024-01-03": 2510.0, "2024-01-05": 2530.0,
    })
    monkeypatch.setattr(mi, "market_for_symbol", lambda s: "KOSPI")
    stock = _stock(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    out = mi.attach_index_close(stock, "005930", _COND, data_dir)
    assert out[mi.INDEX_CLOSE_COL].to_list() == [2500.0, 2510.0, 2510.0, 2530.0]
    assert out.schema["date"] == stock.schema["date"]
    assert len(out) == len(stock)


def test_attach_is_noop_without_relative_return_condition(tmp_path, monkeypatch):
    data_dir = _index_parquet(tmp_path, "KOSPI", {"2024-01-02": 2500.0})
    monkeypatch.setattr(mi, "market_for_symbol", lambda s: "KOSPI")
    stock = _stock(["2024-01-02"])
    out = mi.attach_index_close(stock, "005930", [{"id": "rsi", "params": {}}], data_dir)
    assert mi.INDEX_CLOSE_COL not in out.columns


def test_attach_adds_null_column_when_index_missing(tmp_path, monkeypatch):
    """지수 파일이 없거나(미러 전) 시장을 모르면(미국 종목) 0으로 위장하지 않고 null."""
    data_dir = str(tmp_path / "ohlcv")
    monkeypatch.setattr(mi, "market_for_symbol", lambda s: None)
    out = mi.attach_index_close(_stock(["2024-01-02"]), "AAPL", _COND, data_dir)
    assert out[mi.INDEX_CLOSE_COL].to_list() == [None]
    monkeypatch.setattr(mi, "market_for_symbol", lambda s: "KOSDAQ")   # 파일 없음
    out = mi.attach_index_close(_stock(["2024-01-02"]), "247540", _COND, data_dir)
    assert out[mi.INDEX_CLOSE_COL].to_list() == [None]


def test_index_cache_invalidates_on_file_change(tmp_path, monkeypatch):
    data_dir = _index_parquet(tmp_path, "KOSPI", {"2024-01-02": 2500.0})
    first = mi.load_index_frame("KOSPI", data_dir)
    assert first[mi.INDEX_CLOSE_COL].to_list() == [2500.0]
    time.sleep(0.01)
    _index_parquet(tmp_path, "KOSPI", {"2024-01-02": 2600.0})
    path = mi.index_path("KOSPI", data_dir)
    os.utime(path, None)
    second = mi.load_index_frame("KOSPI", data_dir)
    assert second[mi.INDEX_CLOSE_COL].to_list() == [2600.0]
