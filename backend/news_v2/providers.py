"""
Provider adapters for news_v2.

We delegate the actual external HTTP work to the existing `news.providers.*`
modules (Naver, RSS, Google News) so we don't duplicate provider auth/parsing.
This module gives us a stable surface that the collector calls.

Adapter responsibility:
  - Convert provider raw articles → CollectedArticle dataclass
  - Filter by symbol (Google News naturally; Naver/RSS post-hoc by company name)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class CollectedArticle:
    title: str
    url: str
    source: str
    published_at: datetime
    summary: Optional[str] = None
    body: Optional[str] = None
    provider: str = "unknown"


async def fetch_for_symbol(
    symbol: str, company_name: str, max_articles: int = 30
) -> list[CollectedArticle]:
    """Fetch latest articles for `symbol` from configured providers.

    Returns a flat, provider-tagged list. Caller does normalize + dedup + persist.
    """
    results: list[CollectedArticle] = []

    # Reuse existing GoogleNewsProvider which already accepts (symbol, name) targets.
    try:
        from news.providers.google_news import GoogleNewsProvider  # type: ignore

        gp = GoogleNewsProvider([(symbol, company_name)])
        if gp.is_configured():
            raw = await gp.fetch(max_articles=max_articles)
            for r in raw:
                results.append(
                    CollectedArticle(
                        title=r.title,
                        url=r.url,
                        source=r.source,
                        published_at=r.published_at,
                        summary=getattr(r, "summary", None),
                        body=getattr(r, "body", None),
                        provider="google_news",
                    )
                )
    except Exception:  # pragma: no cover
        pass

    return results
