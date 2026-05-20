"""
NewsRepository — pure DB I/O for news_v2.

Service-layer business rules (priority bumping, status transitions, AI calls)
do NOT live here. This module only knows how to read and write the four tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from news_v2 import models
from news_v2.models import Article, CollectionStatus, IngestionLog, PriorityScore, Status


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
        if status == Status.READY:
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
