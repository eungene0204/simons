"""
NewsService — orchestrator for the news pipeline.

Pipeline:
  fetch → normalize → dedup → store raw → entity map → event extract →
  impact estimate → signal generation → store all artifacts

Each step is independent and can be invoked separately for debugging
or incremental re-processing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Type

from news.providers.base import BaseNewsProvider
from news.providers.naver_news import NaverNewsProvider
from news.providers.rss_provider import RSSNewsProvider
from news.providers.google_news import GoogleNewsProvider
from news import storage
from news import normalizer as norm_module
from news import dedup as dedup_module
from news import entity_mapper
from news import event_extractor
from news import impact_model
from news.schemas import (
    ArticleSymbolMap,
    NormalizedArticle,
    IngestionStats,
    NewsIngestRequest,
)

logger = logging.getLogger(__name__)

# Registry of available news providers
_PROVIDER_REGISTRY: Dict[str, Type[BaseNewsProvider]] = {
    "naver_news": NaverNewsProvider,
    "rss": RSSNewsProvider,
}


def _get_providers(names: Optional[List[str]] = None) -> List[BaseNewsProvider]:
    """Instantiate and return configured providers."""
    providers: List[BaseNewsProvider] = []
    target = names or list(_PROVIDER_REGISTRY.keys())
    for name in target:
        cls = _PROVIDER_REGISTRY.get(name)
        if cls is None:
            logger.warning("Unknown news provider: %s", name)
            continue
        provider = cls()
        if provider.is_configured():
            providers.append(provider)
        else:
            logger.info("Provider %s not configured, skipping", name)
    return providers


def _get_google_news_provider(symbols: List[str]) -> Optional[GoogleNewsProvider]:
    """Build a GoogleNewsProvider from symbol codes by looking up company names."""
    targets = []
    for symbol in symbols:
        row = storage.get_stock_by_symbol(symbol)
        name = row.get("name") if row else None
        if name and name != symbol:
            targets.append((symbol, name))
        else:
            logger.warning("No company name found for symbol %s, skipping Google News", symbol)
    return GoogleNewsProvider(targets) if targets else None


async def ingest(req: NewsIngestRequest) -> List[IngestionStats]:
    """
    Run a full ingestion cycle across all configured providers.

    Steps per provider:
    1. Fetch raw articles
    2. Normalize
    3. Dedup against stored recent articles
    4. Store canonical articles + raw records
    """
    providers = _get_providers(req.providers)
    if req.symbols:
        gp = _get_google_news_provider(req.symbols)
        if gp:
            providers = [gp]
    logs: List[IngestionStats] = []

    for provider in providers:
        log_id = storage.start_ingestion_log(provider.name)
        stats = IngestionStats(
            provider=provider.name,
            started_at=datetime.now(timezone.utc),
        )
        try:
            raw_articles = await provider.fetch(max_articles=req.max_per_provider)
            stats.fetched = len(raw_articles)
            logger.info("[%s] fetched %d articles", provider.name, stats.fetched)

            # Normalize
            normalized = [norm_module.normalize(r) for r in raw_articles]

            # Load recent articles for dedup comparison
            recent = storage.get_recent_article_titles(window_hours=24)

            # Filter duplicates
            unique, dup_count = dedup_module.filter_duplicates(normalized, existing_recent=recent)
            stats.deduplicated = dup_count
            logger.info("[%s] %d duplicates removed, %d unique", provider.name, dup_count, len(unique))

            # Store
            raw_by_url = {r.url: r for r in raw_articles}
            inserted = 0
            for article in unique:
                raw = raw_by_url.get(article.url)
                newly_inserted = storage.upsert_article(article)
                if newly_inserted:
                    inserted += 1
                    # Force-map to target symbol if fetched by Google News
                    if raw and raw.raw_json and "symbol" in raw.raw_json:
                        storage.upsert_symbol_maps([
                            ArticleSymbolMap(
                                article_id=article.id,
                                symbol=raw.raw_json["symbol"],
                                company_name=raw.raw_json.get("company_name"),
                                scope="stock",
                                relevance=0.8,
                            )
                        ])
                    # Also store raw record
                    if raw:
                        storage.upsert_raw_article(
                            article_id=article.id,
                            provider=provider.name,
                            external_id=raw.external_id,
                            title=raw.title,
                            body=raw.body,
                            url=raw.url,
                            source=raw.source,
                            author=raw.author,
                            published_at=raw.published_at,
                            category=raw.category,
                            raw_json=raw.raw_json,
                        )

            stats.inserted = inserted
            stats.status = "success"
            stats.finished_at = datetime.now(timezone.utc)
            logger.info("[%s] inserted %d new articles", provider.name, inserted)

        except Exception as exc:
            logger.error("[%s] ingestion failed: %s", provider.name, exc, exc_info=True)
            stats.status = "error"
            stats.error = str(exc)
            stats.finished_at = datetime.now(timezone.utc)

        storage.finish_ingestion_log(
            log_id,
            status=stats.status,
            fetched=stats.fetched,
            deduplicated=stats.deduplicated,
            inserted=stats.inserted,
            error=stats.error,
        )
        logs.append(stats)

    return logs


async def analyze_article(article_id: str, force: bool = False) -> bool:
    """
    Run entity mapping, event extraction, impact estimation, and signal
    generation for a single stored article.

    Returns True if analysis was performed, False if already done and force=False.
    """
    article_row = storage.get_article_by_id(article_id)
    if not article_row:
        logger.warning("Article not found: %s", article_id)
        return False

    # Skip if already analyzed (unless forced)
    existing_event = storage.get_event_for_article(article_id)
    if existing_event and not force:
        logger.debug("Article %s already analyzed, skipping", article_id)
        return False

    # Reconstruct NormalizedArticle from DB row
    from datetime import datetime, timezone

    def _parse_dt(s):
        if not s:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)

    article = NormalizedArticle(
        id=article_row["id"],
        title=article_row["title"],
        summary=article_row.get("summary"),
        url=article_row["url"],
        source=article_row["source"],
        author=article_row.get("author"),
        published_at=_parse_dt(article_row["publishedAt"]),
        crawled_at=_parse_dt(article_row["crawledAt"]),
        category=article_row.get("category"),
        language=article_row.get("language", "ko"),
        body_hash=article_row.get("bodyHash"),
        canonical_id=article_row.get("canonicalId"),
        is_canonical=bool(article_row.get("isCanonical", 1)),
    )

    # Entity mapping
    symbol_maps = entity_mapper.map_entities(article)
    storage.upsert_symbol_maps(symbol_maps)

    # Event extraction
    event = event_extractor.extract_event(article)
    storage.upsert_event(event)

    # Impact estimation (use primary symbol if available)
    primary_symbol: Optional[str] = None
    stock_maps = [m for m in symbol_maps if m.scope == "stock" and not m.symbol.startswith("__")]
    if stock_maps:
        # Highest relevance first
        primary_symbol = max(stock_maps, key=lambda m: m.relevance).symbol

    impact = impact_model.estimate_impact(article, event, primary_symbol)
    storage.upsert_impact(impact)

    # Signal generation
    signals = impact_model.build_signals(article, event, impact, symbol_maps)
    storage.upsert_signals(signals)

    logger.debug(
        "Analyzed article %s: event=%s sentiment=%s impact=%.2f alert=%s",
        article_id, event.event_type, event.sentiment, impact.impact_score, impact.risk_alert_level,
    )
    return True


async def ingest_and_analyze(req: NewsIngestRequest) -> Tuple[List[IngestionStats], int]:
    """
    Convenience: ingest then analyze all newly inserted articles.

    Returns (ingestion_logs, analyzed_count).
    """
    logs = await ingest(req)

    # Gather recently inserted article IDs (those without events yet)
    conn_rows = storage.get_top_articles(limit=200)
    analyzed = 0
    for row in conn_rows:
        event_row = storage.get_event_for_article(row["id"])
        if not event_row:
            success = await analyze_article(row["id"])
            if success:
                analyzed += 1

    return logs, analyzed


def get_risk_alerts_for_virtual_trading(
    symbols: List[str],
    as_of: Optional[datetime] = None,
) -> Dict[str, dict]:
    """
    Returns active risk alerts for a list of symbols.
    Used by VirtualTrader to pause/reduce positions on high-risk news.

    Only considers signals where valid_from <= as_of (no look-ahead).
    """
    from datetime import timedelta
    result: Dict[str, dict] = {}
    cutoff = as_of or datetime.now(timezone.utc)

    for symbol in symbols:
        signals = storage.get_signals_for_symbol(
            symbol=symbol,
            as_of=cutoff,
            signal_type="news_risk_alert",
            limit=5,
        )
        if not signals:
            continue

        recent_signals = [s for s in signals if s.get("value", 0) > 0.0]
        if not recent_signals:
            continue

        # Use the most recent high-risk signal
        latest = recent_signals[0]
        import json
        metadata = {}
        try:
            metadata = json.loads(latest.get("metadata") or "{}")
        except Exception:
            pass

        result[symbol] = {
            "symbol": symbol,
            "risk_alert_level": metadata.get("risk_alert", "low"),
            "signal_value": latest.get("value", 0),
            "confidence": latest.get("confidence", 0),
            "valid_from": latest.get("validFrom"),
            "article_title": latest.get("title"),
            "article_url": latest.get("url"),
            "event_type": metadata.get("event_type"),
        }

    return result
