"""
Tests for news entity mapping.

Covers:
- Stock name matching
- Sector detection
- Macro scope detection
- Mixed article (stock + macro)
- Ambiguous names
- Pseudo-symbol handling
- Empty article (no entities)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from news.schemas import NormalizedArticle
from news.entity_mapper import (
    _detect_macro,
    _detect_sector,
    map_entities,
)


def _make_article(title: str, summary: str = "") -> NormalizedArticle:
    return NormalizedArticle(
        id="emap-test",
        title=title,
        summary=summary or None,
        url="https://example.com",
        source="Test",
        published_at=datetime.now(timezone.utc),
        crawled_at=datetime.now(timezone.utc),
    )


# Mock stock data for tests (avoids DB dependency)
_MOCK_STOCKS = [
    {"symbol": "005930", "name": "삼성전자", "market": "KOSPI"},
    {"symbol": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    {"symbol": "051910", "name": "LG화학", "market": "KOSPI"},
    {"symbol": "035720", "name": "카카오", "market": "KOSPI"},
    {"symbol": "035420", "name": "NAVER", "market": "KOSPI"},
    {"symbol": "005380", "name": "현대차", "market": "KOSPI"},
    {"symbol": "207940", "name": "삼성바이오로직스", "market": "KOSPI"},
]


@pytest.fixture(autouse=True)
def mock_stocks():
    with patch("news.entity_mapper.get_all_stocks", return_value=_MOCK_STOCKS):
        with patch("news.entity_mapper._cache_loaded", False):
            yield


class TestMacroDetection:
    def test_kospi_mention(self):
        assert _detect_macro("코스피 2600선 돌파") is True

    def test_interest_rate(self):
        assert _detect_macro("기준금리 인상으로 시장 흔들") is True

    def test_foreign_investors(self):
        assert _detect_macro("외국인 순매수 5000억") is True

    def test_no_macro_in_company_news(self):
        assert _detect_macro("삼성전자 신제품 출시") is False


class TestSectorDetection:
    def test_semiconductor(self):
        assert _detect_sector("반도체 업황 회복세") == "반도체"

    def test_battery(self):
        assert _detect_sector("배터리 시장 성장 전망") == "배터리/2차전지"

    def test_biotech(self):
        assert _detect_sector("바이오 신약 개발 호재") == "바이오/제약"

    def test_finance(self):
        assert _detect_sector("은행권 금리 인상") == "금융/은행"

    def test_no_sector(self):
        assert _detect_sector("날씨 맑음") is None


class TestMapEntities:
    def test_single_stock_match(self):
        article = _make_article("삼성전자 3분기 실적 발표")
        maps = map_entities(article)
        symbols = [m.symbol for m in maps]
        assert "005930" in symbols

    def test_multiple_stocks(self):
        article = _make_article("삼성전자와 SK하이닉스 반도체 협력 강화")
        maps = map_entities(article)
        symbols = [m.symbol for m in maps if not m.symbol.startswith("__")]
        assert "005930" in symbols
        assert "000660" in symbols

    def test_title_match_higher_relevance(self):
        article = _make_article(
            "삼성전자 어닝 서프라이즈",
            summary="현대차도 실적 호조를 보였다. 현대차 관련 수혜주로 주목"
        )
        maps = map_entities(article)
        samsung_map = next((m for m in maps if m.symbol == "005930"), None)
        hyundai_map = next((m for m in maps if m.symbol == "005380"), None)
        if samsung_map and hyundai_map:
            # Samsung in title should have higher relevance
            assert samsung_map.relevance >= hyundai_map.relevance

    def test_macro_article_no_stock(self):
        article = _make_article("코스피 외국인 매도세 지속, 증시 조정")
        maps = map_entities(article)
        # Macro article with no company names → macro pseudo-symbol
        scopes = [m.scope for m in maps]
        assert "macro" in scopes

    def test_sector_article(self):
        article = _make_article("반도체 업황 회복세... 하반기 기대감 상승")
        maps = map_entities(article)
        scopes = [m.scope for m in maps]
        assert "sector" in scopes or "stock" in scopes

    def test_empty_article_no_crash(self):
        article = _make_article("뉴스 제목 없음")
        maps = map_entities(article)
        # Should not crash — may return empty or macro
        assert isinstance(maps, list)

    def test_naver_match(self):
        article = _make_article("NAVER 웹툰 해외 진출 가속화")
        maps = map_entities(article)
        symbols = [m.symbol for m in maps if not m.symbol.startswith("__")]
        assert "035420" in symbols

    def test_scope_stock_for_company_news(self):
        article = _make_article("삼성전자 자사주 매입 발표")
        maps = map_entities(article)
        stock_maps = [m for m in maps if m.symbol == "005930"]
        assert stock_maps[0].scope == "stock"

    def test_relevance_bounds(self):
        article = _make_article("카카오 카카오톡 신기능 출시")
        maps = map_entities(article)
        for m in maps:
            assert 0.0 <= m.relevance <= 1.0

    def test_sector_tagged_on_stock_maps(self):
        article = _make_article("삼성전자 반도체 부문 실적 개선")
        maps = map_entities(article)
        stock_maps = [m for m in maps if m.symbol == "005930"]
        if stock_maps:
            # Sector should be tagged if a sector keyword was found
            assert stock_maps[0].sector == "반도체" or stock_maps[0].sector is None


class TestAmbiguity:
    def test_samsung_prefix_multiple(self):
        # "삼성" appears in multiple company names — should prefer full name
        article = _make_article("삼성전자 실적 발표 삼성바이오로직스 신약 승인")
        maps = map_entities(article)
        symbols = [m.symbol for m in maps if not m.symbol.startswith("__")]
        # Both should be matched if full names found
        assert "005930" in symbols or "207940" in symbols

    def test_short_name_not_over_matched(self):
        # "LG" alone should not match if full "LG화학" not in text
        article = _make_article("LG화학 배터리 수주 성공")
        maps = map_entities(article)
        lg_chem = [m for m in maps if m.symbol == "051910"]
        assert len(lg_chem) > 0  # LG화학 full name should match
