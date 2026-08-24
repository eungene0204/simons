"""토스증권 한국 배치 시세 provider(engine/providers/toss_kr.py) 검증.

계약:
  - 한국 종목코드(6자리·숫자 시작)만 처리한다 — 미국 티커는 KR 레인 미진입.
  - /api/v1/prices 응답(lastPrice만 제공)을 원 단위 정수 StockQuote로 변환하고,
    전일종가는 로컬 한국 파케이(data/ohlcv) 마지막 종가로 보강한다.
  - 날짜는 KST 기준. 인증·토큰 캐시·배치는 TossUSProvider 상속(별도 검증 불필요).
"""

import asyncio

import polars as pl
import pytest

import engine.providers.toss_kr as toss_kr
from engine.providers.toss_kr import TossKRProvider, is_kr_symbol


@pytest.fixture
def provider(monkeypatch, tmp_path):
    monkeypatch.setenv("TOSS_INVEST_CLIENT_ID", "tsck_test")
    monkeypatch.setenv("TOSS_INVEST_CLIENT_SECRET", "tssk_test")
    monkeypatch.setattr(toss_kr, "_KR_OHLCV_DIR", tmp_path)
    pl.DataFrame({"close": [281500.0, 257000.0]}).write_parquet(tmp_path / "005930.parquet")
    return TossKRProvider()


def test_is_kr_symbol_classification():
    assert is_kr_symbol("005930")
    assert is_kr_symbol("0151S0")   # 한국 ETN류 (영숫자 혼합, 숫자 시작)
    assert not is_kr_symbol("AAPL")
    assert not is_kr_symbol("BRK-B")
    assert not is_kr_symbol("00593")     # 5자리
    assert not is_kr_symbol("../0059")


def test_to_quote_maps_int_price_prev_close_and_kst_date(provider):
    quote = provider._to_quote({
        "symbol": "005930",
        "timestamp": "2026-08-24T14:30:00.000+09:00",
        "lastPrice": "269500",
        "currency": "KRW",
    })
    assert quote is not None
    assert quote.close == 269500 and isinstance(quote.close, int)  # 원 단위 정수 규약
    assert quote.date == "2026-08-24"
    assert quote.source == "toss_kr"
    # 장중(현재가 != 마지막 종가): 파케이 마지막 종가가 전일종가
    assert quote.prev_close == 257000
    assert quote.change_rate == pytest.approx(4.86, abs=0.01)


def test_prev_close_uses_second_last_after_daily_sync(provider):
    # 21:00 sync 후 파케이가 오늘 봉까지 반영(현재가 == 마지막 종가) — 직전 봉이 전일종가
    quote = provider._to_quote({
        "symbol": "005930",
        "timestamp": "2026-08-24T21:30:00.000+09:00",
        "lastPrice": "257000",
    })
    assert quote.prev_close == 281500


def test_to_quote_rejects_invalid_price(provider):
    assert provider._to_quote({"symbol": "005930", "lastPrice": "0"}) is None
    assert provider._to_quote({"symbol": "005930", "lastPrice": None}) is None
    assert provider._to_quote({"symbol": "", "lastPrice": "1000"}) is None


def test_get_prices_filters_non_kr_and_requires_config(provider, monkeypatch):
    called_symbols: list[list[str]] = []

    def fake_fetch(symbols):
        called_symbols.append(symbols)
        return {}

    monkeypatch.setattr(provider, "_fetch_quotes", fake_fetch)
    asyncio.run(provider.get_prices(["AAPL", "005930", "000660"]))
    assert called_symbols == [["005930", "000660"]]

    unconfigured = TossKRProvider.__new__(TossKRProvider)
    unconfigured._client_id = ""
    unconfigured._client_secret = ""
    assert asyncio.run(unconfigured.get_prices(["005930"])) == {}
