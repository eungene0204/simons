import json
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


def test_kis_ws_provider_signed_decline_diff_not_double_counted():
    """2026-08-24 사고 재현: KRX 피드가 전일대비를 부호 포함(-12000)으로 보내면
    하락 분기(prev = price + diff)에서 이중 감산돼 전일종가가 257500으로 틀렸다.
    방향은 부호 필드로만 판정하고 변동폭은 절대값을 써야 한다."""
    provider = KISWebSocketProvider()
    fields = ["0"] * 47
    fields[0] = "005930"
    fields[1] = "090100"
    fields[2] = "269500"
    fields[3] = "5"         # 하락
    fields[4] = "-12000"    # 부호 포함 전일대비
    fields[5] = "-4.26"
    fields[7] = "271500"
    fields[8] = "272000"
    fields[9] = "269000"
    fields[13] = "850413"

    raw = f"0|H0STCNT0|1|{'^'.join(fields)}"
    quote = provider._parse_realtime(raw)

    assert quote is not None
    assert quote.prev_close == 281500  # 269500 + |−12000|
    assert quote.change_rate == -4.26


@pytest.mark.asyncio
async def test_kis_ws_provider_stale_quote_not_served(monkeypatch):
    """2026-08-24 사고 재현: 틱이 끊긴 뒤에도 캐시가 남아 아침 시세가 하루 종일
    서빙됐다. 신선도 한도를 넘긴 캐시는 None/제외로 반환해 REST 폴백이 동작해야 한다."""
    import time as _time
    from engine.providers.base import StockQuote

    monkeypatch.setenv("KIS_APP_KEY", "test-app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "test-app-secret")
    provider = KISWebSocketProvider()

    def _quote(symbol, ts):
        return StockQuote(
            symbol=symbol, name=symbol, date="2026-08-24",
            open=271500, high=272000, low=269000, close=269500,
            volume=850413, source="kis_ws_total", timestamp=ts,
        )

    provider._cache["005930"] = _quote("005930", _time.time() - 3600)  # 1시간 전 틱
    provider._cache["000660"] = _quote("000660", _time.time())          # 방금 틱

    assert await provider.get_price("005930") is None
    assert (await provider.get_price("000660")) is not None

    prices = await provider.get_prices(["005930", "000660"])
    assert "005930" not in prices
    assert "000660" in prices


def test_kis_ws_provider_max_subscribe_over_triggers_resync():
    """MAX SUBSCRIBE OVER(OPSP0008) 응답이 오면 세션 재정합 플래그가 서고,
    쿨다운 안의 반복 재정합은 막힌다."""
    provider = KISWebSocketProvider()

    ack = json.dumps({
        "header": {"tr_id": "H0STCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "1", "msg_cd": "OPSP0008", "msg1": "MAX SUBSCRIBE OVER"},
    })
    provider._log_subscribe_ack(ack)
    assert provider._resync_needed is True

    assert provider._resync_due() is True       # 첫 재정합 실행
    assert provider._resync_needed is False     # 플래그 소모

    provider._log_subscribe_ack(ack)            # 쿨다운 안에서 재발
    assert provider._resync_due() is False      # 재연결 폭주 방지


def test_kis_ws_provider_unsubscribe_not_found_no_resync():
    """UNSUBSCRIBE ERROR(not found, OPSP0003)는 서버에 이미 없는 등록이므로
    재정합을 트리거하지 않는다."""
    provider = KISWebSocketProvider()
    ack = json.dumps({
        "header": {"tr_id": "H0STCNT0", "tr_key": "005930"},
        "body": {"rt_cd": "1", "msg_cd": "OPSP0003", "msg1": "UNSUBSCRIBE ERROR(not found!)"},
    })
    provider._log_subscribe_ack(ack)
    assert provider._resync_needed is False
