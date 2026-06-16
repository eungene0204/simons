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

from news_v2.config import _app_db_url, get_settings

_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None
_app_engine: Optional[AsyncEngine] = None
_app_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def _build_engine(db_url: str) -> AsyncEngine:
    is_sqlite = db_url.startswith("sqlite")
    connect_args = {"timeout": 30} if is_sqlite else {}
    pool_kwargs = {} if is_sqlite else {"poolclass": NullPool}
    engine = create_async_engine(
        db_url,
        future=True,
        pool_pre_ping=True,
        echo=False,
        connect_args=connect_args,
        **pool_kwargs,
    )
    if is_sqlite:
        # WAL mode + 30s busy timeout — SQLite is shared with Next.js (Prisma)
        # so write contention is expected; wait instead of failing.
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):  # type: ignore[no-untyped-def]
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA busy_timeout = 30000")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.close()
    return engine


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = _build_engine(get_settings().db_url)
    return _engine


def _get_app_engine() -> AsyncEngine:
    global _app_engine
    if _app_engine is None:
        _app_engine = _build_engine(_app_db_url())
    return _app_engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = async_sessionmaker(
            _get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_maker


def get_app_session_maker() -> async_sessionmaker[AsyncSession]:
    """앱(Prisma) DB 세션 메이커 — priority sync가 watchlist/search/holding/stock을 읽을 때 사용.

    news DB URL과 동일하면(sqlite 단일 파일 dev 모드) news 세션 메이커를 그대로 재사용해
    중복 엔진을 만들지 않는다. NEWSV2_DB_URL이 Postgres로 갈린 경우에만 별도 sqlite 엔진을 연다.
    """
    global _app_session_maker
    if _app_db_url() == get_settings().db_url:
        return get_session_maker()
    if _app_session_maker is None:
        _app_session_maker = async_sessionmaker(
            _get_app_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _app_session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields one session per request, commits or rolls back."""
    maker = get_session_maker()
    async with maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """news_v2 테이블을 없으면 생성한다(idempotent).

    news_v2엔 alembic이 없고 create_all이 스키마의 단일 소스다(테스트도 동일).
    fresh postgres/sqlite 배포에서 startup 시 호출해 'relation does not exist'를 막는다.
    """
    from news_v2.models import Base

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose() -> None:
    global _engine, _session_maker, _app_engine, _app_session_maker
    if _engine is not None:
        await _engine.dispose()
    if _app_engine is not None:
        await _app_engine.dispose()
    _engine = None
    _session_maker = None
    _app_engine = None
    _app_session_maker = None
