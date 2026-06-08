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
import os
import random
import subprocess
import sys
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
_worker_process: Optional[subprocess.Popen] = None
_LEADER_LOCK_KEY = "news:scheduler:leader"
_LEADER_LEASE_S = 90
_PENDING_COLLECT_AGE_S = 5
_PENDING_COLLECT_INTERVAL_S = 10
_PENDING_COLLECT_LIMIT = 10


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


def _queue_name(queue: str) -> str:
    if queue == "hot":
        return "news.collect.high"
    if queue == "cold":
        return "news.collect.cold"
    return "news.collect.default"


def _worker_command(cfg) -> list[str]:
    queues = ",".join(getattr(cfg, "worker_queues", []))
    return [
        sys.executable,
        "-m",
        "celery",
        "-A",
        "news_v2.celery_app.celery_app",
        "worker",
        "-Q",
        queues,
        "--concurrency",
        str(getattr(cfg, "worker_concurrency", 2)),
        "--loglevel",
        "INFO",
    ]


def _worker_env() -> dict[str, str]:
    env = os.environ.copy()
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = backend_dir if not existing else f"{backend_dir}{os.pathsep}{existing}"
    return env


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_worker_lock(path: str) -> Optional[int]:
    try:
        with open(path, "r", encoding="utf-8") as lock_file:
            raw = lock_file.read().strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def _write_worker_lock(cfg, pid: int) -> None:
    path = getattr(cfg, "worker_lock_path", "/tmp/simons_news_v2_worker.lock")
    with open(path, "w", encoding="utf-8") as lock_file:
        lock_file.write(str(pid))


def _acquire_worker_lock(cfg) -> bool:
    path = getattr(cfg, "worker_lock_path", "/tmp/simons_news_v2_worker.lock")
    lock_dir = os.path.dirname(path)
    if lock_dir:
        os.makedirs(lock_dir, exist_ok=True)

    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            existing_pid = _read_worker_lock(path)
            if existing_pid is not None and _pid_is_running(existing_pid):
                log.info("worker_autostart_skipped_lock_held", pid=existing_pid, path=path)
                return False
            try:
                os.unlink(path)
                log.info("worker_stale_lock_removed", path=path, pid=existing_pid)
            except FileNotFoundError:
                continue
            except OSError as exc:
                log.warning("worker_stale_lock_remove_failed", path=path, error=str(exc))
                return False
        except OSError as exc:
            log.warning("worker_lock_acquire_failed", path=path, error=str(exc))
            return False
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
                lock_file.write(str(os.getpid()))
            return True


def _release_worker_lock(cfg) -> None:
    path = getattr(cfg, "worker_lock_path", "/tmp/simons_news_v2_worker.lock")
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        log.warning("worker_lock_release_failed", path=path, error=str(exc))


def _broker_worker_claims_queue(cfg) -> bool:
    target_queues = set(getattr(cfg, "worker_queues", []))
    if not target_queues:
        return False

    try:
        from news_v2.celery_app import celery_app

        active_queues = celery_app.control.inspect(timeout=1.0).active_queues() or {}
    except Exception as exc:
        log.warning("worker_inspect_failed", error=str(exc))
        return False

    for worker_name, queues in active_queues.items():
        queue_names = {queue.get("name") for queue in queues if isinstance(queue, dict)}
        claimed = target_queues.intersection(name for name in queue_names if name)
        if claimed:
            log.info(
                "worker_autostart_skipped_existing_worker",
                worker=worker_name,
                queues=sorted(claimed),
            )
            return True
    return False


def _local_worker_is_running() -> bool:
    return _worker_process is not None and _worker_process.poll() is None


def _collection_worker_available(cfg) -> bool:
    return _local_worker_is_running() or _broker_worker_claims_queue(cfg)


def _start_worker_process() -> None:
    global _worker_process
    cfg = get_settings()
    if not cfg.enabled or not cfg.queue_enabled:
        return
    if not getattr(cfg, "worker_autostart_enabled", True):
        log.info("worker_autostart_disabled")
        return
    if _worker_process is not None and _worker_process.poll() is None:
        return

    if not _acquire_worker_lock(cfg):
        return

    if _broker_worker_claims_queue(cfg):
        _release_worker_lock(cfg)
        return

    try:
        _worker_process = subprocess.Popen(
            _worker_command(cfg),
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            env=_worker_env(),
        )
        _write_worker_lock(cfg, _worker_process.pid)
        log.info("worker_autostarted", pid=_worker_process.pid)
    except Exception as exc:  # pragma: no cover
        _release_worker_lock(cfg)
        log.warning("worker_autostart_failed", error=str(exc))


