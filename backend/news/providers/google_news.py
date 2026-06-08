"""
Google News RSS provider for stock-specific news.

Searches Google News RSS by company name to fetch news for specific Korean stocks.
No API key required — uses public Google News RSS endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import quote

import httpx

from news.providers.base import BaseNewsProvider
from news.schemas import RawArticle

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_RSS_BASE = "https://news.google.com/rss/search?hl=ko&gl=KR&ceid=KR:ko&q={query}"


def _parse_date(date_str: str) -> datetime:
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    from html import unescape
    # Unwrap CDATA sections
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    # Decode entities first (RSS often encodes HTML as &lt;a&gt;...&lt;/a&gt;)
    text = unescape(text)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode any remaining entities
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_items(xml: str) -> List[dict]:
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.DOTALL):
        def tag(name: str) -> str:
            m = re.search(rf"<{name}(?:[^>]*)>(.*?)</{name}>", block, re.DOTALL)
            return _strip_html(m.group(1).strip()) if m else ""

        title = tag("title")
        link = tag("link") or tag("guid")
        source = tag("source") or "Google News"
        pub_date = tag("pubDate")
        description = tag("description") or None

        if not title or not link:
            continue

        items.append({
            "title": title,
            "url": link,
            "source": source,
            "published_at": _parse_date(pub_date) if pub_date else datetime.now(timezone.utc),
            "description": description,
        })
    return items


def _company_aliases(company_name: str) -> list[str]:
    name = re.sub(r"\s+", " ", (company_name or "").strip())
    if not name:
        return []

    aliases = [name]
    if name.endswith("자동차") and len(name) > len("자동차"):
        aliases.append(f"{name[:-len('자동차')]}차")

    unique_aliases: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias and alias not in seen:
            seen.add(alias)
            unique_aliases.append(alias)
    return unique_aliases


def _build_search_queries(company_name: str) -> list[str]:
    aliases = _company_aliases(company_name)
    if not aliases:
        return []
    if len(aliases) == 1:
        return [aliases[0]]
    return [" OR ".join(aliases), aliases[0]]


class GoogleNewsProvider(BaseNewsProvider):
    """
    Fetches stock-specific news from Google News RSS.
    Takes a list of (symbol, company_name) pairs to search for.
    """

    name = "google_news"

    def __init__(
        self,
        targets: List[tuple[str, str]],  # [(symbol, company_name), ...]
        timeout: float = 15.0,
    ):
        self._targets = targets
        self._timeout = timeout

    def is_configured(self) -> bool:
        return bool(self._targets)

    async def fetch(self, max_articles: int = 50) -> List[RawArticle]:
        articles: List[RawArticle] = []
        seen_urls: set = set()
        per_symbol = max(1, max_articles // max(len(self._targets), 1))

        async with httpx.AsyncClient(headers=_HEADERS, timeout=self._timeout, follow_redirects=True) as client:
            for symbol, company_name in self._targets:
                target_articles: list[RawArticle] = []
                for raw_query in _build_search_queries(company_name):
                    query = quote(raw_query)
                    url = _RSS_BASE.format(query=query)
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            logger.warning("Google News RSS %s returned %d", company_name, resp.status_code)
                            continue

                        items = _parse_items(resp.text)
                        for item in items[:per_symbol]:
                            if item["url"] in seen_urls:
                                continue
                            seen_urls.add(item["url"])

                            target_articles.append(
                                RawArticle(
                                    provider=self.name,
                                    external_id=None,
                                    title=item["title"],
                                    body=item.get("description"),
                                    url=item["url"],
                                    source=item["source"],
                                    author=None,
                                    published_at=item["published_at"],
                                    category="뉴스",
                                    raw_json={
                                        "symbol": symbol,
                                        "company_name": company_name,
                                        "query": raw_query,
                                    },
                                )
                            )

                        logger.info("[google_news] %s(%s): %d articles", raw_query, symbol, len(items))
                        await asyncio.sleep(0.25)

                    except Exception as exc:
                        logger.warning("Google News fetch failed for %s: %s", raw_query, exc)

                articles.extend(
                    sorted(target_articles, key=lambda item: item.published_at, reverse=True)[:per_symbol]
                )

        return articles[:max_articles]
