"""
Celery tasks for news_v2.

Every task runs an async session, instantiates NewsService, performs the unit
of work, and persists. Retries use exponential backoff. After max_retries the
task lands in `news.dlq` (declared in celery_app) and we mark the symbol FAILED.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from news_v2.celery_app import celery_app
from news_v2.config import get_settings
from news_v2.db import get_session_maker
from news_v2.logging_setup import get_logger
from news_v2.models import Status
from news_v2.priority import PriorityFeatures, assign_tier, compute_score, recompute_cohort
from news_v2.repository import NewsRepository
from news_v2.service import NewsService

log = get_logger(__name__)


def _reset_engine() -> None:
    """Drop the cached async engine so the next task builds a fresh one bound
    to its own event loop. Each Celery task call creates a new asyncio loop
    via asyncio.run(); reusing an engine from a closed loop produces
    'attached to a different loop' RuntimeErrors deep inside asyncpg.
    """
    from news_v2 import db

    if db._engine is not None:
        try:
            db._engine.sync_engine.dispose()
        except Exception:  # pragma: no cover
            pass
    db._engine = None
    db._session_maker = None


def _run(coro):
    """Run an async coroutine from a sync Celery task. Coroutine bodies only
    execute on await, so resetting the engine before asyncio.run() ensures
    that the body's first get_session_maker() call builds a fresh engine on
    the new loop.
    """
    _reset_engine()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, loop).result()
    except RuntimeError:
        pass
    return asyncio.run(coro)


# ─── collect ───────────────────────────────────────────────────────────────────


@celery_app.task(
    name="news_v2.tasks.collect_news",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def collect_news(self, symbol: str, company_name: Optional[str] = None) -> dict:
    async def _do():
        maker = get_session_maker()
        async with maker() as session:
            service = NewsService(session)
            inserted = await service.run_collect(
                symbol, company_name=company_name, job_id=self.request.id
            )
            return {"symbol": symbol, "inserted": inserted}

    try:
        return _run(_do())
    except Exception as exc:
        log.exception("collect_news_failed", symbol=symbol, retries=self.request.retries)
        if self.request.retries >= self.max_retries:
            _run(_mark_failed(symbol, str(exc)))
        raise


@celery_app.task(name="news_v2.tasks.refresh_stale_news")
def refresh_stale_news(symbol: str) -> dict:
    return collect_news.apply(args=[symbol]).result  # type: ignore[no-any-return]


# ─── analyze ───────────────────────────────────────────────────────────────────


@celery_app.task(
    name="news_v2.tasks.analyze_news",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def analyze_news(self, article_id: int) -> dict:
    async def _do():
        maker = get_session_maker()
        async with maker() as session:
            service = NewsService(session)
            await service.run_analyze(article_id)
            return {"article_id": article_id}

    return _run(_do())


@celery_app.task(name="news_v2.tasks.update_sentiment")
def update_sentiment(article_id: int) -> dict:
    """Re-run AI analysis on an existing article. Same impl as analyze_news for now."""
    return analyze_news.apply(args=[article_id]).result  # type: ignore[no-any-return]


# ─── dedup maintenance ─────────────────────────────────────────────────────────


@celery_app.task(name="news_v2.tasks.deduplicate_news")
def deduplicate_news(symbol: Optional[str] = None) -> dict:
    """Embedding-based dedup pass — placeholder for the slow path.

    For now we just count exact-hash duplicates that snuck in. Real embedding
    cosine dedup would require embeddings populated by an analyzer, which we
    leave behind a feature flag.
    """
    async def _do():
        maker = get_session_maker()
        async with maker() as session:
            from sqlalchemy import func, select

            from news_v2.models import Article

            q = select(Article.hash, func.count(Article.id)).group_by(Article.hash)
            if symbol:
                q = q.where(Article.symbol == symbol)
            rows = (await session.execute(q)).all()
            dupes = sum(c - 1 for _, c in rows if c > 1)
            return {"symbol": symbol, "duplicate_rows": dupes}

    return _run(_do())


# ─── priority + cleanup ────────────────────────────────────────────────────────


@celery_app.task(name="news_v2.tasks.recompute_priority")
def recompute_priority() -> dict:
    async def _do():
        cfg = get_settings()
        maker = get_session_maker()
        async with maker() as session:
            repo = NewsRepository(session)
            rows = await repo.list_all_priorities()
            features = [
                PriorityFeatures(
                    symbol=r.symbol,
                    turnover=r.turnover or 0.0,
                    volatility=r.volatility or 0.0,
                    view_count_24h=r.view_count_24h or 0,
                    watchlist_count=r.watchlist_count or 0,
                    search_count_24h=r.search_count_24h or 0,
                    ai_importance=r.ai_importance or 0.0,
                )
                for r in rows
            ]
            cohort = recompute_cohort(features)
            for f, r in zip(features, rows):
                r.score = compute_score(f, cohort, cfg.priority_weights)
                r.tier = assign_tier(r.score, cfg)
            await session.commit()
            return {"updated": len(rows)}

    return _run(_do())


@celery_app.task(name="news_v2.tasks.prune_old_news")
def prune_old_news(days: int = 90) -> dict:
    async def _do():
        maker = get_session_maker()
        async with maker() as session:
            repo = NewsRepository(session)
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
            removed = await repo.delete_older_than(cutoff)
            await session.commit()
            return {"removed": removed}

    return _run(_do())


# ─── private helpers ───────────────────────────────────────────────────────────


async def _mark_failed(symbol: str, error: str) -> None:
    maker = get_session_maker()
    async with maker() as session:
        repo = NewsRepository(session)
        await repo.set_status(symbol, Status.FAILED, error=error)
        await session.commit()
