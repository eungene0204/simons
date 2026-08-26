"""미국 일봉 서빙(us_ohlcv.load_us_ohlcv) 검증.

계약:
  - 한국 경로(GET /stock/{symbol}/ohlcv)와 동일한 {candles, lastClose, sigma} 형태.
  - 미국 주가는 float 유지 (한국 경로의 int 절삭을 따라가면 저가주 차트가 뭉개짐).
  - 티커 형식이 아니거나(경로 조작 포함) 파일이 없으면 None.
"""

from datetime import date

import polars as pl
import pytest

from us_ohlcv import load_us_ohlcv


@pytest.fixture
def us_data_dir(tmp_path):
    df = pl.DataFrame({
        "date": [date(2026, 8, d) for d in range(1, 11)],
        "open": [100.1234567 + i for i in range(10)],
        "high": [101.5 + i for i in range(10)],
        "low": [99.5 + i for i in range(10)],
        "close": [100.9876543 + i for i in range(10)],
        "volume": [1000.0 + i for i in range(10)],
    })
    df.write_parquet(tmp_path / "AAPL.parquet")
    return str(tmp_path)


def test_float_prices_preserved(us_data_dir):
    result = load_us_ohlcv("AAPL", data_dir=us_data_dir)
    assert result is not None
    first = result["candles"][0]
    assert first["open"] == pytest.approx(100.1235)  # round(x, 4) — int 절삭 금지
    assert first["close"] == pytest.approx(100.9877)
    assert isinstance(first["volume"], int)
    assert result["lastClose"] == pytest.approx(109.9877)
    assert first["date"] == "2026-08-01"
    assert isinstance(result["sigma"], float)


def test_limit_respected(us_data_dir):
    result = load_us_ohlcv("AAPL", limit=3, data_dir=us_data_dir)
    assert len(result["candles"]) == 3
    assert result["candles"][0]["date"] == "2026-08-08"


def test_missing_symbol_returns_none(us_data_dir):
    assert load_us_ohlcv("MSFT", data_dir=us_data_dir) is None


def test_non_ticker_symbols_rejected(us_data_dir):
    # 한국 심볼(숫자 시작)·소문자·경로 조작은 파일 조회 전에 거른다
    assert load_us_ohlcv("005930", data_dir=us_data_dir) is None
    assert load_us_ohlcv("aapl", data_dir=us_data_dir) is None
    assert load_us_ohlcv("../AAPL", data_dir=us_data_dir) is None
    assert load_us_ohlcv("A" * 11, data_dir=us_data_dir) is None


def test_null_close_rows_dropped_and_null_ohlc_falls_back(tmp_path):
    df = pl.DataFrame({
        "date": [date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)],
        "open": [None, 10.0, 11.0],
        "high": [None, 10.5, 11.5],
        "low": [None, 9.5, 10.5],
        "close": [9.0, None, 11.2],
        "volume": [None, 100.0, 200.0],
    })
    df.write_parquet(tmp_path / "TEST.parquet")

    result = load_us_ohlcv("TEST", data_dir=str(tmp_path))
    # close가 null인 8/2 행은 제거된다
    assert [c["date"] for c in result["candles"]] == ["2026-08-01", "2026-08-03"]
    # open/high/low가 null이면 같은 봉의 close로 대체, volume null은 0
    assert result["candles"][0]["open"] == pytest.approx(9.0)
    assert result["candles"][0]["volume"] == 0