def _stop_worker_process() -> None:
    global _worker_process
    if _worker_process is None:
        return
    if _worker_process.poll() is None:
        _worker_process.terminate()
        try:
            _worker_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _worker_process.kill()
            _worker_process.wait(timeout=5)
    cfg = get_settings()
    _release_worker_lock(cfg)
    log.info("worker_stopped")
    _worker_process = None


async def _enqueue_collection_queue(queue_label: str, limit: int = 500) -> None:
    cfg = get_settings()
    if not cfg.enabled:
        return
    maker = get_session_maker()
    async with maker() as session:
        repo = NewsRepository(session)
        symbols = await repo.list_symbols_in_queue(queue_label, limit=limit)

    if not symbols:
        return

    # Lazy import to avoid hard dep on celery at module import.
    try:
        from news_v2.celery_app import celery_app
    except Exception:
        log.warning("scheduler_celery_missing", queue=queue_label)
        return

    if not cfg.queue_enabled:
        log.info("scheduler_queue_disabled", queue=queue_label, count=len(symbols))
        return

    queue = _queue_name(queue_label)
    interval_s = {
        "hot": cfg.hot_interval_s,
        "warm": cfg.warm_interval_s,
        "cold": cfg.cold_interval_s,
    }.get(queue_label, cfg.warm_interval_s)
    for symbol in symbols:
        # jitter ±25% so we don't push 500 at the same wall-clock instant.
        jitter = random.uniform(0, 0.25 * interval_s)
        celery_app.send_task(
            "news_v2.tasks.collect_news",
            args=[symbol],
            queue=queue,
            countdown=jitter,
        )
    log.info("scheduler_queue_dispatched", queue=queue_label, count=len(symbols))


async def _collect_pending_inline() -> None:
    """Fallback for dev/local runs where broker is configured but no worker is alive."""
    cfg = get_settings()
    if not cfg.enabled:
        return
    if _collection_worker_available(cfg):
        return

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=_PENDING_COLLECT_AGE_S)
    maker = get_session_maker()
    async with maker() as session:
        repo = NewsRepository(session)
        symbols = await repo.list_collecting_symbols(
            older_than=cutoff,
            limit=_PENDING_COLLECT_LIMIT,
        )
        if not symbols:
            return

        service = NewsService(session=session, queue=_InlineQueue())
        collected = 0
        for symbol in symbols:
            try:
                collected += await service.run_collect(symbol)
            except Exception as exc:
                log.exception("pending_collect_symbol_failed", symbol=symbol, error=str(exc))
        log.info("pending_collect_done", symbols=len(symbols), inserted=collected)


async def _enqueue_tier(tier: int) -> None:
    await _enqueue_collection_queue({1: "hot", 2: "warm", 3: "cold"}.get(tier, "cold"))


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


async def _guarded_pending_collect() -> None:
    if not await _acquire_leader_lease():
        return
    await _refresh_leader_lease()
    await _collect_pending_inline()


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    cfg = get_settings()
    if not cfg.enabled:
        log.info("scheduler_disabled_via_flag")
        return None  # type: ignore[return-value]

    _start_worker_process()

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(_guarded_tier1, "interval", seconds=cfg.hot_interval_s,
                      id="hot_queue", max_instances=1, coalesce=True)
    scheduler.add_job(_guarded_tier2, "interval", seconds=cfg.warm_interval_s,
                      id="warm_queue", max_instances=1, coalesce=True)
    scheduler.add_job(_guarded_tier3, "interval", seconds=cfg.cold_interval_s,
                      id="cold_queue", max_instances=1, coalesce=True)
    scheduler.add_job(_guarded_priority, "interval", seconds=cfg.priority_recompute_interval_s,
                      id="priority", max_instances=1, coalesce=True)
    scheduler.add_job(_guarded_pending_collect, "interval", seconds=_PENDING_COLLECT_INTERVAL_S,
                      id="pending_collect", max_instances=1, coalesce=True)
    scheduler.add_job(
        _guarded_priority,
        "date",
        run_date=datetime.now(timezone.utc) + timedelta(seconds=1),
        id="priority_bootstrap",
        max_instances=1,
        coalesce=True,
    )
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
    worker_pid = _worker_process.pid if _worker_process is not None and _worker_process.poll() is None else None
    log.info(
        "scheduler_started",
        hot=cfg.hot_interval_s,
        warm=cfg.warm_interval_s,
        cold=cfg.cold_interval_s,
        worker_pid=worker_pid,
    )
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    _stop_worker_process()


if __name__ == "__main__":  # pragma: no cover
    async def _main() -> None:
        start_scheduler()
        # Keep the loop alive forever.
        await asyncio.Event().wait()

    asyncio.run(_main())
