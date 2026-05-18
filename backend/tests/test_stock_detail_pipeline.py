import asyncio
import os
import sys
import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    _build_company_intro,
    _build_public_company_overview,
    _fetch_company_basic_from_public_api,
    _fetch_listing_info_from_public_api,
    _fetch_summary_financials_from_public_api,
    _extract_latest_debt_ratio,
    _fetch_kis_stock_detail,
    _financial_ratio_cache,
    _get_cached_listing_info,
    _get_cached_public_company_info,
    _normalize_company_name_for_match,
    _nl_parser_status,
    _nl_parsers,
    _public_company_info_cache,
    _summarize_model,
    _listing_info_cache,
    market_stock_detail,
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

    monkeypatch.setattr("main._http_session.get", mock_get)

    result = _fetch_kis_stock_detail("005930", "app-key", "app-secret", "token")

    assert result is not None
    assert result["symbol"] == "005930"
    assert result["debtRatio"] == 25.75
    assert result["per"] == 12.5
    assert result["pbr"] == 1.2


def test_build_company_intro_uses_sector_and_industry():
    result = _build_company_intro("삼성전자", "정보기술", "반도체")

    assert result == "삼성전자는 정보기술 섹터의 반도체 업종에 속한 상장사입니다."


def test_build_public_company_overview_uses_public_fields():
    result = _build_public_company_overview(
        {
            "name": "삼성전자(주)",
            "disclosureName": "삼성전자",
            "representativeName": "전영현, 노태문",
            "address": "경기도 수원시 영통구 삼성로 129 (매탄동)",
        },
        {
            "listingDate": "19750611",
        },
    )

    assert result == (
        "삼성전자는 국내 상장사입니다. "
        "상장일은 1975년 06월 11일입니다. "
        "대표자는 전영현, 노태문입니다. "
        "본사는 경기도 수원시 영통구 삼성로 129 (매탄동)에 있습니다."
    )


def test_normalize_company_name_for_match_removes_legal_suffixes():
    assert _normalize_company_name_for_match("(주) 삼성전자") == "삼성전자"
    assert _normalize_company_name_for_match("삼성전자(주)") == "삼성전자"
    assert _normalize_company_name_for_match("주식회사 삼성전자") == "삼성전자"


def test_fetch_listing_info_from_public_api_returns_listing_date(monkeypatch):
    monkeypatch.setattr("main._get_public_data_service_key", lambda: "test-key")

    def mock_get(url, params=None, timeout=None):
        if url.endswith("/GetKrxListedInfoService/getItemInfo"):
            return _MockResponse(200, {
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {
                        "items": {
                            "item": [
                                {"srtnCd": "005930", "crno": "1301110006246"},
                            ]
                        }
                    },
                }
            })

        if url.endswith("/GetStocIssuInfoService/getItemBasiInfo"):
            return _MockResponse(200, {
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {
                        "items": {
                            "item": [
                                {"crno": "1301110006246", "lstgDt": "19750611"},
                            ]
                        }
                    },
                }
            })

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("main._http_session.get", mock_get)

    result = _fetch_listing_info_from_public_api("005930")

    assert result == {
        "listingDate": "19750611",
        "crno": "1301110006246",
        "isinCode": None,
        "stockIssueCompanyName": None,
        "issuedShares": 0,
        "parValue": 0,
        "delistingDate": None,
        "source": "fsc_stock_issuance",
    }


def test_fetch_company_basic_from_public_api_returns_company_outline(monkeypatch):
    monkeypatch.setattr("main._get_public_data_service_key", lambda: "test-key")

    def mock_get(url, params=None, timeout=None):
        assert url.endswith("/GetCorpBasicInfoService_V2/getCorpOutline_V2")
        return _MockResponse(200, {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [{
                            "crno": "1301110006246",
                            "corpNm": "삼성전자",
                            "corpEnsnNm": "Samsung Electronics Co., Ltd.",
                            "enpRprFnm": "한종희",
                            "enpEstbDt": "19690113",
                            "enpHmpgUrl": "https://www.samsung.com/sec/",
                            "sicNm": "반도체 제조업",
                            "enpMainBizNm": "반도체 및 전자제품 제조",
                            "enpEmpeCnt": "124804",
                            "enpBsadr": "경기도 수원시 영통구 삼성로 129",
                        }]
                    },
                },
            }
        })

    monkeypatch.setattr("main._http_session.get", mock_get)

    result = _fetch_company_basic_from_public_api("1301110006246", "삼성전자")

    assert result is not None
    assert result["name"] == "삼성전자"
    assert result["englishName"] == "Samsung Electronics Co., Ltd."
    assert result["representativeName"] == "한종희"
    assert result["establishmentDate"] == "19690113"
    assert result["homepageUrl"] == "https://www.samsung.com/sec/"
    assert result["industry"] == "반도체 제조업"
    assert result["mainBusiness"] == "반도체 및 전자제품 제조"
    assert result["employeeCount"] == 124804


