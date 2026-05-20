"""
SQLAlchemy ORM models for news_v2.

These mirror the Prisma models (NewsV2Article, NewsV2PriorityScore,
NewsV2CollectionStatus, NewsV2IngestionLog). We keep two definitions
intentionally: Prisma owns migrations for the Next.js side, SQLAlchemy
gives Python workers + FastAPI native async access without going through
Node.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


# Postgres uses BIGINT; SQLite needs plain INTEGER for autoincrement.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


class Base(DeclarativeBase):
    pass


class JSONList(TypeDecorator):
    """Store a Python list as a JSON-encoded TEXT column.

    Postgres could use TEXT[] / JSONB, but we keep this portable so the same
    code runs on dev SQLite. The column type stays TEXT either way.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Optional[list], dialect):  # type: ignore[override]
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: Optional[str], dialect):  # type: ignore[override]
        if value is None or value == "":
            return []
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return []


class Article(Base):
    __tablename__ = "NewsV2Article"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column("normalizedTitle", Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column("publishedAt", DateTime, nullable=False)
    sentiment: Mapped[Optional[str]] = mapped_column(String(16))
    sentiment_score: Mapped[Optional[float]] = mapped_column("sentimentScore", Float)
    impact_level: Mapped[Optional[str]] = mapped_column("impactLevel", String(16))
    market_effect: Mapped[Optional[str]] = mapped_column("marketEffect", Text)
    related_symbols: Mapped[list] = mapped_column("relatedSymbols", JSONList, default=list)
    ai_summary: Mapped[Optional[str]] = mapped_column("aiSummary", Text)
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="analyzed")
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("symbol", "hash", name="uq_newsv2_symbol_hash"),
        Index("idx_newsv2_symbol_pub", "symbol", "publishedAt"),
        Index("idx_newsv2_hash", "hash"),
        Index("idx_newsv2_pub", "publishedAt"),
    )


class PriorityScore(Base):
    __tablename__ = "NewsV2PriorityScore"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_collected: Mapped[Optional[datetime]] = mapped_column("lastCollected", DateTime)
    last_viewed: Mapped[Optional[datetime]] = mapped_column("lastViewed", DateTime)
    view_count_24h: Mapped[int] = mapped_column("viewCount24h", Integer, default=0, nullable=False)
    watchlist_count: Mapped[int] = mapped_column("watchlistCount", Integer, default=0, nullable=False)
    search_count_24h: Mapped[int] = mapped_column("searchCount24h", Integer, default=0, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    turnover: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ai_importance: Mapped[float] = mapped_column("aiImportance", Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (Index("idx_newsv2_priority_tier", "tier", "score"),)


class CollectionStatus(Base):
    __tablename__ = "NewsV2CollectionStatus"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="NOT_COLLECTED", nullable=False)
    last_success_at: Mapped[Optional[datetime]] = mapped_column("lastSuccessAt", DateTime)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column("lastAttemptAt", DateTime)
    last_error: Mapped[Optional[str]] = mapped_column("lastError", Text)
    attempt_count: Mapped[int] = mapped_column("attemptCount", Integer, default=0, nullable=False)
    in_flight_job_id: Mapped[Optional[str]] = mapped_column("inFlightJobId", String(64))
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class IngestionLog(Base):
    __tablename__ = "NewsV2IngestionLog"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[Optional[str]] = mapped_column("jobId", String(64))
    started_at: Mapped[datetime] = mapped_column("startedAt", DateTime, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column("finishedAt", DateTime)
    fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deduped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inserted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (Index("idx_newsv2_ingest_symbol_time", "symbol", "startedAt"),)


# ─── status constants ───────────────────────────────────────────────────────────

class Status:
    NOT_COLLECTED = "NOT_COLLECTED"
    COLLECTING = "COLLECTING"
    READY = "READY"
    STALE = "STALE"
    NO_NEWS_FOUND = "NO_NEWS_FOUND"
    FAILED = "FAILED"

    ALL = {NOT_COLLECTED, COLLECTING, READY, STALE, NO_NEWS_FOUND, FAILED}
