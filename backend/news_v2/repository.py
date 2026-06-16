"""
NewsRepository — pure DB I/O for news_v2.

Service-layer business rules (priority bumping, status transitions, AI calls)
do NOT live here. This module only knows how to read and write the four tables.
"""

from __future__ import annotations

import html
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from news_v2.models import (
    Article,
    CollectionStatus,
    IngestionLog,
    CollectionQueueItem,
    NewsAnalysis,
    PriorityEvent,
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
    body_preview: Optional[str] = None


_HTML_BREAK_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTISPACE_RE = re.compile(r"\s+")
_COMPARE_NORMALIZE_RE = re.compile(r"[\s\"'`.,:;!?()\[\]{}<>|/\-]+")


def _normalize_preview_lines(text: Optional[str]) -> list[str]:
    if not text:
        return []
    cleaned = html.unescape(text).replace("\xa0", " ")
    cleaned = _HTML_BREAK_RE.sub("\n", cleaned)
    cleaned = _HTML_TAG_RE.sub(" ", cleaned)
    lines = [
        _MULTISPACE_RE.sub(" ", line).strip(" -:|/\t")
        for line in cleaned.splitlines()
    ]
    return [line for line in lines if line]


def _normalize_preview_text(text: Optional[str]) -> Optional[str]:
    lines = _normalize_preview_lines(text)
    return lines[0] if lines else None


def _strip_trailing_source(text: str, source: str) -> str:
    normalized_source = _normalize_preview_text(source) or ""
    candidate = text.strip()
    if not normalized_source:
        return candidate
    if candidate.endswith(normalized_source):
        candidate = candidate[: -len(normalized_source)].rstrip(" -:|/")
    return candidate.strip()


def _canonicalize_compare(text: Optional[str], source: str) -> str:
    normalized = _strip_trailing_source(_normalize_preview_text(text) or "", source)
    return _COMPARE_NORMALIZE_RE.sub("", normalized).lower()


def _build_body_preview(
    title: str,
    raw_content: Optional[str],
    summary: Optional[str],
    source: str,
) -> Optional[str]:
    title_key = _canonicalize_compare(title, source)
    for text in (raw_content, summary):
        for line in _normalize_preview_lines(text):
            candidate = _strip_trailing_source(line, source)
            if not candidate:
                continue
            if _canonicalize_compare(candidate, source) == title_key:
                continue
            if title and candidate.startswith(title):
                remainder = candidate[len(title):].lstrip(" -:|/")
                if not remainder:
                    continue
                candidate = remainder
            if _canonicalize_compare(candidate, source) == title_key:
                continue
            return candidate[:240]
        candidate = _normalize_preview_text(text)
        if not candidate:
            continue
        candidate = _strip_trailing_source(candidate, source)
        if _canonicalize_compare(candidate, source) == title_key:
            continue
        if title and candidate.startswith(title):
            candidate = candidate[len(title):].lstrip(" -:|/")
            if not candidate:
                continue
        if _canonicalize_compare(candidate, source) == title_key:
            continue
        return candidate[:240]
    return None


@dataclass
class QueueMonitorDTO:
    symbol: str
    queue: str
    score: float
    reason: Optional[str]
    is_trending: bool
    updated_at: datetime


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
                body_preview=_build_body_preview(
                    raw.title,
                    raw.raw_content,
                    analysis.summary if analysis else None,
                    raw.source,
                ),
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

    async def delete_stock_news_cache(self, symbol: str) -> int:
        result = await self.session.execute(
            delete(StockNewsCache).where(StockNewsCache.symbol == symbol)
        )
        return result.rowcount or 0

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

    async def record_priority_event(
        self,
        *,
        symbol: str,
        event_type: str,
        user_id: Optional[str] = None,
        weight: float = 1.0,
        metadata: Optional[dict] = None,
        current_view_ttl_s: int = 600,
    ) -> None:
        """Append the user-demand event and update the materialized counters."""
        now = _utcnow()
        self.session.add(
            PriorityEvent(
                symbol=symbol,
                event_type=event_type,
                user_id=user_id,
                weight=max(float(weight or 1.0), 0.0),
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
                created_at=now,
            )
        )
        row = await self.get_priority(symbol)
        if row is None:
            row = PriorityScore(symbol=symbol)
            self.session.add(row)

        if event_type in {"current_view", "stock_view", "stock_detail_view"}:
            row.last_viewed = now
            row.current_view_until = now + timedelta(seconds=current_view_ttl_s)
            row.view_count_24h = (row.view_count_24h or 0) + int(max(weight, 1.0))
        elif event_type == "watchlist_add":
            row.watchlist_count = max((row.watchlist_count or 0) + int(max(weight, 1.0)), 0)
        elif event_type == "watchlist_remove":
            row.watchlist_count = max((row.watchlist_count or 0) - int(max(weight, 1.0)), 0)
        elif event_type == "holding_buy":
            row.holding_count = max((row.holding_count or 0) + int(max(weight, 1.0)), 0)
        elif event_type == "holding_sell":
            row.holding_count = max((row.holding_count or 0) - int(max(weight, 1.0)), 0)
        elif event_type in {"stock_search", "search"}:
            row.search_count_24h = (row.search_count_24h or 0) + int(max(weight, 1.0))
        row.updated_at = now

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

    async def list_symbols_in_queue(self, queue: str, limit: int = 500) -> list[str]:
        stmt = (
            select(CollectionQueueItem.symbol)
            .where(CollectionQueueItem.queue == queue)
            .order_by(CollectionQueueItem.score.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_collection_queue(
        self,
        *,
        symbol: str,
        queue: str,
        score: float,
        reason: Optional[str],
        is_trending: bool,
    ) -> None:
        row = (
            await self.session.execute(
                select(CollectionQueueItem).where(CollectionQueueItem.symbol == symbol)
            )
        ).scalar_one_or_none()
        now = _utcnow()
        if row is None:
            self.session.add(
                CollectionQueueItem(
                    symbol=symbol,
                    queue=queue,
                    score=score,
                    reason=reason,
                    is_trending=bool(is_trending),
                    enqueued_at=now,
                    updated_at=now,
                )
            )
            return
        row.queue = queue
        row.score = score
        row.reason = reason
        row.is_trending = bool(is_trending)
        row.updated_at = now

    async def list_queue_monitor(self, queue: Optional[str] = None, limit: int = 100) -> list[QueueMonitorDTO]:
        stmt = select(CollectionQueueItem)
        if queue:
            stmt = stmt.where(CollectionQueueItem.queue == queue)
        stmt = stmt.order_by(CollectionQueueItem.score.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return [
            QueueMonitorDTO(
                symbol=row.symbol,
                queue=row.queue,
                score=row.score,
                reason=row.reason,
                is_trending=bool(row.is_trending),
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def list_all_priorities(self) -> list[PriorityScore]:
        return list(
            (await self.session.execute(select(PriorityScore))).scalars().all()
        )

    async def sync_holding_counts_from_virtual_positions(
        self, reader: Optional[AsyncSession] = None
    ) -> int:
        """Mirror actual virtual-account holdings into priority rows.

        This reads committed positions, not order intents. A symbol is treated
        as held when at least one virtual account has quantity > 0.

        `reader`(주어지면)에서 앱 테이블을 읽고 PriorityScore는 self.session(news DB)에
        쓴다 — news DB가 Postgres로 갈려 앱 테이블이 없을 때 앱 DB에서 읽기 위함.
        """
        src = reader or self.session
        rows = (
            await src.execute(
                text(
                    'SELECT "symbol", COUNT(DISTINCT "accountId") '
                    'FROM "VirtualPosition" '
                    'WHERE "quantity" > 0 '
                    'GROUP BY "symbol"'
                )
            )
        ).all()
        await self.session.execute(update(PriorityScore).values(holding_count=0))
        for symbol, count in rows:
            row = await self.get_priority(str(symbol))
            if row is None:
                self.session.add(PriorityScore(symbol=str(symbol), holding_count=int(count)))
            else:
                row.holding_count = int(count)
                row.updated_at = _utcnow()
        return len(rows)

    async def sync_watchlist_counts_from_db(self, reader: Optional[AsyncSession] = None) -> int:
        """Mirror watchlist membership into priority rows (reads app DB when given)."""
        src = reader or self.session
        rows = (
            await src.execute(
                text(
                    'SELECT "symbol", COUNT(*) '
                    'FROM "WatchlistSymbol" '
                    'GROUP BY "symbol"'
                )
            )
        ).all()
        await self.session.execute(update(PriorityScore).values(watchlist_count=0))
        for symbol, count in rows:
            row = await self.get_priority(str(symbol))
            if row is None:
                self.session.add(PriorityScore(symbol=str(symbol), watchlist_count=int(count)))
            else:
                row.watchlist_count = int(count)
                row.updated_at = _utcnow()
        return len(rows)

    async def sync_search_counts_from_db(self, reader: Optional[AsyncSession] = None) -> int:
        """Mirror aggregate stock search counts into priority rows (reads app DB when given)."""
        src = reader or self.session
        rows = (
            await src.execute(
                text(
                    'SELECT "symbol", "count" '
                    'FROM "SearchCount" '
                    'WHERE "count" > 0'
                )
            )
        ).all()
        await self.session.execute(update(PriorityScore).values(search_count_24h=0))
        for symbol, count in rows:
            row = await self.get_priority(str(symbol))
            if row is None:
                self.session.add(PriorityScore(symbol=str(symbol), search_count_24h=int(count)))
            else:
                row.search_count_24h = int(count)
                row.updated_at = _utcnow()
        return len(rows)

    async def ensure_stock_universe_priority_rows(
        self, limit: int = 5000, reader: Optional[AsyncSession] = None
    ) -> int:
        """Ensure cold-queue coverage exists for the known stock universe (reads app DB when given)."""
        src = reader or self.session
        rows = (
            await src.execute(
                text('SELECT "symbol" FROM "Stock" WHERE "symbol" IS NOT NULL LIMIT :limit'),
                {"limit": limit},
            )
        ).all()
        created = 0
        for (symbol,) in rows:
            if not symbol:
                continue
            if await self.get_priority(str(symbol)) is None:
                self.session.add(PriorityScore(symbol=str(symbol)))
                created += 1
        return created

    async def news_counts_by_symbol(self, *, since: datetime) -> dict[str, int]:
        stmt = (
            select(StockNewsCache.symbol, func.count(StockNewsCache.news_id))
            .where(StockNewsCache.published_at >= since)
            .group_by(StockNewsCache.symbol)
        )
        return {symbol: int(count) for symbol, count in (await self.session.execute(stmt)).all()}

    # ─── status ────────────────────────────────────────────────────────────────

    async def get_status(self, symbol: str) -> Optional[CollectionStatus]:
        return (
            await self.session.execute(
                select(CollectionStatus).where(CollectionStatus.symbol == symbol)
            )
        ).scalar_one_or_none()

    async def list_collecting_symbols(
        self,
        *,
        older_than: datetime,
        limit: int = 20,
    ) -> list[str]:
        stmt = (
            select(CollectionStatus.symbol)
            .where(
                CollectionStatus.status == Status.COLLECTING,
                CollectionStatus.last_attempt_at <= older_than,
            )
            .order_by(CollectionStatus.last_attempt_at.asc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

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
