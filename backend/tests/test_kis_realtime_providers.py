import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.providers.kis import KISProvider
from engine.providers.kis_ws import KISWebSocketProvider


class _MockResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_kis_provider_uses_unified_market_code(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "test-app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "test-app-secret")

    captured = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["timeout"] = timeout
        return _MockResponse(200, {
            "output": {
                "hts_kor_isnm": "삼성전자",
                "stck_prpr": "70100",
                "stck_oprc": "69500",
                "stck_hgpr": "70300",
                "stck_lwpr": "69400",
                "acml_vol": "123456",
                "stck_sdpr": "69000",
                "prdy_ctrt": "1.59",
            }
        })

    monkeypatch.setattr("engine.providers.kis.requests.get", fake_get)

    provider = KISProvider()
    quote = provider._fetch_price_sync("005930", "test-token")

    assert quote is not None
    assert quote.source == "kis_total"
    assert captured["params"]["FID_COND_MRKT_DIV_CODE"] == "UN"
    assert captured["params"]["FID_INPUT_ISCD"] == "005930"


def test_kis_ws_provider_parses_total_orderbook():
    provider = KISWebSocketProvider()
    fields = ["0"] * 65
    fields[0] = "005930"
    fields[1] = "091500"
    fields[3] = "70200"
    fields[4] = "70300"
    fields[13] = "70100"
    fields[14] = "70000"
    fields[23] = "1200"
    fields[24] = "900"
    fields[33] = "1500"
    fields[34] = "1100"
    fields[43] = "2100"
    fields[44] = "2600"
    fields[47] = "70100"

    raw = f"0|H0UNASP0|1|{'^'.join(fields)}"
    orderbook = provider._parse_realtime_orderbook(raw)

    assert orderbook is not None
    assert orderbook["symbol"] == "005930"
    assert orderbook["sellOrders"][:2] == [
        {"price": 70200, "quantity": 1200},
        {"price": 70300, "quantity": 900},
    ]
    assert orderbook["buyOrders"][:2] == [
        {"price": 70100, "quantity": 1500},
        {"price": 70000, "quantity": 1100},
    ]
    assert orderbook["totalAskQty"] == 2100
    assert orderbook["totalBidQty"] == 2600


def test_kis_ws_provider_builds_recent_trade_from_total_tick():
    provider = KISWebSocketProvider()
    fields = ["0"] * 47
    fields[0] = "005930"
    fields[1] = "091501"
    fields[2] = "70100"
    fields[3] = "2"
    fields[4] = "1100"
    fields[5] = "1.59"
    fields[7] = "69500"
    fields[8] = "70300"
    fields[9] = "69400"
    fields[10] = "70100"
    fields[11] = "70000"
    fields[12] = "37"
    fields[13] = "123456"
    fields[15] = "9"
    fields[16] = "4"

    raw = f"0|H0UNCNT0|1|{'^'.join(fields)}"
    quote = provider._parse_realtime(raw)
    trade = provider._build_recent_trade(quote, raw) if quote else None

    assert quote is not None
    assert quote.source == "kis_ws_total"
    assert quote.close == 70100
    assert trade == {
        "price": 70100,
        "quantity": 37,
        "type": "buy",
        "timestamp": quote.timestamp,
    }


def test_kis_ws_provider_builds_sell_trade_from_total_tick():
    provider = KISWebSocketProvider()
    fields = ["0"] * 47
    fields[0] = "005930"
    fields[1] = "091502"
    fields[2] = "70000"
    fields[3] = "2"
    fields[4] = "1000"
    fields[5] = "1.45"
    fields[7] = "69500"
    fields[8] = "70300"
    fields[9] = "69400"
    fields[10] = "70100"
    fields[11] = "70000"
    fields[12] = "19"
    fields[13] = "123475"
    fields[15] = "4"
    fields[16] = "9"

    raw = f"0|H0UNCNT0|1|{'^'.join(fields)}"
    quote = provider._parse_realtime(raw)
    trade = provider._build_recent_trade(quote, raw) if quote else None

    assert quote is not None
    assert trade == {
        "price": 70000,
        "quantity": 19,
        "type": "sell",
        "timestamp": quote.timestamp,
    }


def test_kis_ws_provider_upper_limit_sign_is_positive():
    """sign=1(상한)은 상승 방향 — change_rate가 음수로 뒤집히면 안 된다."""
    provider = KISWebSocketProvider()
    fields = ["0"] * 47
    fields[0] = "042700"
    fields[1] = "150000"
    fields[2] = "269500"
    fields[3] = "1"
    fields[4] = "62000"
    fields[5] = "29.88"
    fields[7] = "225500"
    fields[8] = "269500"
    fields[9] = "224000"
    fields[13] = "2355581"

    raw = f"0|H0UNCNT0|1|{'^'.join(fields)}"
    quote = provider._parse_realtime(raw)

    assert quote is not None
    assert quote.change_rate == 29.88
    assert quote.prev_close == 207500


def test_kis_ws_provider_lower_decline_sign_is_negative():
    """sign=5(하락)는 하락 방향 — change_rate가 양수로 남으면 안 된다."""
    provider = KISWebSocketProvider()
    fields = ["0"] * 47
    fields[0] = "005930"
    fields[1] = "150000"
    fields[2] = "68000"
    fields[3] = "5"
    fields[4] = "2100"
    fields[5] = "3.00"
    fields[7] = "70000"
    fields[8] = "70100"
    fields[9] = "67900"
    fields[13] = "500000"

    raw = f"0|H0UNCNT0|1|{'^'.join(fields)}"
    quote = provider._parse_realtime(raw)

    assert quote is not None
    assert quote.change_rate == -3.00
    assert quote.prev_close == 70100


@pytest.mark.asyncio
async def test_kis_ws_provider_get_orderbook_includes_recent_trades(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "test-app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "test-app-secret")
    provider = KISWebSocketProvider()
    provider._orderbook_cache["005930"] = {
        "symbol": "005930",
        "sellOrders": [{"price": 70200, "quantity": 100}],
        "buyOrders": [{"price": 70100, "quantity": 200}],
        "totalAskQty": 100,
        "totalBidQty": 200,
        "source": "kis_ws_total_orderbook",
        "timestamp": 123.0,
    }
    provider._recent_trades["005930"] = [
        {"price": 70100, "quantity": 10, "type": "buy", "timestamp": 456.0},
    ]

    result = await provider.get_orderbook("005930")

    assert result is not None
    assert result["recentTrades"] == [
        {"price": 70100, "quantity": 10, "type": "buy", "timestamp": 456.0},
    ]
