"""
Celery tasks for news_v2.

Every task runs an async session, instantiates NewsService, performs the unit
of work, and persists. Retries use exponential backoff. After max_retries the
task lands in `news.dlq` (declared in celery_app) and we mark the symbol FAILED.
"""

from __future__ import annotations

import atexit
import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from news_v2.celery_app import celery_app
from news_v2.config import get_settings
from news_v2.db import get_session_maker
from news_v2.logging_setup import get_logger
from news_v2.models import Status
from news_v2.priority import PriorityFeatures, decide_priority, recompute_cohort
from news_v2.repository import NewsRepository
from news_v2.service import NewsService

log = get_logger(__name__)
_task_loop: Optional[asyncio.AbstractEventLoop] = None
_task_loop_pid: Optional[int] = None


def _close_task_loop() -> None:
    global _task_loop, _task_loop_pid
    if _task_loop is not None and not _task_loop.is_closed():
        _task_loop.close()
    _task_loop = None
    _task_loop_pid = None


def _get_task_loop() -> asyncio.AbstractEventLoop:
    global _task_loop, _task_loop_pid
    current_pid = os.getpid()
    if (
        _task_loop is None
        or _task_loop.is_closed()
        or _task_loop_pid != current_pid
    ):
        _close_task_loop()
        _task_loop = asyncio.new_event_loop()
        _task_loop_pid = current_pid
    return _task_loop


atexit.register(_close_task_loop)


def _run(coro):
    """Run task coroutines on one persistent loop per worker process.

    Reusing the same loop keeps asyncpg connections bound to a live event loop
    across task invocations, so we don't need to tear down the SQLAlchemy async
    engine between every Celery task.
    """
    loop = _get_task_loop()
    return loop.run_until_complete(coro)


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
def analyze_news(self, news_id: str) -> dict:
    async def _do():
        maker = get_session_maker()
        async with maker() as session:
            service = NewsService(session)
            await service.run_analyze(news_id, raise_on_failure=True)
            return {"news_id": news_id}

    return _run(_do())


@celery_app.task(name="news_v2.tasks.update_sentiment")
def update_sentiment(news_id: str) -> dict:
    """Re-run AI analysis on an existing article. Same impl as analyze_news for now."""
    return analyze_news.apply(args=[news_id]).result  # type: ignore[no-any-return]


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
        maker = get_session_maker()
        async with maker() as session:
            cfg = get_settings()
            repo = NewsRepository(session)
            for event, sync in [
                ("priority_stock_universe_sync_skipped", repo.ensure_stock_universe_priority_rows),
                ("priority_watchlist_sync_skipped", repo.sync_watchlist_counts_from_db),
                ("priority_search_sync_skipped", repo.sync_search_counts_from_db),
                ("priority_holding_sync_skipped", repo.sync_holding_counts_from_virtual_positions),
            ]:
                try:
                    await sync()
                    await session.commit()
                except Exception as exc:
                    await session.rollback()
                    log.warning(event, error=str(exc))
            rows = await repo.list_all_priorities()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            counts_1h = await repo.news_counts_by_symbol(since=now - timedelta(hours=1))
            counts_24h = await repo.news_counts_by_symbol(since=now - timedelta(hours=24))
            features = [
                PriorityFeatures(
                    symbol=r.symbol,
                    turnover=r.turnover or 0.0,
                    volatility=r.volatility or 0.0,
                    view_count_24h=r.view_count_24h or 0,
                    watchlist_count=r.watchlist_count or 0,
                    holding_count=r.holding_count or 0,
                    search_count_24h=r.search_count_24h or 0,
                    trading_value=r.trading_value or 0.0,
                    market_cap=r.market_cap or 0.0,
                    news_count_1h=counts_1h.get(r.symbol, 0),
                    news_count_24h=counts_24h.get(r.symbol, 0),
                    news_velocity=r.news_velocity or 0.0,
                    index_member=r.index_member or 0,
                    ai_importance=r.ai_importance or 0.0,
                    last_viewed=r.last_viewed,
                    current_view_until=r.current_view_until,
                )
                for r in rows
            ]
            cohort = recompute_cohort(features)
            for f, r in zip(features, rows):
                decision = decide_priority(f, cohort, cfg)
                r.score = decision.score
                r.tier = decision.tier
                r.queue = decision.queue
                r.reason = decision.reason
                r.is_trending = decision.is_trending
                r.news_count_1h = f.news_count_1h
                r.news_count_24h = f.news_count_24h
                r.news_velocity = decision.news_velocity
                await repo.upsert_collection_queue(
                    symbol=r.symbol,
                    queue=decision.queue,
                    score=decision.score,
                    reason=decision.reason,
                    is_trending=decision.is_trending,
                )
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
