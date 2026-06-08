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
    Boolean,
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


class NewsRaw(Base):
    __tablename__ = "news_raw"

    news_id: Mapped[str] = mapped_column("newsId", String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column("normalizedTitle", Text, nullable=False)
    title_hash: Mapped[str] = mapped_column("titleHash", String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column("publishedAt", DateTime, nullable=False)
    raw_content: Mapped[Optional[str]] = mapped_column("rawContent", Text)
    content_quality: Mapped[float] = mapped_column("contentQuality", Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_news_raw_published", "publishedAt"),
        Index("idx_news_raw_title_hash", "titleHash"),
        Index("idx_news_raw_source_published", "source", "publishedAt"),
    )


class NewsAnalysis(Base):
    __tablename__ = "news_analysis"

    news_id: Mapped[str] = mapped_column("newsId", String(64), primary_key=True)
    sentiment: Mapped[Optional[str]] = mapped_column(String(16))
    impact_score: Mapped[Optional[float]] = mapped_column("impactScore", Float)
    importance: Mapped[Optional[str]] = mapped_column(String(16))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    market_effect: Mapped[Optional[str]] = mapped_column("marketEffect", Text)
    related_symbols: Mapped[list] = mapped_column("relatedSymbols", JSONList, default=list)
    status: Mapped[str] = mapped_column(String(16), default="analyzed", nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text)
    analyzed_at: Mapped[datetime] = mapped_column("analyzedAt", DateTime, default=datetime.utcnow)

    __table_args__ = (Index("idx_news_analysis_analyzed", "analyzedAt"),)


class NewsSymbolMap(Base):
    __tablename__ = "news_symbol_map"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    news_id: Mapped[str] = mapped_column("newsId", String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    company_name: Mapped[Optional[str]] = mapped_column("companyName", String(128))
    relevance: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("newsId", "symbol", name="uq_news_symbol_map_news_symbol"),
        Index("idx_news_symbol_map_symbol", "symbol"),
        Index("idx_news_symbol_map_news", "newsId"),
    )


class StockNewsCache(Base):
    __tablename__ = "stock_news_cache"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    news_id: Mapped[str] = mapped_column("newsId", String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column("publishedAt", DateTime, nullable=False)
    rank_score: Mapped[float] = mapped_column("rankScore", Float, default=0.0, nullable=False)
    cached_at: Mapped[datetime] = mapped_column("cachedAt", DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "newsId", name="uq_stock_news_cache_symbol_news"),
        Index("idx_stock_news_cache_symbol_published", "symbol", "publishedAt"),
        Index("idx_stock_news_cache_symbol_rank", "symbol", "rankScore"),
    )


class PriorityScore(Base):
    __tablename__ = "NewsV2PriorityScore"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    queue: Mapped[str] = mapped_column(String(16), default="cold", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    is_trending: Mapped[bool] = mapped_column("isTrending", Boolean, default=False, nullable=False)
    last_collected: Mapped[Optional[datetime]] = mapped_column("lastCollected", DateTime)
    last_viewed: Mapped[Optional[datetime]] = mapped_column("lastViewed", DateTime)
    current_view_until: Mapped[Optional[datetime]] = mapped_column("currentViewUntil", DateTime)
    view_count_24h: Mapped[int] = mapped_column("viewCount24h", Integer, default=0, nullable=False)
    watchlist_count: Mapped[int] = mapped_column("watchlistCount", Integer, default=0, nullable=False)
    holding_count: Mapped[int] = mapped_column("holdingCount", Integer, default=0, nullable=False)
    search_count_24h: Mapped[int] = mapped_column("searchCount24h", Integer, default=0, nullable=False)
    volatility: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    turnover: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    market_cap: Mapped[float] = mapped_column("marketCap", Float, default=0.0, nullable=False)
    trading_value: Mapped[float] = mapped_column("tradingValue", Float, default=0.0, nullable=False)
    news_count_1h: Mapped[int] = mapped_column("newsCount1h", Integer, default=0, nullable=False)
    news_count_24h: Mapped[int] = mapped_column("newsCount24h", Integer, default=0, nullable=False)
    news_velocity: Mapped[float] = mapped_column("newsVelocity", Float, default=0.0, nullable=False)
    index_member: Mapped[int] = mapped_column("indexMember", Integer, default=0, nullable=False)
    ai_importance: Mapped[float] = mapped_column("aiImportance", Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_newsv2_priority_tier", "tier", "score"),
        Index("idx_newsv2_priority_queue", "queue", "score"),
        Index("idx_newsv2_priority_trending", "isTrending", "score"),
    )


class PriorityEvent(Base):
    __tablename__ = "NewsV2PriorityEvent"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column("eventType", String(32), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column("userId", String(64))
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column("metadataJson", Text)
    created_at: Mapped[datetime] = mapped_column("createdAt", DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_newsv2_priority_event_symbol_time", "symbol", "createdAt"),
        Index("idx_newsv2_priority_event_type_time", "eventType", "createdAt"),
    )


class CollectionQueueItem(Base):
    __tablename__ = "NewsV2CollectionQueueItem"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    queue: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    is_trending: Mapped[bool] = mapped_column("isTrending", Boolean, default=False, nullable=False)
    enqueued_at: Mapped[datetime] = mapped_column("enqueuedAt", DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("idx_newsv2_collection_queue", "queue", "score"),
        Index("idx_newsv2_collection_queue_updated", "updatedAt"),
    )


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
