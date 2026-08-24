"""미국 종목 상세(/market/stock-detail US 분기) 검증.

계약 (2026-08-24 AAPL→DB Inc. 오염 사고 재발 방지):
  - 미국 티커의 종목정보는 토스 Open API + 마스터(us-stocks.json)로만 구성한다.
    KIS·한국 공공데이터(기업기본정보 API)는 국내 법인 전용이라 미국 심볼/영문명을
    넣으면 무관한 국내 회사에 매칭된다.
  - 기업기본정보 이름 검색의 한글 부분 재시도는 한글이 실제로 있을 때만 수행한다
    ("Apple Inc." → "."으로 재검색되어 오염 매칭됐던 버그).
"""

import asyncio
import time

import main
from engine.providers.base import StockQuote


def _toss_quote(symbol: str, close: float, prev: float, rate: float) -> StockQuote:
    return StockQuote(
        symbol=symbol, name=symbol, date="2026-08-24",
        open=0, high=0, low=0, close=close, volume=0,
        source="toss_us", timestamp=time.time(),
        prev_close=prev, change_rate=rate,
    )


def test_us_payload_built_from_toss_and_master():
    info = {
        "symbol": "AAPL",
        "name": "애플",
        "englishName": "Apple",
        "isinCode": "US0378331005",
        "listDate": "1980-12-12",
        "sharesOutstanding": "14594180000",
    }
    master = {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Information Technology",
              "industry": "Technology Hardware", "name_kr": "애플"}
    quote = _toss_quote("AAPL", 310.59, 309.35, 0.4)

    payload = main._build_us_stock_detail_payload("AAPL", info, master, quote)

    assert payload["name"] == "애플"
    assert payload["companyBasic"] == {"englishName": "Apple Inc."}
    assert payload["listingDate"] == "19801212"          # KR 표기(YYYYMMDD)와 동일 형식
    assert payload["currentPrice"] == 310.59
    assert payload["previousClose"] == 309.35
    assert payload["marketCap"] == int(14594180000 * 310.59)
    assert payload["sector"] == "Information Technology"
    assert payload["source"] == "toss_stock_info"
    assert payload["summaryFinancials"] is None          # 국내 재무 요약 미첨부


def test_us_payload_tolerates_missing_info_and_quote():
    master = {"symbol": "ZZZT", "name": "Test Corp", "listed_date": "2020-01-02"}
    payload = main._build_us_stock_detail_payload("ZZZT", None, master, None)
    assert payload["name"] == "Test Corp"
    assert payload["listingDate"] == "20200102"          # 마스터 폴백
    assert payload["currentPrice"] is None
    assert payload["marketCap"] is None


def test_detail_skips_stock_info_api_when_master_backfilled(monkeypatch):
    """백필된 마스터(name_kr 보유)면 토스 종목정보 API를 호출하지 않는다."""
    info_calls = []

    async def fake_get_stock_info(symbols):
        info_calls.append(list(symbols))
        return {}

    async def fake_get_price(symbol):
        return _toss_quote(symbol, 310.59, 309.35, 0.4)

    monkeypatch.setattr(main.market_data_provider.us_provider, "get_stock_info", fake_get_stock_info)
    monkeypatch.setattr(main.market_data_provider, "get_price", fake_get_price)
    monkeypatch.setattr(main, "us_master_entry", lambda s: {
        "symbol": s, "name": "Apple Inc.", "name_kr": "애플",
        "listed_date": "1980-12-12", "shares_outstanding": 14594180000,
    })

    payload = asyncio.run(main.market_stock_detail("AAPL"))
    assert info_calls == []                     # API 미호출
    assert payload["name"] == "애플"
    assert payload["listingDate"] == "19801212"
    assert payload["marketCap"] == int(14594180000 * 310.59)

    # 미백필 종목(name_kr 없음)은 토스 종목정보 API로 폴백한다
    monkeypatch.setattr(main, "us_master_entry", lambda s: {"symbol": s, "name": "Unlisted Corp"})
    asyncio.run(main.market_stock_detail("XXXX"))
    assert info_calls == [["XXXX"]]


def test_company_basic_korean_retry_requires_hangul(monkeypatch):
    calls = []

    def fake_fetch(url, params):
        calls.append(dict(params))
        return []

    monkeypatch.setattr(main, "_fetch_public_data_items", fake_fetch)

    # 영문명: 문장부호만 남는 재시도("." 검색) 금지 — 1회 조회 후 종료
    assert main._fetch_company_basic_from_public_api(None, "Apple Inc.") is None
    assert len(calls) == 1

    # 한글 포함명: 기존 동작 유지 — 한글 부분("하이닉스")으로 재시도
    calls.clear()
    main._fetch_company_basic_from_public_api(None, "SK하이닉스")
    assert len(calls) == 2
    assert calls[1]["corpNm"] == "하이닉스"
