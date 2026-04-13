import asyncio
import os
import sys
import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    _extract_latest_debt_ratio,
    _fetch_kis_stock_detail,
    _financial_ratio_cache,
    _nl_parser_status,
    _nl_parsers,
    _summarize_model,
    preload_nl_parser,
    preload_summarize_model,
    startup,
)


class _MockResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_extract_latest_debt_ratio_uses_most_recent_period():
    result = _extract_latest_debt_ratio([
        {"stac_yymm": "202412", "lblt_rate": "45.50"},
        {"stac_yymm": "202512", "lblt_rate": "38.25"},
        {"stac_yymm": "202312", "lblt_rate": "55.10"},
    ])

    assert result == 38.25


def test_extract_latest_debt_ratio_skips_invalid_values():
    result = _extract_latest_debt_ratio([
        {"stac_yymm": "202412", "lblt_rate": "-"},
        {"stac_yymm": "202512", "lblt_rate": "0"},
        {"stac_yymm": "202612", "lblt_rate": ""},
    ])

    assert result is None


def test_fetch_kis_stock_detail_includes_debt_ratio(monkeypatch):
    _financial_ratio_cache.clear()

    def mock_get(url, headers=None, params=None, timeout=None):
        if url.endswith("/quotations/inquire-price"):
            return _MockResponse(200, {
                "output": {
                    "hts_kor_isnm": "삼성전자",
                    "stck_prpr": "72500",
                    "stck_oprc": "72000",
                    "stck_hgpr": "72800",
                    "stck_lwpr": "71800",
                    "acml_vol": "12500000",
                    "stck_sdpr": "70770",
                    "prdy_ctrt": "2.44",
                    "hts_avls": "432000000000000",
                    "perx": "12.50",
                    "pbrx": "1.20",
                }
            })

        if url.endswith("/finance/financial-ratio"):
            return _MockResponse(200, {
                "output": [
                    {"stac_yymm": "202412", "lblt_rate": "28.10"},
                    {"stac_yymm": "202512", "lblt_rate": "25.75"},
                ]
            })

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("main.requests.get", mock_get)

    result = _fetch_kis_stock_detail("005930", "app-key", "app-secret", "token")

    assert result is not None
    assert result["symbol"] == "005930"
    assert result["debtRatio"] == 25.75
    assert result["per"] == 12.5
    assert result["pbr"] == 1.2


@pytest.mark.asyncio
async def test_startup_does_not_warm_popular_stock_cache(monkeypatch):
    calls = {"start_ws": 0, "virtual_trader_start": 0, "subscribe": 0, "get_prices": 0}

    async def mock_start_ws():
        calls["start_ws"] += 1

    async def mock_virtual_trader_start():
        calls["virtual_trader_start"] += 1

    async def mock_subscribe(_symbols):
        calls["subscribe"] += 1

    async def mock_get_prices(_symbols):
        calls["get_prices"] += 1
        return {"005930": {"price": 72000}}

    monkeypatch.setattr("main.market_data_provider.start_ws", mock_start_ws)
    monkeypatch.setattr("main._virtual_trader.start", mock_virtual_trader_start)
    monkeypatch.setattr("main.market_data_provider.subscribe", mock_subscribe)
    monkeypatch.setattr("main.market_data_provider.get_prices", mock_get_prices)

    await startup()
    await asyncio.sleep(0)

    assert calls["start_ws"] == 1
    assert calls["virtual_trader_start"] == 1
    assert calls["subscribe"] == 0
    assert calls["get_prices"] == 0


def test_preload_nl_parser_preloads_shared_parser_and_updates_status(monkeypatch):
    class _DummyParser:
        def __init__(self, backend="mlx"):
            self.backend = backend
            self.model_7b = "mlx-community/Qwen3.5-4B-OptiQ-4bit"
            self._mlx_model_7b = None
            self._tokenizer_7b = None

        def _init_mlx(self):
            self._mlx_model_7b = object()
            self._tokenizer_7b = object()

        def _model_log_label(self, model_name: str) -> str:
            return "Qwen3.5-4B"

    monkeypatch.setattr("engine.nl_parser.NLStrategyParser", _DummyParser)
    _nl_parsers.clear()
    _summarize_model["model"] = None
    _summarize_model["tokenizer"] = None
    _nl_parser_status["status"] = "loading"
    _nl_parser_status["error"] = None

    preload_nl_parser()

    assert "mlx" in _nl_parsers
    assert _summarize_model["model"] is _nl_parsers["mlx"]._mlx_model_7b
    assert _summarize_model["tokenizer"] is _nl_parsers["mlx"]._tokenizer_7b
    assert _nl_parser_status == {"status": "ok", "error": None}


def test_preload_summarize_model_uses_shared_nl_parser(monkeypatch):
    class _SharedParser:
        def __init__(self):
            self.model_7b = "mlx-community/Qwen3.5-4B-OptiQ-4bit"
            self._mlx_model_7b = object()
            self._tokenizer_7b = object()

        def _init_mlx(self):
            return None

        def _model_log_label(self, model_name: str) -> str:
            return "Qwen3.5-4B"

    monkeypatch.setattr("platform.system", lambda: "Darwin")

    _nl_parsers.clear()
    _nl_parsers["mlx"] = _SharedParser()
    _summarize_model["model"] = None
    _summarize_model["tokenizer"] = None

    preload_summarize_model()

    assert _summarize_model["model"] is _nl_parsers["mlx"]._mlx_model_7b
    assert _summarize_model["tokenizer"] is _nl_parsers["mlx"]._tokenizer_7b
