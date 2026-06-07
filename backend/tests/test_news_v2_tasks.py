"""Tests for news_v2.tasks loop management in Celery workers."""

import asyncio
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from sqlalchemy.pool import NullPool

from news_v2 import db
from news_v2 import tasks


def teardown_function():
    tasks._close_task_loop()
    if db._engine is not None:
        asyncio.run(db.dispose())


async def _capture_loop_id() -> int:
    return id(asyncio.get_running_loop())


def test_run_reuses_same_loop_within_worker_process():
    first_loop_id = tasks._run(_capture_loop_id())
    second_loop_id = tasks._run(_capture_loop_id())

    assert first_loop_id == second_loop_id


def test_close_task_loop_forces_new_loop():
    first_loop = tasks._get_task_loop()

    tasks._close_task_loop()

    second_loop = tasks._get_task_loop()

    assert first_loop.is_closed() is True
    assert first_loop is not second_loop


@dataclass(frozen=True)
class _DummySettings:
    db_url: str


def test_asyncpg_engine_uses_null_pool(monkeypatch):
    monkeypatch.setattr(db, "get_settings", lambda: _DummySettings("postgresql+asyncpg://u:p@localhost/db"))

    engine = db._get_engine()

    assert isinstance(engine.sync_engine.pool, NullPool)
