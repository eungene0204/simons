"""
NewsService — the public surface used by FastAPI handlers and Celery tasks.

Hot path (tab view):
    get_for_symbol(symbol) → Redis → PG → COLLECTING (enqueue background job)

Collect path (worker):
    run_collect(symbol) → providers.fetch → normalize → dedup → persist → analyze

Analysis path (worker):
    run_analyze(article_id) → AINewsAgent → persist analysis fields → invalidate cache
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from news_v2 import dedup as dedup_mod
from news_v2 import observability as metrics
from news_v2.agent import AINewsAgent, build_agent
from news_v2.cache import NewsCache
from news_v2.config import Settings, get_settings
from news_v2.logging_setup import get_logger
from news_v2.models import Status
from news_v2.providers import fetch_for_symbol
from news_v2.repository import ArticleDTO, NewsRepository

log = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class NewsResponse:
    status: str
    source: str
    stale: bool
    items: list[ArticleDTO]
    fetched_at: Optional[datetime]
    message: Optional[str] = None


# ─── Queue abstraction (Celery preferred, in-process fallback) ─────────────────


class Queue:
    """Lightweight queue façade. Uses Celery if available, else logs + no-op.

    The fallback exists so dev environments without a broker can still use the
    rest of the pipeline (cache miss → COLLECTING → user re-checks later).
    """

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self._celery_app = None
        if cfg.queue_enabled:
            try:
                from news_v2.celery_app import celery_app

                self._celery_app = celery_app
            except Exception as e:  # pragma: no cover
                log.warning("celery_unavailable", error=str(e))

    @property
    def enabled(self) -> bool:
        return self._celery_app is not None

    def enqueue_collect(self, symbol: str, priority: str = "default") -> Optional[str]:
        if not self.enabled:
            log.info("queue_disabled_enqueue_skip", task="collect_news", symbol=symbol)
            return None
        queue = "news.collect.high" if priority == "high" else "news.collect.default"
        result = self._celery_app.send_task(
            "news_v2.tasks.collect_news", args=[symbol], queue=queue
        )
        return result.id

    def enqueue_refresh(self, symbol: str) -> Optional[str]:
        if not self.enabled:
            return None
        result = self._celery_app.send_task(
            "news_v2.tasks.refresh_stale_news", args=[symbol], queue="news.maintenance"
        )
        return result.id

    def enqueue_analyze(self, article_id: int) -> Optional[str]:
        if not self.enabled:
            return None
        result = self._celery_app.send_task(
            "news_v2.tasks.analyze_news", args=[article_id], queue="news.analyze"
        )
        return result.id


# ─── Service ───────────────────────────────────────────────────────────────────


class NewsService:
    def __init__(
        self,
        session: AsyncSession,
        cache: Optional[NewsCache] = None,
        queue: Optional[Queue] = None,
        agent: Optional[AINewsAgent] = None,
        cfg: Optional[Settings] = None,
    ) -> None:
        self.cfg = cfg or get_settings()
        self.repo = NewsRepository(session)
        self.cache = cache or NewsCache(self.cfg)
        self.queue = queue or Queue(self.cfg)
        self.agent = agent or build_agent(self.cfg)
        self.session = session

    # ─── public: read path ─────────────────────────────────────────────────────

    async def get_for_symbol(
        self, symbol: str, company_name: Optional[str] = None, limit: Optional[int] = None
    ) -> NewsResponse:
        page_size = min(limit or self.cfg.default_page_size, self.cfg.max_page_size)

        # 1) Always bump view counters — both Redis (fast aggregate) and PG (persisted).
        await self.cache.incr_views(symbol)
        await self.repo.bump_priority(symbol, delta=self.cfg.view_bonus)
        await self.session.commit()

        # 2) Redis HIT
        cached = await self.cache.get_articles(symbol)
        if cached is not None:
            metrics.cache_hits.labels(layer="redis").inc()
            status = await self.cache.get_status(symbol) or Status.READY
            stale = status == Status.STALE
            if stale:
                self.queue.enqueue_refresh(symbol)
            metrics.request_total.labels(status=status, source="redis").inc()
            return NewsResponse(
                status=status,
                source="redis",
                stale=stale,
                items=cached[:page_size],
                fetched_at=_utcnow(),
            )

        # 3) PG HIT
        rows = await self.repo.list_recent(symbol, limit=page_size)
        if rows:
            metrics.cache_hits.labels(layer="postgres").inc()
            priority = await self.repo.get_priority(symbol)
            last_collected = priority.last_collected if priority else None
            stale = self._is_stale(last_collected)
            await self.cache.set_articles(
                symbol,
                rows,
                ttl_s=self._cache_ttl_for(symbol),
            )
            status = Status.STALE if stale else Status.READY
            await self.cache.set_status(symbol, status)
            if stale:
                self.queue.enqueue_refresh(symbol)
            metrics.request_total.labels(status=status, source="postgres").inc()
            return NewsResponse(
                status=status,
                source="postgres",
                stale=stale,
                items=rows,
                fetched_at=rows[0].published_at if rows else None,
            )

        # 4) MISS → enqueue + return COLLECTING
        if await self.cache.acquire_collect_lock(symbol):
            job_id = self.queue.enqueue_collect(symbol, priority="high")
            await self.repo.set_status(symbol, Status.COLLECTING, job_id=job_id)
            await self.session.commit()
            if not self.queue.enabled:
                # No broker → run inline so dev still works (slower request).
                await self.run_collect(symbol, company_name=company_name)
                rows = await self.repo.list_recent(symbol, limit=page_size)
                status = Status.READY if rows else Status.NO_NEWS_FOUND
                metrics.request_total.labels(status=status, source="postgres").inc()
                return NewsResponse(
                    status=status,
                    source="postgres",
                    stale=False,
                    items=rows,
                    fetched_at=_utcnow(),
                    message=None if rows else "최근 뉴스를 찾지 못했습니다.",
                )

        await self.cache.set_status(symbol, Status.COLLECTING)
        metrics.request_total.labels(status=Status.COLLECTING, source="queue").inc()
        return NewsResponse(
            status=Status.COLLECTING,
            source="queue",
            stale=False,
            items=[],
            fetched_at=None,
            message="뉴스를 수집하고 있습니다.",
        )

    # ─── public: worker path ───────────────────────────────────────────────────

    async def run_collect(
        self, symbol: str, *, company_name: Optional[str] = None, job_id: Optional[str] = None
    ) -> int:
        """Collect from providers, dedup, persist. Returns count of NEW articles."""
        started = _utcnow()
        job_id = job_id or uuid.uuid4().hex
        await self.repo.set_status(symbol, Status.COLLECTING, job_id=job_id)
        await self.session.commit()

        name = company_name or await self._resolve_company_name(symbol) or symbol
        try:
            articles = await fetch_for_symbol(symbol, name, max_articles=30)
        except Exception as e:
            log.exception("collect_fetch_failed", symbol=symbol)
            await self.repo.set_status(symbol, Status.FAILED, error=str(e), job_id=job_id)
            await self.repo.log_ingestion(
                symbol=symbol,
                provider="google_news",
                job_id=job_id,
                started_at=started,
                finished_at=_utcnow(),
                fetched=0,
                deduped=0,
                inserted=0,
                status="error",
                error=str(e),
            )
            await self.session.commit()
            return 0

        fetched = len(articles)
        inserted_ids: list[int] = []
        deduped = 0

        for a in articles:
            h = dedup_mod.title_hash(a.title)
            # Storage uses naive-UTC. Providers occasionally hand back tz-aware
            # datetimes; PostgreSQL with TIMESTAMP WITHOUT TIME ZONE rejects
            # those outright. Drop the tzinfo after converting to UTC.
            pub = a.published_at
            if pub is not None and pub.tzinfo is not None:
                pub = pub.astimezone(timezone.utc).replace(tzinfo=None)
            payload = {
                "symbol": symbol,
                "title": a.title,
                "normalized_title": dedup_mod.normalize_title(a.title),
                "summary": a.summary,
                "source": a.source,
                "url": a.url,
                "published_at": pub,
                "hash": h,
                "status": "raw",
                "related_symbols": [],
            }
            inserted = await self.repo.upsert_article(payload)
            if inserted:
                await self.session.flush()  # populate id
                # Re-fetch to get the assigned id deterministically:
                from sqlalchemy import select
                from news_v2.models import Article

                new_id = (
                    await self.session.execute(
                        select(Article.id).where(
                            Article.symbol == symbol, Article.hash == h
                        )
                    )
                ).scalar_one()
                inserted_ids.append(new_id)
            else:
                deduped += 1

        finished = _utcnow()
        status = Status.NO_NEWS_FOUND if fetched == 0 else Status.READY
        await self.repo.set_status(symbol, status, job_id=job_id)
        await self.repo.set_priority(symbol, last_collected=finished)
        await self.repo.log_ingestion(
            symbol=symbol,
            provider="google_news",
            job_id=job_id,
            started_at=started,
            finished_at=finished,
            fetched=fetched,
            deduped=deduped,
            inserted=len(inserted_ids),
            status="success",
        )
        await self.session.commit()
        metrics.collect_runs.labels(provider="google_news", status="success").inc()

        # Invalidate cache so the next read populates with fresh PG content.
        await self.cache.invalidate(symbol)
        await self.cache.release_collect_lock(symbol)

        # Enqueue analysis for newly inserted articles (or run inline if no queue).
        for aid in inserted_ids:
            if self.queue.enabled:
                self.queue.enqueue_analyze(aid)
            else:
                await self.run_analyze(aid)

        return len(inserted_ids)

    async def run_analyze(self, article_id: int) -> None:
        from sqlalchemy import select

        from news_v2.models import Article

        article = (
            await self.session.execute(select(Article).where(Article.id == article_id))
        ).scalar_one_or_none()
        if article is None:
            return

        result = await self.agent.analyze(
            title=article.title, body=article.summary, symbol=article.symbol
        )
        await self.repo.update_analysis(
            article_id,
            {
                "sentiment": result.sentiment,
                "sentiment_score": result.sentiment_score,
                "impact_level": result.impact_level,
                "market_effect": result.market_effect,
                "related_symbols": result.related_symbols,
                "ai_summary": result.summary,
                "status": "analyzed",
            },
        )
        await self.session.commit()
        await self.cache.invalidate(article.symbol)

    # ─── helpers ───────────────────────────────────────────────────────────────

    def _is_stale(self, last_collected: Optional[datetime]) -> bool:
        """Stale when we haven't collected for longer than cache TTL.

        Note: published_at is the news outlet's publish time — irrelevant for
        freshness of our pipeline. last_collected (from PriorityScore) reflects
        when our worker last ran.
        """
        if last_collected is None:
            return True
        age_s = (_utcnow() - last_collected.replace(tzinfo=None)).total_seconds()
        return age_s > self.cfg.cache_ttl_s

    def _cache_ttl_for(self, _symbol: str) -> int:
        return self.cfg.cache_ttl_s

    async def _resolve_company_name(self, symbol: str) -> Optional[str]:
        """Look up company name from existing Stock table (Prisma)."""
        try:
            from sqlalchemy import text

            row = (
                await self.session.execute(
                    text('SELECT name FROM "Stock" WHERE symbol = :s LIMIT 1'),
                    {"s": symbol},
                )
            ).first()
            return row[0] if row else None
        except Exception:
            return None
