"""
Naver Finance News provider.

Scrapes the Naver Finance news RSS / mobile API endpoint which is publicly
accessible without an API key. Returns Korean financial news articles.

Rate limit: polite crawling, 1–2 req/s with jitter.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
from urllib.parse import urljoin

import httpx

from news.providers.base import BaseNewsProvider
from news.schemas import RawArticle

logger = logging.getLogger(__name__)

# Naver Finance news RSS by category
_RSS_URLS = {
    "market": "https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=401",
    "macro":  "https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258",
    "corp":   "https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=261",
}

# Naver Finance news RSS feeds (publicly accessible)
_RSS_FEED_URLS = [
    "https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=401",
]

# Official Naver Finance RSS (most reliable)
_NAVER_RSS_FEEDS = [
    ("시장", "https://stocks.finance.naver.com/news/rss.naver?category=marketSum"),
    ("경제", "https://stocks.finance.naver.com/news/rss.naver?category=economy"),
    ("기업", "https://stocks.finance.naver.com/news/rss.naver?category=company"),
    ("해외", "https://stocks.finance.naver.com/news/rss.naver?category=world"),
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SimonsBot/1.0; +https://simons.app)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _parse_rss_date(date_str: str) -> datetime:
    """Parse RFC 2822 date from RSS to UTC datetime."""
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _extract_rss_items(xml_text: str, category: str) -> List[dict]:
    """Minimal RSS item parser without external XML lib dependency."""
    items = []
    item_blocks = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
    for block in item_blocks:
        def tag(name: str) -> str:
            m = re.search(rf"<{name}(?:[^>]*)>(.*?)</{name}>", block, re.DOTALL)
            return _strip_html(m.group(1).strip()) if m else ""

        title = tag("title")
        link = tag("link") or tag("guid")
        description = tag("description")
        pub_date = tag("pubDate")
        author = tag("author") or tag("dc:creator")
        source = tag("source") or "Naver Finance"

        if not title or not link:
            continue

        published_at = _parse_rss_date(pub_date) if pub_date else datetime.now(timezone.utc)

        items.append({
            "title": title,
            "url": link,
            "body": description,
            "author": author or None,
            "published_at": published_at,
            "category": category,
            "source": source or "Naver Finance",
        })

    return items


class NaverNewsProvider(BaseNewsProvider):
    """
    Fetches Korean financial news from Naver Finance RSS feeds.
    No API key required — uses public RSS endpoints.
    """

    name = "naver_news"

    def __init__(self, timeout: float = 10.0, max_feeds: int = 4):
        self._timeout = timeout
        self._max_feeds = max_feeds

    def is_configured(self) -> bool:
        return True  # No credentials needed

    async def fetch(self, max_articles: int = 50) -> List[RawArticle]:
        articles: List[RawArticle] = []
        seen_urls: set = set()

        async with httpx.AsyncClient(headers=_HEADERS, timeout=self._timeout, follow_redirects=True) as client:
            feeds = _NAVER_RSS_FEEDS[: self._max_feeds]
            for category, feed_url in feeds:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        logger.warning("Naver RSS %s returned %d", feed_url, resp.status_code)
                        continue

                    items = _extract_rss_items(resp.text, category)
                    per_feed = max(1, max_articles // len(feeds))

                    for item in items[:per_feed]:
                        url = item["url"]
                        if url in seen_urls:
                            continue
                        seen_urls.add(url)

                        articles.append(
                            RawArticle(
                                provider=self.name,
                                external_id=None,
                                title=item["title"],
                                body=item.get("body"),
                                url=url,
                                source=item["source"],
                                author=item.get("author"),
                                published_at=item["published_at"],
                                category=item.get("category"),
                                raw_json={"feed_url": feed_url, "category": category},
                            )
                        )

                    # Polite crawl delay
                    await asyncio.sleep(random.uniform(0.3, 0.7))

                except Exception as exc:
                    logger.warning("Naver RSS fetch failed for %s: %s", feed_url, exc)

        return articles[:max_articles]
