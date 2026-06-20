"""Tests for news_v2 scheduler startup collection target selection."""

import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from news_v2 import config
from news_v2 import scheduler


@dataclass(frozen=True)
class _DummySettings:
    enabled: bool = True
    collection_enabled: bool = True
    queue_enabled: bool = True
    startup_collect_enabled: bool = True
    worker_autostart_enabled: bool = True
    worker_concurrency: int = 2
    worker_lock_path: str = "/tmp/simons_news_v2_worker_test.lock"
    worker_queues: list[str] = None  # type: ignore[assignment]
    bootstrap_symbols: list[str] = None  # type: ignore[assignment]
    bootstrap_collect_limit: int = 3

    def __post_init__(self):
        if self.worker_queues is None:
            object.__setattr__(self, "worker_queues", ["news.collect.high", "news.analyze"])
        if self.bootstrap_symbols is None:
            object.__setattr__(self, "bootstrap_symbols", ["005930", "000660", "005930", "035420"])


class _Repo:
    def __init__(self, tiers):
        self.tiers = tiers

    async def list_symbols_in_tier(self, tier: int, limit: int = 500):
        return list(self.tiers.get(tier, []))[:limit]

    async def list_symbols_in_queue(self, queue: str, limit: int = 500):
        return list(self.tiers.get(queue, []))[:limit]


class _AsyncSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_startup_symbols_fall_back_to_bootstrap_list(monkeypatch):
    monkeypatch.setattr(scheduler, "get_settings", lambda: _DummySettings())

    symbols = await scheduler._resolve_startup_symbols(_Repo({}))

    assert symbols == ["005930", "000660", "035420"]


@pytest.mark.asyncio
async def test_startup_symbols_prefer_priority_tiers(monkeypatch):
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: _DummySettings(bootstrap_symbols=["005930"], bootstrap_collect_limit=4),
    )

    symbols = await scheduler._resolve_startup_symbols(
        _Repo({1: ["HIGH", "MED"], 2: ["LOW", "HIGH"], 3: ["TAIL"]})
    )

    assert symbols == ["HIGH", "MED", "LOW", "TAIL"]


def test_env_list_parses_comma_separated_values(monkeypatch):
    monkeypatch.setenv("NEWSV2_BOOTSTRAP_SYMBOLS", "005930, 000660,,035420 ")

    assert config.Settings().bootstrap_symbols == ["005930", "000660", "035420"]


def test_collection_disabled_keeps_cache_but_disables_queue(monkeypatch):
    monkeypatch.setenv("NEWSV2_COLLECTION_ENABLED", "false")
    monkeypatch.setenv("NEWSV2_REDIS_URL", "redis://redis:6379/1")
    monkeypatch.setenv("NEWSV2_CELERY_BROKER", "redis://redis:6379/2")

    cfg = config.Settings()

    assert cfg.cache_enabled is True
    assert cfg.queue_enabled is False


def test_collection_queue_names_are_separated():
    assert scheduler._queue_name("hot") == "news.collect.high"
    assert scheduler._queue_name("warm") == "news.collect.default"
    assert scheduler._queue_name("cold") == "news.collect.cold"


def test_worker_command_uses_configured_queues_and_concurrency():
    cfg = _DummySettings(worker_queues=["news.collect.high", "news.analyze"], worker_concurrency=3)

    command = scheduler._worker_command(cfg)

    assert command[:4] == [sys.executable, "-m", "celery", "-A"]
    assert "news_v2.celery_app.celery_app" in command
    assert command[command.index("-Q") + 1] == "news.collect.high,news.analyze"
    assert command[command.index("--concurrency") + 1] == "3"


def test_worker_env_adds_backend_to_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "existing")

    env = scheduler._worker_env()

    assert env["PYTHONPATH"].split(os.pathsep)[0].endswith("/backend")
    assert env["PYTHONPATH"].split(os.pathsep)[1] == "existing"


def test_worker_lock_prevents_duplicate_autostart(tmp_path):
    cfg = _DummySettings(worker_lock_path=str(tmp_path / "worker.lock"))

    assert scheduler._acquire_worker_lock(cfg) is True
    assert scheduler._acquire_worker_lock(cfg) is False

    scheduler._release_worker_lock(cfg)

    assert scheduler._acquire_worker_lock(cfg) is True
    scheduler._release_worker_lock(cfg)


def test_worker_autostart_skips_when_broker_worker_exists(monkeypatch, tmp_path):
    cfg = _DummySettings(worker_lock_path=str(tmp_path / "worker.lock"))
    monkeypatch.setattr(scheduler, "get_settings", lambda: cfg)
    monkeypatch.setattr(scheduler, "_broker_worker_claims_queue", lambda settings: True)
    monkeypatch.setattr(scheduler.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Popen called"))
    scheduler._worker_process = None

    scheduler._start_worker_process()

    assert not os.path.exists(cfg.worker_lock_path)


@pytest.mark.asyncio
async def test_pending_collect_runs_inline_when_worker_missing(monkeypatch):
    collected = []

    class _PendingRepo:
        def __init__(self, _session):
            pass

        async def list_collecting_symbols(self, *, older_than, limit=20):
            return ["011790"]

    class _PendingService:
        def __init__(self, *, session, queue):
            pass

        async def run_collect(self, symbol):
            collected.append(symbol)
            return 1

    monkeypatch.setattr(scheduler, "get_settings", lambda: _DummySettings())
    monkeypatch.setattr(scheduler, "_collection_worker_available", lambda _cfg: False)
    monkeypatch.setattr(scheduler, "get_session_maker", lambda: lambda: _AsyncSessionContext())
    monkeypatch.setattr(scheduler, "NewsRepository", _PendingRepo)
    monkeypatch.setattr(scheduler, "NewsService", _PendingService)

    await scheduler._collect_pending_inline()

    assert collected == ["011790"]


@pytest.mark.asyncio
async def test_maintenance_tasks_skip_celery_when_collection_disabled(monkeypatch):
    send_task = Mock()
    celery_module = SimpleNamespace(celery_app=SimpleNamespace(send_task=send_task))
    monkeypatch.setattr(
        scheduler,
        "get_settings",
        lambda: _DummySettings(collection_enabled=False, queue_enabled=False),
    )
    monkeypatch.setitem(sys.modules, "news_v2.celery_app", celery_module)

    await scheduler._recompute_priority()
    await scheduler._prune()

    send_task.assert_not_called()
