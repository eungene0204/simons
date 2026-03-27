"""
Provider 단위 테스트 — HTTP 호출을 mock하여 파싱 로직 검증
"""

import pytest
import time
from unittest.mock import patch, MagicMock

from engine.providers.base import StockQuote, BaseProvider, ProviderHealth
from engine.providers.naver import NaverProvider, _parse_number, _fetch_naver_quote
from engine.providers.pykrx_provider import PykrxProvider
from main import _fetch_naver_index


# ─── StockQuote ───────────────────────────────────────────────

class TestStockQuote:
    def test_to_dict(self):
        q = StockQuote(
            symbol="005930", name="삼성전자", date="2026-03-27",
            open=55000, high=56000, low=54000, close=55500,
            volume=10000000, source="naver", timestamp=1000.0,
        )
        d = q.to_dict()
        assert d["symbol"] == "005930"
        assert d["close"] == 55500
        assert d["source"] == "naver"
        assert isinstance(d, dict)


# ─── Naver Provider ──────────────────────────────────────────

class TestNaverParseNumber:
    def test_comma_number(self):
        assert _parse_number("173,000") == 173000

    def test_negative(self):
        assert _parse_number("-7,100") == -7100

    def test_empty(self):
        assert _parse_number("") == 0

    def test_none(self):
        assert _parse_number(None) == 0

    def test_korean_suffix(self):
        # "26,161,756" → 26161756
        assert _parse_number("26,161,756") == 26161756


class TestNaverProvider:
    @patch("engine.providers.naver.requests.get")
    def test_fetch_naver_quote_success(self, mock_get):
        """네이버 basic + integration 응답 파싱"""
        basic_resp = MagicMock()
        basic_resp.status_code = 200
        basic_resp.json.return_value = {
            "stockName": "삼성전자",
            "closePrice": "55,500",
            "localTradedAt": "2026-03-27T14:30:00+09:00",
        }

        integ_resp = MagicMock()
        integ_resp.status_code = 200
        integ_resp.json.return_value = {
            "totalInfos": [
                {"code": "openPrice", "value": "55,000"},
                {"code": "highPrice", "value": "56,000"},
                {"code": "lowPrice", "value": "54,000"},
                {"code": "accumulatedTradingVolume", "value": "10,000,000"},
            ]
        }

        mock_get.side_effect = [basic_resp, integ_resp]

        quote = _fetch_naver_quote("005930")
        assert quote is not None
        assert quote.symbol == "005930"
        assert quote.name == "삼성전자"
        assert quote.close == 55500
        assert quote.open == 55000
        assert quote.high == 56000
        assert quote.low == 54000
        assert quote.volume == 10000000
        assert quote.source == "naver"

    @patch("engine.providers.naver.requests.get")
    def test_fetch_naver_quote_basic_fails(self, mock_get):
        """basic 엔드포인트 실패 시 None 반환"""
        basic_resp = MagicMock()
        basic_resp.status_code = 404
        mock_get.return_value = basic_resp

        quote = _fetch_naver_quote("999999")
        assert quote is None

    @patch("engine.providers.naver.requests.get")
    def test_fetch_naver_quote_zero_price(self, mock_get):
        """종가가 0이면 None 반환"""
        basic_resp = MagicMock()
        basic_resp.status_code = 200
        basic_resp.json.return_value = {
            "stockName": "테스트",
            "closePrice": "0",
            "localTradedAt": "2026-03-27",
        }
        mock_get.return_value = basic_resp

        quote = _fetch_naver_quote("000000")
        assert quote is None


# ─── Pykrx Provider ──────────────────────────────────────────

class TestPykrxProvider:
    @patch("engine.providers.pykrx_provider._fetch_pykrx_prices")
    @pytest.mark.asyncio
    async def test_get_price_delegates(self, mock_fetch):
        """get_price가 _fetch_pykrx_prices를 호출하는지 확인"""
        mock_quote = StockQuote(
            symbol="005930", name="삼성전자", date="2026-03-26",
            open=55000, high=56000, low=54000, close=55500,
            volume=10000000, source="pykrx", timestamp=time.time(),
        )
        mock_fetch.return_value = {"005930": mock_quote}

        provider = PykrxProvider()
        result = await provider.get_price("005930")
        assert result is not None
        assert result.source == "pykrx"


# ─── Naver Index ──────────────────────────────────────────────

class TestNaverIndex:
    def _make_basic_resp(self, close="5,438.87", change="-21.59", ratio="-0.40"):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "closePrice": close,
            "compareToPreviousClosePrice": change,
            "fluctuationsRatio": ratio,
            "localTradedAt": "2026-03-27T16:33:00+09:00",
        }
        return resp

    def _make_integ_resp(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "totalInfos": [
                {"code": "openPrice", "value": "5,300.61"},
                {"code": "highPrice", "value": "5,462.51"},
                {"code": "lowPrice",  "value": "5,288.33"},
                {"code": "accumulatedTradingVolume", "value": "650,000,000"},
            ]
        }
        return resp

    @patch("requests.get")
    def test_success(self, mock_get):
        """정상 응답 파싱"""
        mock_get.side_effect = [self._make_basic_resp(), self._make_integ_resp()]
        result = _fetch_naver_index("KOSPI", "코스피")
        assert result is not None
        assert result["value"] == 5438.87
        assert result["change"] == -21.59
        assert result["changePercent"] == -0.40
        assert result["open"] == 5300.61
        assert result["high"] == 5462.51
        assert result["low"] == 5288.33
        assert result["source"] == "naver"
        assert result["date"] == "2026-03-27"

    @patch("requests.get")
    def test_basic_fails(self, mock_get):
        """basic 엔드포인트 404 → None 반환"""
        resp = MagicMock()
        resp.status_code = 404
        mock_get.return_value = resp
        assert _fetch_naver_index("KOSPI", "코스피") is None

    @patch("requests.get")
    def test_zero_price(self, mock_get):
        """closePrice가 0 → None 반환"""
        mock_get.side_effect = [self._make_basic_resp(close="0"), self._make_integ_resp()]
        assert _fetch_naver_index("KOSPI", "코스피") is None

    @patch("requests.get")
    def test_integration_fails_gracefully(self, mock_get):
        """integration 실패해도 기본값으로 반환"""
        integ_fail = MagicMock()
        integ_fail.status_code = 500
        mock_get.side_effect = [self._make_basic_resp(), integ_fail]
        result = _fetch_naver_index("KOSDAQ", "코스닥")
        assert result is not None
        assert result["value"] == 5438.87
        assert result["open"] == 0.0
