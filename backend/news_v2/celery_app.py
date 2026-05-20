"""
Celery app for news_v2.

Run a worker with:
    celery -A news_v2.celery_app.celery_app worker \\
        -Q news.collect.high,news.collect.default,news.analyze,news.maintenance \\
        --concurrency=4

The broker URL must be set via NEWSV2_CELERY_BROKER (or NEWSV2_REDIS_URL).
If neither is set, importing tasks module still works but enqueuing is a no-op
(see Queue façade in service.py).
"""

from __future__ import annotations

from kombu import Queue as KQueue

from news_v2.config import get_settings

_cfg = get_settings()


def _make_app():
    from celery import Celery

    app = Celery(
        "news_v2",
        broker=_cfg.celery_broker or "memory://",
        backend=None,
        include=["news_v2.tasks"],
    )
    app.conf.update(
        task_default_queue="news.collect.default",
        task_queues=(
            KQueue("news.collect.high"),
            KQueue("news.collect.default"),
            KQueue("news.analyze"),
            KQueue("news.maintenance"),
            KQueue("news.dlq"),
        ),
        task_routes={
            "news_v2.tasks.collect_news": {"queue": "news.collect.default"},
            "news_v2.tasks.refresh_stale_news": {"queue": "news.maintenance"},
            "news_v2.tasks.analyze_news": {"queue": "news.analyze"},
            "news_v2.tasks.deduplicate_news": {"queue": "news.maintenance"},
            "news_v2.tasks.update_sentiment": {"queue": "news.analyze"},
            "news_v2.tasks.recompute_priority": {"queue": "news.maintenance"},
            "news_v2.tasks.prune_old_news": {"queue": "news.maintenance"},
        },
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        timezone="UTC",
        enable_utc=True,
    )
    return app


# Always defined; the broker may be a memory:// no-op when not configured.
celery_app = _make_app()
