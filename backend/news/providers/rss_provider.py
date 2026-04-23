"""
Generic RSS/Atom feed news provider.

Configured via NEWS_RSS_FEEDS environment variable (comma-separated URLs)
or via explicit feed_urls parameter. Useful for adding custom Korean financial
news sources (e.g. 한국경제, 매일경제, 연합뉴스 economy section).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

import httpx

from news.providers.base import BaseNewsProvider
from news.schemas import RawArticle

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SimonsBot/1.0)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Well-known Korean financial RSS feeds
DEFAULT_FEEDS = [
    ("한국경제", "https://www.hankyung.com/feed/economy"),
    ("연합뉴스 경제", "https://www.yna.co.kr/rss/economy.xml"),
    ("매일경제", "https://www.mk.co.kr/rss/30200030/"),
]


def _strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)


def _parse_rss(xml_text: str, source_name: str, feed_url: str) -> List[dict]:
    items = []
    blocks = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
    for block in blocks:
        def tag(name: str) -> str:
            m = re.search(rf"<{name}(?:[^>]*)>\s*(.*?)\s*</{name}>", block, re.DOTALL)
            if m:
                val = m.group(1)
                # Unwrap CDATA
                cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>", val, re.DOTALL)
                return _strip_html(cdata.group(1) if cdata else val).strip()
            return ""

        title = tag("title")
        link = tag("link") or tag("guid")
        description = _strip_html(tag("description"))
        pub_date = tag("pubDate") or tag("dc:date") or tag("published")
        author = tag("author") or tag("dc:creator") or ""
        category = tag("category") or ""

        if not title or not link:
            continue

        items.append({
            "title": title,
            "url": link,
            "body": description or None,
            "author": author or None,
            "published_at": _parse_date(pub_date),
            "category": category or None,
            "source": source_name,
            "feed_url": feed_url,
        })

    return items


class RSSNewsProvider(BaseNewsProvider):
    """
    Generic RSS feed provider. Feed list is either passed explicitly
    or read from NEWS_RSS_FEEDS env var (format: "Name1|url1,Name2|url2").
    Falls back to DEFAULT_FEEDS if nothing configured.
    """

    name = "rss"

    def __init__(
        self,
        feed_urls: Optional[List[tuple[str, str]]] = None,
        timeout: float = 10.0,
    ):
        self._timeout = timeout
        if feed_urls:
            self._feeds = feed_urls
        else:
            env_feeds = self._parse_env_feeds()
            self._feeds = env_feeds if env_feeds else DEFAULT_FEEDS

    def is_configured(self) -> bool:
        return bool(self._feeds)

    @staticmethod
    def _parse_env_feeds() -> List[tuple[str, str]]:
        raw = os.getenv("NEWS_RSS_FEEDS", "").strip()
        if not raw:
            return []
        result = []
        for entry in raw.split(","):
            parts = entry.strip().split("|", 1)
            if len(parts) == 2:
                result.append((parts[0].strip(), parts[1].strip()))
            elif len(parts) == 1 and parts[0].startswith("http"):
                result.append(("RSS", parts[0].strip()))
        return result

    async def fetch(self, max_articles: int = 50) -> List[RawArticle]:
        articles: List[RawArticle] = []
        seen_urls: set = set()
        per_feed = max(1, max_articles // max(len(self._feeds), 1))

        async with httpx.AsyncClient(headers=_HEADERS, timeout=self._timeout, follow_redirects=True) as client:
            for source_name, feed_url in self._feeds:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        logger.warning("RSS %s returned %d", feed_url, resp.status_code)
                        continue

                    items = _parse_rss(resp.text, source_name, feed_url)
                    for item in items[:per_feed]:
                        if item["url"] in seen_urls:
                            continue
                        seen_urls.add(item["url"])

                        articles.append(
                            RawArticle(
                                provider=self.name,
                                external_id=None,
                                title=item["title"],
                                body=item.get("body"),
                                url=item["url"],
                                source=item["source"],
                                author=item.get("author"),
                                published_at=item["published_at"],
                                category=item.get("category"),
                                raw_json={"feed_url": feed_url},
                            )
                        )

                    await asyncio.sleep(random.uniform(0.2, 0.5))

                except Exception as exc:
                    logger.warning("RSS fetch failed %s: %s", feed_url, exc)

        return articles[:max_articles]
