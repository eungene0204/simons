"""토스증권 미국 시세 provider(engine/providers/toss_us.py) 검증.

계약:
  - 미국 티커만 처리한다 (한국 심볼은 6자리·숫자 시작 — US 레인 미진입).
  - /api/v1/prices 응답(lastPrice만 제공)을 StockQuote로 변환하고,
    전일종가는 로컬 미국 파케이(data/ohlcv-us) 마지막 종가로 보강한다.
  - 날짜는 미국 세션 기준(뉴욕 시간대)으로 변환한다.
  - 토큰은 만료 전까지 재사용, 401이면 1회 재발급 후 재시도.
  - MarketDataProvider에서 미국 심볼은 토스 레인 단독 — KR 체인·WS 구독에 흘러가지 않는다.
"""

import asyncio
import time
from datetime import date

import polars as pl
import pytest

import engine.providers.toss_us as toss_us
from engine.providers.base import StockQuote
from engine.providers.toss_us import TossUSProvider, is_us_symbol


@pytest.fixture
def provider(monkeypatch, tmp_path):
    monkeypatch.setenv("TOSS_INVEST_CLIENT_ID", "tsck_test")
    monkeypatch.setenv("TOSS_INVEST_CLIENT_SECRET", "tssk_test")
    monkeypatch.setattr(toss_us, "_US_OHLCV_DIR", tmp_path)
    monkeypatch.setattr(toss_us, "_master_map", {"AAPL": {"symbol": "AAPL", "name": "Apple Inc."}})
    pl.DataFrame({"close": [300.0, 309.35]}).write_parquet(tmp_path / "AAPL.parquet")
    return TossUSProvider()


def test_is_us_symbol_classification():
    assert is_us_symbol("AAPL")
    assert is_us_symbol("BRK-B")
    assert is_us_symbol("BF.A")
    assert not is_us_symbol("005930")   # 한국 주식
    assert not is_us_symbol("0151S0")   # 한국 ETF (영숫자 혼합이지만 숫자 시작)
    assert not is_us_symbol("aapl")
    assert not is_us_symbol("../AAPL")


def test_to_quote_maps_price_prev_close_and_ny_date(provider):
    quote = provider._to_quote({
        "symbol": "AAPL",
        # KST 19:31 (월) == 뉴욕 06:31 (월) — 미국 세션 날짜로 변환돼야 한다
        "timestamp": "2026-08-24T19:31:03.000+09:00",
        "lastPrice": "310.59",
        "currency": "USD",
    })
    assert quote is not None
    assert quote.close == pytest.approx(310.59)
    assert quote.name == "Apple Inc."
    assert quote.date == "2026-08-24"
    assert quote.source == "toss_us"
    assert quote.prev_close == pytest.approx(309.35)  # 파케이 마지막 종가
    assert quote.change_rate == pytest.approx(0.4, abs=0.01)


def test_to_quote_kst_morning_maps_to_previous_ny_date(provider):
    # KST 10:00 (월) == 뉴욕 21:00 (일) — 주간거래(야간 ATS) 시각은 전일 뉴욕 날짜
    quote = provider._to_quote({
        "symbol": "AAPL",
        "timestamp": "2026-08-24T10:00:00.000+09:00",
        "lastPrice": "310.59",
    })
    assert quote.date == "2026-08-23"


def test_prev_close_uses_second_last_when_price_equals_last_close(provider):
    # 장 마감 후 파케이가 오늘 봉까지 반영한 상태 — 직전 봉이 전일종가
    assert provider._prev_close("AAPL", 309.35) == pytest.approx(300.0)
    # 세션 진행 중 (현재가 != 마지막 종가) — 마지막 봉이 전일종가
    assert provider._prev_close("AAPL", 310.59) == pytest.approx(309.35)


def test_to_quote_rejects_invalid_price(provider):
    assert provider._to_quote({"symbol": "AAPL", "lastPrice": "0"}) is None
    assert provider._to_quote({"symbol": "AAPL", "lastPrice": None}) is None
    assert provider._to_quote({"symbol": "", "lastPrice": "10"}) is None


