"""
Async SQLAlchemy session factory for news_v2.

Dev: sqlite+aiosqlite (default — same file Prisma uses).
Prod: postgresql+asyncpg.

The session factory is created lazily so importing this module doesn't try
to open a connection during test collection.
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from news_v2.config import get_settings

_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        cfg = get_settings()
        is_sqlite = cfg.db_url.startswith("sqlite")
        connect_args = {"timeout": 30} if is_sqlite else {}
        pool_kwargs = {} if is_sqlite else {"poolclass": NullPool}
        _engine = create_async_engine(
            cfg.db_url,
            future=True,
            pool_pre_ping=True,
            echo=False,
            connect_args=connect_args,
            **pool_kwargs,
        )
        if is_sqlite:
            # WAL mode + 30s busy timeout — SQLite is shared with Next.js (Prisma)
            # so write contention is expected; wait instead of failing.
            sync_engine = _engine.sync_engine

            @event.listens_for(sync_engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _):  # type: ignore[no-untyped-def]
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA busy_timeout = 30000")
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
                cursor.close()
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            _get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields one session per request, commits or rolls back."""
    maker = get_session_maker()
    async with maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose() -> None:
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None
