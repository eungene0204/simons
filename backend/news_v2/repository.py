"""
NewsRepository — pure DB I/O for news_v2.

Service-layer business rules (priority bumping, status transitions, AI calls)
do NOT live here. This module only knows how to read and write the four tables.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from news_v2 import models
from news_v2.models import (
    Article,
    CollectionStatus,
    IngestionLog,
    NewsAnalysis,
    NewsRaw,
    NewsSymbolMap,
    PriorityScore,
    Status,
    StockNewsCache,
)


@dataclass
class ArticleDTO:
    """Plain transport object — keeps callers (cache, API) decoupled from ORM."""

    id: int
    symbol: str
    title: str
    summary: Optional[str]
    source: str
    url: str
    published_at: datetime
    sentiment: Optional[str]
    sentiment_score: Optional[float]
    impact_level: Optional[str]
    market_effect: Optional[str]
    related_symbols: list[str]
    ai_summary: Optional[str]
    hash: str

    @classmethod
    def from_orm(cls, a: Article) -> "ArticleDTO":
        return cls(
            id=a.id,
            symbol=a.symbol,
            title=a.title,
            summary=a.summary,
            source=a.source,
            url=a.url,
            published_at=a.published_at,
            sentiment=a.sentiment,
            sentiment_score=a.sentiment_score,
            impact_level=a.impact_level,
            market_effect=a.market_effect,
            related_symbols=list(a.related_symbols or []),
            ai_summary=a.ai_summary,
            hash=a.hash,
        )


@dataclass
class CachedNewsDTO:
    """Final stock-news-tab row, already materialized for immediate rendering."""

    news_id: str
    title: str
    url: str
    source: str
    published_at: datetime
    summary: Optional[str]
    sentiment: str
    impact_score: float
    importance: str
    market_effect: Optional[str]
    related_symbols: list[str]
    rank_score: float
    cached_at: datetime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_news_id(url: str, title_hash: str) -> str:
    return hashlib.sha256(f"{url.strip()}|{title_hash}".encode("utf-8")).hexdigest()


class NewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── articles ──────────────────────────────────────────────────────────────

    async def list_recent(self, symbol: str, limit: int = 20) -> list[ArticleDTO]:
        stmt = (
            select(Article)
            .where(Article.symbol == symbol)
            .order_by(Article.published_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [ArticleDTO.from_orm(r) for r in rows]

    async def list_cached_news(self, symbol: str, limit: int = 30) -> list[CachedNewsDTO]:
        stmt = (
            select(StockNewsCache, NewsRaw, NewsAnalysis)
            .join(NewsRaw, NewsRaw.news_id == StockNewsCache.news_id)
            .outerjoin(NewsAnalysis, NewsAnalysis.news_id == StockNewsCache.news_id)
            .where(StockNewsCache.symbol == symbol)
            .order_by(StockNewsCache.published_at.desc(), StockNewsCache.rank_score.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            CachedNewsDTO(
                news_id=raw.news_id,
                title=raw.title,
                url=raw.url,
                source=raw.source,
                published_at=cache.published_at,
                summary=(analysis.summary if analysis else None),
                sentiment=(analysis.sentiment if analysis and analysis.sentiment else "neutral"),
                impact_score=float(analysis.impact_score if analysis and analysis.impact_score is not None else 0.0),
                importance=(analysis.importance if analysis and analysis.importance else "low"),
                market_effect=(analysis.market_effect if analysis else None),
                related_symbols=list(analysis.related_symbols or []) if analysis else [],
                rank_score=float(cache.rank_score or 0.0),
                cached_at=cache.cached_at,
            )
            for cache, raw, analysis in rows
        ]

    async def get_cache_last_updated(self, symbol: str) -> Optional[datetime]:
        stmt = select(func.max(StockNewsCache.cached_at)).where(StockNewsCache.symbol == symbol)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_raw_news(self, news_id: str) -> Optional[NewsRaw]:
        return (
            await self.session.execute(select(NewsRaw).where(NewsRaw.news_id == news_id))
        ).scalar_one_or_none()

    async def get_symbols_for_news(self, news_id: str) -> list[NewsSymbolMap]:
        rows = (
            await self.session.execute(
                select(NewsSymbolMap).where(NewsSymbolMap.news_id == news_id)
            )
        ).scalars().all()
        return list(rows)

    async def upsert_raw_news(self, payload: dict) -> tuple[str, bool]:
        """Insert canonical raw news, deduping by URL first, then normalized title hash."""
        existing = (
            await self.session.execute(
                select(NewsRaw).where(
                    or_(
                        NewsRaw.url == payload["url"],
                        NewsRaw.title_hash == payload["title_hash"],
                    )
                )
            )
        ).scalars().first()
        if existing is not None:
            if _is_better_representative(payload, existing):
                existing.title = payload["title"]
                existing.normalized_title = payload["normalized_title"]
                existing.title_hash = payload["title_hash"]
                existing.url = payload["url"]
                existing.source = payload["source"]
                existing.published_at = payload["published_at"]
                existing.raw_content = payload.get("raw_content")
                existing.content_quality = payload.get("content_quality", 0.0)
            return existing.news_id, False

        news_id = payload.get("news_id") or make_news_id(payload["url"], payload["title_hash"])
        self.session.add(
            NewsRaw(
                news_id=news_id,
                title=payload["title"],
                normalized_title=payload["normalized_title"],
                title_hash=payload["title_hash"],
                url=payload["url"],
                source=payload["source"],
                published_at=payload["published_at"],
                raw_content=payload.get("raw_content"),
                content_quality=payload.get("content_quality", 0.0),
            )
        )
        return news_id, True

    async def upsert_news_symbol_maps(self, news_id: str, maps: Iterable[dict]) -> None:
        await self.session.execute(delete(NewsSymbolMap).where(NewsSymbolMap.news_id == news_id))
        for item in maps:
            self.session.add(
                NewsSymbolMap(
                    news_id=news_id,
                    symbol=item["symbol"],
                    company_name=item.get("company_name"),
                    relevance=item.get("relevance", 1.0),
                    evidence=item.get("evidence"),
                )
            )

    async def upsert_news_analysis(self, news_id: str, fields: dict) -> None:
        row = (
            await self.session.execute(
                select(NewsAnalysis).where(NewsAnalysis.news_id == news_id)
            )
        ).scalar_one_or_none()
        if row is None:
            self.session.add(NewsAnalysis(news_id=news_id, **fields))
            return
        for key, value in fields.items():
            setattr(row, key, value)
        row.analyzed_at = _utcnow()

    async def upsert_stock_news_cache(
        self,
        *,
        symbol: str,
        news_id: str,
        published_at: datetime,
        rank_score: float,
    ) -> None:
        row = (
            await self.session.execute(
                select(StockNewsCache).where(
                    StockNewsCache.symbol == symbol,
                    StockNewsCache.news_id == news_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            self.session.add(
                StockNewsCache(
                    symbol=symbol,
                    news_id=news_id,
                    published_at=published_at,
                    rank_score=rank_score,
                    cached_at=_utcnow(),
                )
            )
            return
        row.published_at = published_at
        row.rank_score = rank_score
        row.cached_at = _utcnow()

    async def get_latest_published_at(self, symbol: str) -> Optional[datetime]:
        stmt = select(func.max(Article.published_at)).where(Article.symbol == symbol)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_article(self, payload: dict) -> bool:
        """Insert if (symbol, hash) is new. Returns True if a new row was inserted."""
        # Check existence first — portable across SQLite/PG without needing ON CONFLICT
        # specifics, at the cost of one extra SELECT. For high write volumes, swap to
        # dialect-specific upsert.
        existing = (
            await self.session.execute(
                select(Article.id).where(
                    Article.symbol == payload["symbol"], Article.hash == payload["hash"]
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False

        article = Article(**payload)
        self.session.add(article)
        return True

    async def update_analysis(self, article_id: int, fields: dict) -> None:
        await self.session.execute(
            update(Article).where(Article.id == article_id).values(**fields)
        )

    async def delete_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(Article).where(Article.published_at < cutoff)
        )
        return result.rowcount or 0

    # ─── priority ──────────────────────────────────────────────────────────────

    async def get_priority(self, symbol: str) -> Optional[PriorityScore]:
        return (
            await self.session.execute(
                select(PriorityScore).where(PriorityScore.symbol == symbol)
            )
        ).scalar_one_or_none()

    async def bump_priority(self, symbol: str, delta: float) -> None:
        """+= delta on score; touch last_viewed and view_count_24h."""
        row = await self.get_priority(symbol)
        now = _utcnow()
        if row is None:
            self.session.add(
                PriorityScore(
                    symbol=symbol,
                    score=max(delta, 0.0),
                    tier=3,
                    last_viewed=now,
                    view_count_24h=1,
                )
            )
        else:
            row.score = (row.score or 0.0) + delta
            row.last_viewed = now
            row.view_count_24h = (row.view_count_24h or 0) + 1

    async def set_priority(self, symbol: str, **fields) -> None:
        row = await self.get_priority(symbol)
        if row is None:
            self.session.add(PriorityScore(symbol=symbol, **fields))
            return
        for k, v in fields.items():
            setattr(row, k, v)

    async def list_symbols_in_tier(self, tier: int, limit: int = 500) -> list[str]:
        stmt = (
            select(PriorityScore.symbol)
            .where(PriorityScore.tier == tier)
            .order_by(PriorityScore.score.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_all_priorities(self) -> list[PriorityScore]:
        return list(
            (await self.session.execute(select(PriorityScore))).scalars().all()
        )

    # ─── status ────────────────────────────────────────────────────────────────

    async def get_status(self, symbol: str) -> Optional[CollectionStatus]:
        return (
            await self.session.execute(
                select(CollectionStatus).where(CollectionStatus.symbol == symbol)
            )
        ).scalar_one_or_none()

    async def set_status(
        self,
        symbol: str,
        status: str,
        *,
        error: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> None:
        if status not in Status.ALL:
            raise ValueError(f"Invalid status: {status}")
        row = await self.get_status(symbol)
        now = _utcnow()
        if row is None:
            row = CollectionStatus(symbol=symbol, status=status)
            self.session.add(row)
        row.status = status
        row.last_attempt_at = now
        if error is not None:
            row.last_error = error
            row.attempt_count = (row.attempt_count or 0) + 1
        if status in {Status.READY, Status.NO_NEWS_FOUND}:
            row.last_success_at = now
            row.attempt_count = 0
            row.last_error = None
        if job_id is not None:
            row.in_flight_job_id = job_id
        if status not in {Status.COLLECTING}:
            row.in_flight_job_id = None

    # ─── ingestion log ─────────────────────────────────────────────────────────

    async def log_ingestion(
        self,
        *,
        symbol: str,
        provider: str,
        job_id: Optional[str],
        started_at: datetime,
        finished_at: Optional[datetime],
        fetched: int,
        deduped: int,
        inserted: int,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        self.session.add(
            IngestionLog(
                symbol=symbol,
                provider=provider,
                job_id=job_id,
                started_at=started_at,
                finished_at=finished_at,
                fetched=fetched,
                deduped=deduped,
                inserted=inserted,
                status=status,
                error=error,
            )
        )


_SOURCE_PRIORITY = {
    "연합뉴스": 100,
    "한국경제": 90,
    "매일경제": 88,
    "머니투데이": 84,
    "이데일리": 82,
    "google_news": 50,
}


def _source_priority(source: str) -> int:
    return _SOURCE_PRIORITY.get(source, 10)


def _is_better_representative(payload: dict, existing: NewsRaw) -> bool:
    existing_score = (
        existing.published_at,
        _source_priority(existing.source),
        float(existing.content_quality or 0.0),
    )
    incoming_score = (
        payload.get("published_at") or datetime.min,
        _source_priority(payload.get("source") or ""),
        float(payload.get("content_quality") or 0.0),
    )
    return incoming_score > existing_score
