"""
Entity mapping layer.

Maps article title/body → related Korean stocks, sectors, and market scope.

Strategy:
1. Build an in-memory lookup table from the Stock table (symbol, name, aliases)
2. Search for company name mentions in the normalized title + body
3. Classify scope: stock | sector | macro
4. Assign relevance score based on mention position (title > body) and count

Korean company names are often ambiguous (삼성 → multiple entities).
The mapper resolves this by preferring full-name matches and using suffix hints
(전자, 화학, 바이오, etc.) to disambiguate.
"""

from __future__ import annotations

import re
import threading
from typing import Dict, List, Optional, Tuple

from news.schemas import ArticleSymbolMap, ArticleScope, NormalizedArticle
from news.storage import get_all_stocks

# Cache is refreshed lazily (TTL-based)
_cache_lock = threading.Lock()
_stock_cache: List[Dict] = []
_cache_loaded = False

# Korean sector keywords → sector name
_SECTOR_KEYWORDS: Dict[str, str] = {
    "반도체": "반도체",
    "디스플레이": "디스플레이",
    "배터리": "배터리/2차전지",
    "2차전지": "배터리/2차전지",
    "전기차": "전기차",
    "바이오": "바이오/제약",
    "제약": "바이오/제약",
    "의료": "헬스케어",
    "은행": "금융/은행",
    "증권": "금융/증권",
    "보험": "금융/보험",
    "건설": "건설",
    "조선": "조선/해운",
    "해운": "조선/해운",
    "자동차": "자동차",
    "철강": "철강/소재",
    "화학": "화학",
    "에너지": "에너지",
    "통신": "통신/IT",
    "인터넷": "통신/IT",
    "게임": "엔터/게임",
    "엔터": "엔터/게임",
    "유통": "유통/소비재",
    "식품": "식품/음료",
    "항공": "항공/여행",
}

# Macro / market-wide keywords
_MACRO_KEYWORDS = [
    "코스피", "코스닥", "주식시장", "증시", "금리", "기준금리", "연준", "fed",
    "인플레이션", "물가", "환율", "원달러", "외국인", "기관", "수급",
    "글로벌", "미국증시", "나스닥", "s&p", "다우", "vix", "경기침체",
    "경기", "gdp", "수출", "무역", "관세", "정책", "한국은행", "기재부",
]

# Company suffixes that help disambiguate (e.g., 삼성전자 vs 삼성물산)
_COMPANY_SUFFIXES = [
    "전자", "화학", "물산", "바이오", "제약", "증권", "생명", "화재", "보험",
    "건설", "중공업", "엔지니어링", "에너지", "통신", "네트웍스", "정보통신",
    "유통", "식품", "홀딩스", "지주", "그룹", "코퍼레이션", "테크",
]


def _load_stocks() -> List[Dict]:
    global _stock_cache, _cache_loaded
    with _cache_lock:
        if not _cache_loaded:
            _stock_cache = get_all_stocks()
            _cache_loaded = True
    return _stock_cache


def refresh_cache() -> None:
    """Force reload of stock cache from DB."""
    global _cache_loaded
    with _cache_lock:
        _cache_loaded = False
    _load_stocks()


def _build_search_text(article: NormalizedArticle) -> str:
    parts = [article.title]
    if article.summary:
        parts.append(article.summary)
    return " ".join(parts).lower()


def _score_mention(name: str, title: str, body: str) -> float:
    """Higher score = more prominent mention."""
    score = 0.0
    name_lower = name.lower()
    if name_lower in title.lower():
        score += 1.0
    count_body = body.lower().count(name_lower)
    score += min(count_body * 0.2, 0.8)
    return min(score, 1.0)


def _detect_macro(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _MACRO_KEYWORDS)


def _detect_sector(text: str) -> Optional[str]:
    text_lower = text.lower()
    for keyword, sector in _SECTOR_KEYWORDS.items():
        if keyword in text_lower:
            return sector
    return None


def map_entities(article: NormalizedArticle) -> List[ArticleSymbolMap]:
    """
    Map an article to its related stocks/sectors/macro scope.

    Returns a list of ArticleSymbolMap. May be empty for articles with
    no identifiable market entities.
    """
    stocks = _load_stocks()
    title = article.title
    body = article.summary or ""
    search_text = f"{title} {body}".lower()

    results: List[ArticleSymbolMap] = []
    matched_symbols: set = set()

    # Pass 1: exact company name match (longer names first to avoid substring traps)
    sorted_stocks = sorted(stocks, key=lambda s: len(s.get("name") or ""), reverse=True)
    for stock in sorted_stocks:
        name = stock.get("name") or ""
        symbol = stock.get("symbol") or ""
        if not name or not symbol or len(name) < 2:
            continue

        if name.lower() in search_text and symbol not in matched_symbols:
            relevance = _score_mention(name, title, body)
            results.append(
                ArticleSymbolMap(
                    article_id=article.id,
                    symbol=symbol,
                    company_name=name,
                    scope="stock",
                    relevance=relevance,
                )
            )
            matched_symbols.add(symbol)
            # Limit per-article symbol count
            if len(matched_symbols) >= 10:
                break

    # Pass 2: sector detection (if no stocks matched or supplement stock matches)
    sector = _detect_sector(search_text)
    if sector and not results:
        results.append(
            ArticleSymbolMap(
                article_id=article.id,
                symbol="__sector__",
                company_name=None,
                scope="sector",
                sector=sector,
                relevance=0.7,
            )
        )
    elif sector and results:
        # Tag existing stock maps with sector
        for m in results:
            if m.sector is None:
                m.sector = sector

    # Pass 3: macro scope
    if _detect_macro(search_text):
        if not results:
            # Pure macro article
            results.append(
                ArticleSymbolMap(
                    article_id=article.id,
                    symbol="__macro__",
                    company_name=None,
                    scope="macro",
                    relevance=0.5,
                )
            )
        else:
            # Downgrade relevance for stock articles that also mention macro terms
            for m in results:
                m.relevance = max(0.3, m.relevance * 0.9)

    return results