def test_fetch_company_basic_from_public_api_normalizes_homepage_url(monkeypatch):
    monkeypatch.setattr("main._get_public_data_service_key", lambda: "test-key")

    def mock_get(url, params=None, timeout=None):
        assert url.endswith("/GetCorpBasicInfoService_V2/getCorpOutline_V2")
        return _MockResponse(200, {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [{
                            "crno": "1301110006246",
                            "corpNm": "삼성전자",
                            "enpHmpgUrl": "www.samsung.com/sec",
                        }]
                    },
                },
            }
        })

    monkeypatch.setattr("main._http_session.get", mock_get)

    result = _fetch_company_basic_from_public_api("1301110006246", "삼성전자")

    assert result is not None
    assert result["homepageUrl"] == "https://www.samsung.com/sec"


def test_fetch_company_basic_from_public_api_prefers_listed_company_match(monkeypatch):
    monkeypatch.setattr("main._get_public_data_service_key", lambda: "test-key")

    def mock_get(url, params=None, timeout=None):
        assert url.endswith("/GetCorpBasicInfoService_V2/getCorpOutline_V2")
        return _MockResponse(200, {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [
                            {
                                "crno": "1101110877477",
                                "corpNm": "삼성전자잠실판매",
                            },
                            {
                                "crno": "1301110006246",
                                "corpNm": "삼성전자(주)",
                                "enpPbanCmpyNm": "삼성전자",
                                "corpRegMrktDcdNm": "유가",
                                "enpXchgLstgDt": "75/06/11",
                                "fssCorpUnqNo": "00126380",
                            },
                        ]
                    },
                },
            }
        })

    monkeypatch.setattr("main._http_session.get", mock_get)

    result = _fetch_company_basic_from_public_api(None, "(주)삼성전자")

    assert result is not None
    assert result["crno"] == "1301110006246"
    assert result["name"] == "삼성전자(주)"


def test_fetch_company_basic_from_public_api_merges_sparse_public_rows(monkeypatch):
    monkeypatch.setattr("main._get_public_data_service_key", lambda: "test-key")

    def mock_get(url, params=None, timeout=None):
        assert url.endswith("/GetCorpBasicInfoService_V2/getCorpOutline_V2")
        return _MockResponse(200, {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [
                            {
                                "crno": "1301110006246",
                                "corpNm": "삼성전자(주)",
                                "enpPbanCmpyNm": "삼성전자",
                                "corpRegMrktDcdNm": "유가",
                            },
                            {
                                "crno": "1301110006246",
                                "corpNm": "삼성전자(주)",
                                "sicNm": "이동전화기 제조업",
                                "enpMainBizNm": "전자제품 제조",
                            },
                        ]
                    },
                },
            }
        })

    monkeypatch.setattr("main._http_session.get", mock_get)

    result = _fetch_company_basic_from_public_api(None, "삼성전자")

    assert result is not None
    assert result["name"] == "삼성전자(주)"
    assert result["disclosureName"] == "삼성전자"
    assert result["industry"] == "이동전화기 제조업"
    assert result["mainBusiness"] == "전자제품 제조"


def test_fetch_company_basic_from_public_api_requires_identifier(monkeypatch):
    monkeypatch.setattr("main._get_public_data_service_key", lambda: "test-key")

    def mock_get(url, params=None, timeout=None):
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("main._http_session.get", mock_get)

    assert _fetch_company_basic_from_public_api(None, None) is None


