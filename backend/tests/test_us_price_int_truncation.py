"""미국 종목 시세가 원화식 int 절삭 경로에 타는 회귀 방지.

2026-09-01 사고: 엔진 로더가 US 파케이도 돌려주게 된 뒤(8164294e)로
GET /stock/{symbol}/ohlcv 의 US 폴백(load_us_ohlcv, float 유지)이 죽은 경로가 되어
한국 경로의 int() 절삭이 달러 소수점을 뭉갰다 (14.73 → 14.00, 등락률 0.00%).

계약: 미국 티커는 어떤 서빙 경로에서도 가격을 정수로 절삭하지 않는다.
한국 심볼(숫자 시작)은 기존 원 단위 정수 규약을 유지한다.
"""
from datetime import date

import polars as pl
import pytest


@pytest.fixture
def us_parquet_dir(tmp_path, monkeypatch):
    """us_ohlcv 기본 디렉터리를 임시 US 파케이로 교체."""
    df = pl.DataFrame({
        "date": [date(2026, 8, d) for d in range(20, 29)],
        "open": [14.70 + i * 0.01 for i in range(9)],
        "high": [14.80 + i * 0.01 for i in range(9)],
        "low": [14.60 + i * 0.01 for i in range(9)],
        "close": [14.73 + i * 0.01 for i in range(9)],
        "volume": [1_000_000.0 + i for i in range(9)],
    })
    df.write_parquet(tmp_path / "AES.parquet")

    import us_ohlcv
    monkeypatch.setattr(us_ohlcv, "_US_DATA_DIR", str(tmp_path))
    return df


def test_ohlcv_endpoint_serves_us_floats_even_when_loader_has_the_symbol(
    us_parquet_dir, monkeypatch
):
    """로더가 US 파케이를 돌려줘도 US 티커는 float 경로(us_ohlcv)로 서빙돼야 한다."""
    import main

    # 8164294e 이후의 로더 동작 재현: US 심볼에도 DataFrame을 돌려준다
    monkeypatch.setattr(
        main.engine.loader, "load_symbol_data", lambda symbol: us_parquet_dir
    )

    result = main.get_stock_ohlcv("AES")

    first = result["candles"][0]
    assert first["close"] == pytest.approx(14.73)   # int 절삭이면 14
    assert first["open"] == pytest.approx(14.70)
    assert result["lastClose"] == pytest.approx(14.81)
    # 절삭됐다면 모든 종가가 같은 정수로 뭉개져 등락이 사라진다
    closes = [c["close"] for c in result["candles"]]
    assert len(set(closes)) > 1


def test_ohlcv_endpoint_keeps_kr_integer_convention(us_parquet_dir, monkeypatch):
    """한국 심볼은 US 폴백에 걸리지 않고 기존 원 단위 정수 규약을 유지한다."""
    import main

    kr_df = pl.DataFrame({
        "date": [date(2026, 8, d) for d in range(20, 23)],
        "open": [70100.0, 70200.0, 70300.0],
        "high": [70500.0, 70600.0, 70700.0],
        "low": [69900.0, 70000.0, 70100.0],
        "close": [70400.0, 70500.0, 70600.0],
        "volume": [1000.0, 1100.0, 1200.0],
    })
    monkeypatch.setattr(
        main.engine.loader, "load_symbol_data",
        lambda symbol: kr_df if symbol == "005930" else None,
    )

    result = main.get_stock_ohlcv("005930")
    first = result["candles"][0]
    assert first["close"] == 70400 and isinstance(first["close"], int)
    assert isinstance(result["lastClose"], int)


def test_market_signals_preserves_us_float_prices(monkeypatch):
    """/market/signals 도 US 심볼 가격을 int 절삭하지 않는다."""
    import main

    df = pl.DataFrame({
        "date": [date(2026, 8, 27), date(2026, 8, 28)],
        "open": [14.72, 14.73],
        "high": [14.75, 14.75],
        "low": [14.71, 14.71],
        "close": [14.75, 14.73],
        "volume": [100.0, 200.0],
    })
    monkeypatch.setattr(main.engine.loader, "load_symbol_data", lambda symbol: df)
    monkeypatch.setattr(main, "prepare_signal_dataframe",
                        lambda df, *args, **kwargs: df)

    result = main.market_signals({"symbols": ["AES"]})

    sig = result["signals"][0]
    assert "error" not in sig, sig
    assert sig["close"] == pytest.approx(14.73)
    assert sig["open"] == pytest.approx(14.73)
    assert isinstance(sig["volume"], int)


def test_market_signals_keeps_kr_integer_convention(monkeypatch):
    import main

    df = pl.DataFrame({
        "date": [date(2026, 8, 28)],
        "open": [70100.0],
        "high": [70500.0],
        "low": [69900.0],
        "close": [70400.0],
        "volume": [1000.0],
    })
    monkeypatch.setattr(main.engine.loader, "load_symbol_data", lambda symbol: df)
    monkeypatch.setattr(main, "prepare_signal_dataframe",
                        lambda df, *args, **kwargs: df)

    result = main.market_signals({"symbols": ["005930"]})

    sig = result["signals"][0]
    assert sig["close"] == 70400 and isinstance(sig["close"], int)


def test_trailing_stop_reason_price_display():
    """트레일링스톱 사유 문구 — US는 달러 소수점, KR은 원 단위 정수."""
    from engine.virtual_trader import _price_display

    assert _price_display(14.73, "AES") == "$14.73"
    assert _price_display(1234.5, "AAPL") == "$1,234.50"
    assert _price_display(70400.0, "005930") == "70,400원"
