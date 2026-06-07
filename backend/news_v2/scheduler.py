"""
APScheduler bootstrap for news_v2.

Two ways to use:
  1. As a separate process: `python -m news_v2.scheduler`
  2. From inside FastAPI lifespan: `start_scheduler()` at startup, `stop_scheduler()` at shutdown.

When multiple FastAPI replicas are running, only ONE should host the scheduler.
We use a Redis SETNX lease (news:scheduler:leader) to elect the leader; followers
just no-op. If Redis isn't available, the scheduler runs everywhere — fine for
single-instance dev.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from news_v2.cache import NewsCache
from news_v2.config import get_settings
from news_v2.db import get_session_maker
from news_v2.logging_setup import get_logger
from news_v2.repository import NewsRepository
from news_v2.service import NewsService

log = get_logger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None
_LEADER_LOCK_KEY = "news:scheduler:leader"
_LEADER_LEASE_S = 90


class _InlineQueue:
    """Force worker-path analysis to run inside the scheduler background job."""

    enabled = False

    def enqueue_collect(self, symbol: str, priority: str = "default") -> None:
        return None

    def enqueue_refresh(self, symbol: str) -> None:
        return None

    def enqueue_analyze(self, news_id: str) -> None:
        return None


async def _acquire_leader_lease() -> bool:
    cache = NewsCache()
    c = await cache.client()
    if c is None:
        return True
    try:
        return bool(await c.set(_LEADER_LOCK_KEY, "1", nx=True, ex=_LEADER_LEASE_S))
    except Exception:
        return True


async def _refresh_leader_lease() -> None:
    cache = NewsCache()
    c = await cache.client()
    if c is None:
        return
    try:
        await c.set(_LEADER_LOCK_KEY, "1", ex=_LEADER_LEASE_S)
    except Exception:  # pragma: no cover
        pass


async def _enqueue_tier(tier: int) -> None:
    cfg = get_settings()
    if not cfg.enabled:
        return
    maker = get_session_maker()
    async with maker() as session:
        repo = NewsRepository(session)
        symbols = await repo.list_symbols_in_tier(tier, limit=500)

    if not symbols:
        return

    # Lazy import to avoid hard dep on celery at module import.
    try:
        from news_v2.celery_app import celery_app
    except Exception:
        log.warning("scheduler_celery_missing", tier=tier)
        return

    if not cfg.queue_enabled:
        log.info("scheduler_queue_disabled", tier=tier, count=len(symbols))
        return

    queue = "news.collect.high" if tier == 1 else "news.collect.default"
    for symbol in symbols:
        # jitter ±25% so we don't push 500 at the same wall-clock instant.
        jitter = random.uniform(0, 0.25 * cfg.tier1_interval_s)
        celery_app.send_task(
            "news_v2.tasks.collect_news",
            args=[symbol],
            queue=queue,
            countdown=jitter,
        )
    log.info("scheduler_tier_dispatched", tier=tier, count=len(symbols))


async def _resolve_startup_symbols(repo: NewsRepository) -> list[str]:
    cfg = get_settings()
    symbols: list[str] = []
    seen: set[str] = set()
    for tier in (1, 2, 3):
        for symbol in await repo.list_symbols_in_tier(tier, limit=cfg.bootstrap_collect_limit):
            if symbol and symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
            if len(symbols) >= cfg.bootstrap_collect_limit:
                break
        if len(symbols) >= cfg.bootstrap_collect_limit:
            break
    if not symbols:
        symbols = list(cfg.bootstrap_symbols)

    seen.clear()
    deduped: list[str] = []
    for symbol in symbols:
        if symbol and symbol not in seen:
            seen.add(symbol)
            deduped.append(symbol)
        if len(deduped) >= cfg.bootstrap_collect_limit:
            break
    return deduped


async def _startup_collect() -> None:
    """Run actual collection once after backend startup, outside the UI path."""
    cfg = get_settings()
    if not cfg.enabled or not cfg.startup_collect_enabled:
        return

    maker = get_session_maker()
    async with maker() as session:
        repo = NewsRepository(session)
        symbols = await _resolve_startup_symbols(repo)
        if not symbols:
            log.info("startup_collect_no_symbols")
            return

        service = NewsService(session=session, queue=_InlineQueue())
        collected = 0
        for symbol in symbols:
            try:
                collected += await service.run_collect(symbol)
            except Exception as exc:
                log.exception("startup_collect_symbol_failed", symbol=symbol, error=str(exc))
        log.info("startup_collect_done", symbols=len(symbols), inserted=collected)


async def _recompute_priority() -> None:
    try:
        from news_v2.celery_app import celery_app

        celery_app.send_task("news_v2.tasks.recompute_priority", queue="news.maintenance")
    except Exception:  # pragma: no cover
        log.warning("scheduler_priority_dispatch_failed")


async def _prune() -> None:
    try:
        from news_v2.celery_app import celery_app

        celery_app.send_task("news_v2.tasks.prune_old_news", queue="news.maintenance")
    except Exception:  # pragma: no cover
        log.warning("scheduler_prune_dispatch_failed")


async def _guarded_tier1() -> None:
    if not await _acquire_leader_lease():
        return
    await _refresh_leader_lease()
    await _enqueue_tier(1)


async def _guarded_tier2() -> None:
    if not await _acquire_leader_lease():
        return
    await _refresh_leader_lease()
    await _enqueue_tier(2)


async def _guarded_tier3() -> None:
    if not await _acquire_leader_lease():
        return
    await _refresh_leader_lease()
    await _enqueue_tier(3)


async def _guarded_priority() -> None:
    if not await _acquire_leader_lease():
        return
    await _refresh_leader_lease()
    await _recompute_priority()


async def _guarded_prune() -> None:
    if not await _acquire_leader_lease():
        return
    await _refresh_leader_lease()
    await _prune()


async def _guarded_startup_collect() -> None:
    if not await _acquire_leader_lease():
        return
    await _refresh_leader_lease()
    await _startup_collect()


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    cfg = get_settings()
    if not cfg.enabled:
        log.info("scheduler_disabled_via_flag")
        return None  # type: ignore[return-value]

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(_guarded_tier1, "interval", seconds=cfg.tier1_interval_s,
                      id="tier1", max_instances=1, coalesce=True)
    scheduler.add_job(_guarded_tier2, "interval", seconds=cfg.tier2_interval_s,
                      id="tier2", max_instances=1, coalesce=True)
    scheduler.add_job(_guarded_tier3, "interval", seconds=cfg.tier3_interval_s,
                      id="tier3", max_instances=1, coalesce=True)
    scheduler.add_job(_guarded_priority, "interval", minutes=30,
                      id="priority", max_instances=1, coalesce=True)
    scheduler.add_job(_guarded_prune, "cron", hour=3,
                      id="prune", max_instances=1, coalesce=True)
    if cfg.startup_collect_enabled:
        scheduler.add_job(
            _guarded_startup_collect,
            "date",
            run_date=datetime.now(timezone.utc) + timedelta(seconds=cfg.startup_collect_delay_s),
            id="startup_collect",
            max_instances=1,
            coalesce=True,
        )

    scheduler.start()
    _scheduler = scheduler
    log.info("scheduler_started", tier1=cfg.tier1_interval_s, tier2=cfg.tier2_interval_s, tier3=cfg.tier3_interval_s)
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


if __name__ == "__main__":  # pragma: no cover
    async def _main() -> None:
        start_scheduler()
        # Keep the loop alive forever.
        await asyncio.Event().wait()

    asyncio.run(_main())