def test_fetch_summary_financials_from_public_api_returns_latest_summary(monkeypatch):
    monkeypatch.setattr("main._get_public_data_service_key", lambda: "test-key")

    def mock_get(url, params=None, timeout=None):
        assert url.endswith("/GetFinaStatInfoService_V2/getSummFinaStat_V2")
        return _MockResponse(200, {
            "response": {
                "header": {"resultCode": "00"},
                "body": {
                    "items": {
                        "item": [
                            {
                                "crno": "1301110006246",
                                "bizYear": "2023",
                                "basDt": "20231231",
                                "fnclDcdNm": "별도",
                                "enpSaleAmt": "1000",
                            },
                            {
                                "crno": "1301110006246",
                                "bizYear": "2024",
                                "basDt": "20241231",
                                "fnclDcdNm": "연결",
                                "enpSaleAmt": "2000",
                                "enpBzopPft": "-100",
                                "enpTastAmt": "5000",
                                "enpTdbtAmt": "1500",
                                "enpTcptAmt": "3500",
                                "fnclDebtRto": "42.86",
                            },
                        ]
                    },
                },
            }
        })

    monkeypatch.setattr("main._http_session.get", mock_get)

    result = _fetch_summary_financials_from_public_api("1301110006246")

    assert result is not None
    assert result["businessYear"] == "2024"
    assert result["statementType"] == "연결"
    assert result["sales"] == 2000
    assert result["operatingProfit"] == -100
    assert result["totalAssets"] == 5000
    assert result["debtRatio"] == 42.86


def test_get_cached_listing_info_uses_cache(monkeypatch):
    _listing_info_cache.clear()
    calls = {"count": 0}

    def mock_fetch(symbol, company_name=None):
        calls["count"] += 1
        return {"listingDate": "19750611", "source": f"listing:{symbol}"}

    monkeypatch.setattr("main._fetch_listing_info_from_public_api", mock_fetch)

    first = _get_cached_listing_info("005930")
    second = _get_cached_listing_info("005930")

    assert first == second
    assert calls["count"] == 1


def test_get_cached_public_company_info_uses_cache(monkeypatch):
    _public_company_info_cache.clear()
    calls = {"count": 0}

    def mock_fetch(symbol, company_name=None):
        calls["count"] += 1
        return {
            "listing": {"crno": "1301110006246", "listingDate": "19750611"},
            "companyBasic": {"name": "삼성전자"},
            "summaryFinancials": {"businessYear": "2024"},
        }

    monkeypatch.setattr("main._fetch_public_company_info", mock_fetch)

    first = _get_cached_public_company_info("005930")
    second = _get_cached_public_company_info("005930")

    assert first == second
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_market_stock_detail_uses_company_profile_without_kis(monkeypatch):
    class _Quote:
        close = 72500
        volume = 12500000
        prev_close = 70770
        name = "삼성전자"

    async def mock_resolve(_symbol):
        return _Quote(), "", "", None

    monkeypatch.setattr("main._resolve_kis_orderbook_context", mock_resolve)
    monkeypatch.setattr("main._resolve_investment_sector", lambda _symbol, _company_name, _industry: "반도체")
    monkeypatch.setattr("main._get_cached_public_company_info", lambda _symbol, _company_name=None: {
        "listing": {
            "listingDate": "19750611",
            "crno": "1301110006246",
        },
        "companyBasic": {
            "name": "삼성전자",
            "industry": "반도체 제조업",
        },
        "summaryFinancials": None,
        "source": "fsc_public_company_info",
    })

    result = await market_stock_detail("005930")

    assert result["name"] == "삼성전자"
    assert result["description"] == "삼성전자는 반도체 제조업 업종에 속한 국내 상장사입니다. 상장일은 1975년 06월 11일입니다."
    assert result["sector"] == "반도체"
    assert result["industry"] == "반도체 제조업"
    assert result["currentPrice"] == 72500
    assert result["source"] == "fsc_public_company_info"


@pytest.mark.asyncio
async def test_market_stock_detail_can_skip_profile_and_listing(monkeypatch):
    class _Quote:
        close = 72500
        volume = 12500000
        prev_close = 70770
        name = "삼성전자"

    async def mock_resolve(_symbol):
        return _Quote(), "", "", None

    monkeypatch.setattr("main._resolve_kis_orderbook_context", mock_resolve)
    monkeypatch.setattr("main._get_cached_listing_info", lambda _symbol: {
        "listingDate": "19750611",
        "source": "fsc_stock_issuance",
    })
    monkeypatch.setattr("main._get_cached_public_company_info", lambda _symbol, _company_name=None: None)

    result = await market_stock_detail("005930", include_profile=False, include_listing=False)

    assert result["description"].endswith("국내 상장사입니다.")
    assert result["sector"] == ""
    assert result["industry"] == ""
    assert result["listingDate"] is None
    assert result["currentPrice"] == 72500
    assert result["source"] == "quote_only"