def test_get_prices_filters_non_us_and_requires_config(provider, monkeypatch):
    called_symbols: list[list[str]] = []

    def fake_fetch(symbols):
        called_symbols.append(symbols)
        return {}

    monkeypatch.setattr(provider, "_fetch_quotes", fake_fetch)
    asyncio.run(provider.get_prices(["005930", "AAPL", "MSFT"]))
    assert called_symbols == [["AAPL", "MSFT"]]

    unconfigured = TossUSProvider.__new__(TossUSProvider)
    unconfigured._client_id = ""
    unconfigured._client_secret = ""
    assert asyncio.run(unconfigured.get_prices(["AAPL"])) == {}


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_token_cached_and_reissued_on_401(provider, monkeypatch):
    token_calls = []

    def fake_post(url, data=None, timeout=None):
        token_calls.append(url)
        return _FakeResponse(payload={"access_token": f"tok{len(token_calls)}", "expires_in": 86400})

    get_calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        get_calls.append(headers["Authorization"])
        # 첫 요청은 401 (토큰 폐기 시나리오) — 재발급 후 재시도돼야 한다
        if len(get_calls) == 1:
            return _FakeResponse(status_code=401)
        return _FakeResponse(payload={"result": [
            {"symbol": "AAPL", "timestamp": "2026-08-24T19:31:03.000+09:00", "lastPrice": "310.59"},
        ]})

    monkeypatch.setattr(toss_us.requests, "post", fake_post)
    monkeypatch.setattr(toss_us.requests, "get", fake_get)

    quotes = provider._fetch_quotes(["AAPL"])
    assert quotes["AAPL"].close == pytest.approx(310.59)
    assert len(token_calls) == 2                # 최초 발급 + 401 후 재발급
    assert get_calls == ["Bearer tok1", "Bearer tok2"]

    # 유효한 토큰은 재사용 — 추가 발급 없음
    provider._fetch_quotes(["AAPL"])
    assert len(token_calls) == 2


def test_get_stock_info_maps_symbols_and_filters_kr(provider, monkeypatch):
    requested = []

    def fake_post(url, data=None, timeout=None):
        return _FakeResponse(payload={"access_token": "tok", "expires_in": 86400})

    def fake_get(url, params=None, headers=None, timeout=None):
        requested.append(params["symbols"])
        return _FakeResponse(payload={"result": [
            {"symbol": "BRK.B", "name": "버크셔 해서웨이", "isinCode": "US0846707026"},
        ]})

    monkeypatch.setattr(toss_us.requests, "post", fake_post)
    monkeypatch.setattr(toss_us.requests, "get", fake_get)

    info = asyncio.run(provider.get_stock_info(["005930", "BRK-B"]))
    assert requested == ["BRK.B"]                       # KR 심볼 제외 + 점 표기 요청
    assert info["BRK-B"]["name"] == "버크셔 해서웨이"     # 우리 표기로 복원


def test_class_share_symbols_requested_with_dot_returned_with_dash(provider, monkeypatch):
    """우리 표기는 대시(BRK-B), 토스 표기는 점(BRK.B) — 요청 시 변환·응답 시 복원."""
    requested_params = []

    def fake_post(url, data=None, timeout=None):
        return _FakeResponse(payload={"access_token": "tok", "expires_in": 86400})

    def fake_get(url, params=None, headers=None, timeout=None):
        requested_params.append(params["symbols"])
        return _FakeResponse(payload={"result": [
            {"symbol": "BRK.B", "timestamp": "2026-08-24T19:31:03.000+09:00", "lastPrice": "498.17"},
        ]})

    monkeypatch.setattr(toss_us.requests, "post", fake_post)
    monkeypatch.setattr(toss_us.requests, "get", fake_get)

    quotes = provider._fetch_quotes(["BRK-B"])
    assert requested_params == ["BRK.B"]        # API에는 점 표기로 요청
    assert "BRK-B" in quotes                    # 결과는 우리 표기로 복원
    assert quotes["BRK-B"].close == pytest.approx(498.17)


def _stock_quote(symbol: str, close: float, source: str) -> StockQuote:
    return StockQuote(
        symbol=symbol, name=symbol, date="2026-08-24",
        open=0, high=0, low=0, close=close, volume=0,
        source=source, timestamp=time.time(),
    )


def test_market_data_provider_routes_us_to_toss_lane(monkeypatch):
    from engine.market_data import MarketDataProvider

    mdp = MarketDataProvider()

    class _StubUS:
        name = "toss_us"

        def is_configured(self):
            return True

        async def get_prices(self, symbols):
            return {s: _stock_quote(s, 310.59, "toss_us") for s in symbols}

    class _StubWS:
        name = "kis_ws"
        subscribed: list[str] = []

        def is_configured(self):
            return False

        async def subscribe(self, symbols):
            _StubWS.subscribed.extend(symbols)

    class _StubKR:
        name = "kr_stub"
        seen: list[str] = []

        def is_configured(self):
            return True

        async def get_prices(self, symbols):
            _StubKR.seen.extend(symbols)
            return {s: _stock_quote(s, 257000, "kr_stub") for s in symbols}

        async def get_price(self, symbol):
            return (await self.get_prices([symbol])).get(symbol)

        async def health_check(self):
            return True

    mdp.us_provider = _StubUS()
    mdp.ws_provider = _StubWS()
    mdp.providers = [_StubKR()]
    mdp.cache.clear()

    result = asyncio.run(mdp.get_prices(["AAPL", "005930"]))
    assert result["AAPL"].source == "toss_us"
    assert result["005930"].source == "kr_stub"
    assert _StubKR.seen == ["005930"]  # KR 체인에 미국 티커 미진입

    # 구독 경로에도 미국 티커가 흘러가지 않는다
    asyncio.run(mdp.subscribe(["AAPL", "005930"]))
    assert _StubWS.subscribed == ["005930"]