@pytest.mark.asyncio
async def test_market_stock_detail_includes_public_company_info(monkeypatch):
    class _Quote:
        close = 72500
        volume = 12500000
        prev_close = 70770
        name = "삼성전자"

    async def mock_resolve(_symbol):
        return _Quote(), "", "", None

    monkeypatch.setattr("main._resolve_kis_orderbook_context", mock_resolve)
    monkeypatch.setattr("main._resolve_investment_sector", lambda _symbol, _company_name, _industry: "반도체")
    monkeypatch.setattr("main._get_cached_public_company_info", lambda _symbol, _company_name=None: {
        "listing": {
            "listingDate": "19750611",
            "crno": "1301110006246",
        },
        "companyBasic": {
            "name": "삼성전자",
            "industry": "반도체 제조업",
            "mainBusiness": "반도체 및 전자제품 제조",
        },
        "summaryFinancials": {
            "businessYear": "2024",
            "sales": 2000,
            "debtRatio": 42.86,
        },
        "source": "fsc_public_company_info",
    })

    result = await market_stock_detail("005930")

    assert result["listingDate"] == "19750611"
    assert result["description"] == "삼성전자의 주요 사업은 반도체 및 전자제품 제조입니다. 상장일은 1975년 06월 11일입니다."
    assert result["industry"] == "반도체 제조업"
    assert result["sector"] == "반도체"
    assert result["debtRatio"] == 42.86
    assert result["companyBasic"]["name"] == "삼성전자"
    assert result["summaryFinancials"]["businessYear"] == "2024"
    assert result["source"] == "fsc_public_company_info"


@pytest.mark.asyncio
async def test_market_stock_detail_prefers_public_main_business(monkeypatch):
    class _Quote:
        close = 72500
        volume = 12500000
        prev_close = 70770
        name = "삼성전자"

    async def mock_resolve(_symbol):
        return _Quote(), "", "", None

    monkeypatch.setattr("main._resolve_kis_orderbook_context", mock_resolve)
    monkeypatch.setattr("main._resolve_investment_sector", lambda _symbol, _company_name, _industry: "반도체")
    monkeypatch.setattr("main._get_cached_public_company_info", lambda _symbol, _company_name=None: {
        "listing": {
            "listingDate": "19750611",
            "crno": "1301110006246",
        },
        "companyBasic": {
            "name": "삼성전자",
            "industry": "반도체 제조업",
            "mainBusiness": "반도체 및 전자제품 제조",
        },
        "summaryFinancials": None,
        "source": "fsc_public_company_info",
    })

    result = await market_stock_detail("005930")

    assert result["description"] == "삼성전자의 주요 사업은 반도체 및 전자제품 제조입니다. 상장일은 1975년 06월 11일입니다."


@pytest.mark.asyncio
async def test_market_stock_detail_builds_korean_intro_from_public_basic(monkeypatch):
    class _Quote:
        close = 72500
        volume = 12500000
        prev_close = 70770
        name = "삼성전자"

    async def mock_resolve(_symbol):
        return _Quote(), "", "", None

    monkeypatch.setattr("main._resolve_kis_orderbook_context", mock_resolve)
    monkeypatch.setattr("main._get_cached_public_company_info", lambda _symbol, _company_name=None: {
        "listing": {
            "listingDate": "19750611",
            "crno": "1301110006246",
        },
        "companyBasic": {
            "name": "삼성전자(주)",
            "industry": None,
            "mainBusiness": None,
        },
        "summaryFinancials": None,
        "source": "fsc_public_company_info",
    })

    result = await market_stock_detail("005930", include_profile=False)

    assert result["description"] == "삼성전자는 국내 상장사입니다. 상장일은 1975년 06월 11일입니다."


@pytest.mark.asyncio
async def test_market_stock_detail_keeps_public_description_when_profile_skipped(monkeypatch):
    class _Quote:
        close = 72500
        volume = 12500000
        prev_close = 70770
        name = "삼성전자"

    async def mock_resolve(_symbol):
        return _Quote(), "", "", None

    monkeypatch.setattr("main._resolve_kis_orderbook_context", mock_resolve)
    monkeypatch.setattr("main._get_cached_public_company_info", lambda _symbol, _company_name=None: {
        "listing": {
            "listingDate": "19750611",
            "crno": "1301110006246",
        },
        "companyBasic": {
            "name": "삼성전자(주)",
            "industry": None,
            "mainBusiness": None,
        },
        "summaryFinancials": None,
        "source": "fsc_public_company_info",
    })

    result = await market_stock_detail("005930", include_profile=False)

    assert result["description"] == "삼성전자는 국내 상장사입니다. 상장일은 1975년 06월 11일입니다."


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
