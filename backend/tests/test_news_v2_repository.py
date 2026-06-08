"""Tests for news_v2.repository — DB CRUD against an in-memory SQLite engine."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import text

from news_v2.models import Base, NewsAnalysis, NewsRaw, StockNewsCache, Status
from news_v2.repository import NewsRepository


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_upsert_article_dedups_by_hash(session):
    repo = NewsRepository(session)
    base = {
        "symbol": "005930",
        "title": "삼성전자 어닝 서프라이즈",
        "normalized_title": "삼성전자 어닝 서프라이즈",
        "summary": None,
        "source": "google_news",
        "url": "https://x/1",
        "published_at": _utcnow(),
        "hash": "h1" * 32,
        "status": "raw",
        "related_symbols": [],
    }
    assert await repo.upsert_article(base) is True
    await session.commit()
    # Same hash → no insert
    assert await repo.upsert_article(base) is False


@pytest.mark.asyncio
async def test_list_recent_orders_by_published_desc(session):
    repo = NewsRepository(session)
    now = _utcnow()
    for i, h in enumerate(["a" * 64, "b" * 64, "c" * 64]):
        await repo.upsert_article(
            {
                "symbol": "005930",
                "title": f"기사 {i}",
                "normalized_title": f"기사 {i}",
                "summary": None,
                "source": "google_news",
                "url": f"https://x/{i}",
                "published_at": now - timedelta(hours=i),
                "hash": h,
                "status": "raw",
                "related_symbols": [],
            }
        )
    await session.commit()
    rows = await repo.list_recent("005930", limit=10)
    assert [r.title for r in rows] == ["기사 0", "기사 1", "기사 2"]


@pytest.mark.asyncio
async def test_bump_priority_creates_and_increments(session):
    repo = NewsRepository(session)
    await repo.bump_priority("005930", delta=50)
    await session.commit()
    row = await repo.get_priority("005930")
    assert row is not None
    assert row.score == 50
    assert row.view_count_24h == 1

    await repo.bump_priority("005930", delta=25)
    await session.commit()
    row = await repo.get_priority("005930")
    assert row.score == 75
    assert row.view_count_24h == 2


@pytest.mark.asyncio
async def test_set_status_transitions(session):
    repo = NewsRepository(session)
    await repo.set_status("005930", Status.COLLECTING, job_id="abc")
    await session.commit()
    row = await repo.get_status("005930")
    assert row.status == Status.COLLECTING
    assert row.in_flight_job_id == "abc"

    await repo.set_status("005930", Status.READY)
    await session.commit()
    row = await repo.get_status("005930")
    assert row.status == Status.READY
    assert row.last_success_at is not None
    assert row.attempt_count == 0
    assert row.in_flight_job_id is None


@pytest.mark.asyncio
async def test_set_status_invalid_raises(session):
    repo = NewsRepository(session)
    with pytest.raises(ValueError):
        await repo.set_status("005930", "BOGUS")


@pytest.mark.asyncio
async def test_list_symbols_in_tier_ordered_by_score(session):
    repo = NewsRepository(session)
    from news_v2.models import PriorityScore

    session.add(PriorityScore(symbol="HIGH", score=900, tier=1))
    session.add(PriorityScore(symbol="MED", score=300, tier=1))
    session.add(PriorityScore(symbol="LOW", score=10, tier=3))
    await session.commit()
    tier1 = await repo.list_symbols_in_tier(1)
    assert tier1 == ["HIGH", "MED"]
    tier3 = await repo.list_symbols_in_tier(3)
    assert tier3 == ["LOW"]


@pytest.mark.asyncio
async def test_record_priority_event_updates_materialized_counters(session):
    repo = NewsRepository(session)

    await repo.record_priority_event(symbol="005930", event_type="current_view", current_view_ttl_s=300)
    await repo.record_priority_event(symbol="005930", event_type="watchlist_add")
    await repo.record_priority_event(symbol="005930", event_type="holding_buy")
    await repo.record_priority_event(symbol="005930", event_type="stock_search")
    await session.commit()

    row = await repo.get_priority("005930")
    assert row is not None
    assert row.view_count_24h == 1
    assert row.watchlist_count == 1
    assert row.holding_count == 1
    assert row.search_count_24h == 1
    assert row.current_view_until is not None


@pytest.mark.asyncio
async def test_collection_queue_monitor_orders_by_score(session):
    repo = NewsRepository(session)

    await repo.upsert_collection_queue(
        symbol="LOW",
        queue="warm",
        score=100,
        reason="trading_value",
        is_trending=False,
    )
    await repo.upsert_collection_queue(
        symbol="HIGH",
        queue="hot",
        score=900,
        reason="current_view",
        is_trending=True,
    )
    await session.commit()

    hot = await repo.list_symbols_in_queue("hot")
    rows = await repo.list_queue_monitor()
    assert hot == ["HIGH"]
    assert [row.symbol for row in rows] == ["HIGH", "LOW"]
    assert rows[0].is_trending is True


@pytest.mark.asyncio
async def test_sync_holding_counts_reads_actual_virtual_positions(session):
    repo = NewsRepository(session)
    await session.execute(
        text(
            'CREATE TABLE "VirtualPosition" ('
            '"id" TEXT PRIMARY KEY, '
            '"accountId" TEXT NOT NULL, '
            '"symbol" TEXT NOT NULL, '
            '"quantity" INTEGER NOT NULL)'
        )
    )
    await session.execute(
        text(
            'INSERT INTO "VirtualPosition" ("id", "accountId", "symbol", "quantity") '
            'VALUES '
            "('p1', 'a1', '005930', 10), "
            "('p2', 'a2', '005930', 3), "
            "('p3', 'a1', '000660', 0)"
        )
    )
    await session.commit()

    synced = await repo.sync_holding_counts_from_virtual_positions()
    await session.commit()

    samsung = await repo.get_priority("005930")
    hynix = await repo.get_priority("000660")
    assert synced == 1
    assert samsung is not None
    assert samsung.holding_count == 2
    assert hynix is None


@pytest.mark.asyncio
async def test_sync_watchlist_search_and_stock_universe_demand(session):
    repo = NewsRepository(session)
    await session.execute(text('CREATE TABLE "Stock" ("symbol" TEXT PRIMARY KEY)'))
    await session.execute(
        text(
            'CREATE TABLE "WatchlistSymbol" ('
            '"id" TEXT PRIMARY KEY, '
            '"symbol" TEXT NOT NULL)'
        )
    )
    await session.execute(
        text(
            'CREATE TABLE "SearchCount" ('
            '"id" INTEGER PRIMARY KEY, '
            '"symbol" TEXT NOT NULL, '
            '"count" INTEGER NOT NULL)'
        )
    )
    await session.execute(text('INSERT INTO "Stock" ("symbol") VALUES (\'005930\'), (\'000660\')'))
    await session.execute(
        text(
            'INSERT INTO "WatchlistSymbol" ("id", "symbol") '
            "VALUES ('w1', '005930'), ('w2', '000660')"
        )
    )
    await session.execute(
        text(
            'INSERT INTO "SearchCount" ("id", "symbol", "count") '
            "VALUES (1, '005930', 7)"
        )
    )
    await session.commit()

    created = await repo.ensure_stock_universe_priority_rows()
    watched = await repo.sync_watchlist_counts_from_db()
    searched = await repo.sync_search_counts_from_db()
    await session.commit()

    samsung = await repo.get_priority("005930")
    hynix = await repo.get_priority("000660")
    assert created == 2
    assert watched == 2
    assert searched == 1
    assert samsung is not None
    assert samsung.watchlist_count == 1
    assert samsung.search_count_24h == 7
    assert hynix is not None
    assert hynix.watchlist_count == 1
    assert hynix.search_count_24h == 0


@pytest.mark.asyncio
async def test_delete_older_than(session):
    repo = NewsRepository(session)
    now = _utcnow()
    await repo.upsert_article(
        {
            "symbol": "005930",
            "title": "old",
            "normalized_title": "old",
            "summary": None,
            "source": "x",
            "url": "u1",
            "published_at": now - timedelta(days=200),
            "hash": "o" * 64,
            "status": "raw",
            "related_symbols": [],
        }
    )
    await repo.upsert_article(
        {
            "symbol": "005930",
            "title": "new",
            "normalized_title": "new",
            "summary": None,
            "source": "x",
            "url": "u2",
            "published_at": now,
            "hash": "n" * 64,
            "status": "raw",
            "related_symbols": [],
        }
    )
    await session.commit()
    removed = await repo.delete_older_than(now - timedelta(days=90))
    await session.commit()
    assert removed == 1
    rows = await repo.list_recent("005930")
    assert [r.title for r in rows] == ["new"]


@pytest.mark.asyncio
async def test_upsert_raw_news_dedups_by_url_and_title_hash(session):
    repo = NewsRepository(session)
    now = _utcnow()
    payload = {
        "title": "삼성전자 어닝 서프라이즈",
        "normalized_title": "삼성전자 어닝 서프라이즈",
        "title_hash": "a" * 64,
        "url": "https://news/1",
        "source": "한국경제",
        "published_at": now,
        "raw_content": "본문",
        "content_quality": 0.8,
    }

    news_id, inserted = await repo.upsert_raw_news(payload)
    assert inserted is True

    same_url_id, inserted = await repo.upsert_raw_news({**payload, "title_hash": "b" * 64})
    same_title_id, inserted_title = await repo.upsert_raw_news({**payload, "url": "https://news/2"})

    assert same_url_id == news_id
    assert same_title_id == news_id
    assert inserted is False
    assert inserted_title is False


@pytest.mark.asyncio
async def test_list_cached_news_reads_final_cache_projection(session):
    repo = NewsRepository(session)
    now = _utcnow()
    session.add_all(
        [
            NewsRaw(
                news_id="n1",
                title="old",
                normalized_title="old",
                title_hash="o" * 64,
                url="https://news/old",
                source="연합뉴스",
                published_at=now - timedelta(hours=1),
                raw_content="old body",
                content_quality=0.2,
            ),
            NewsRaw(
                news_id="n2",
                title="new",
                normalized_title="new",
                title_hash="n" * 64,
                url="https://news/new",
                source="연합뉴스",
                published_at=now,
                raw_content="new body",
                content_quality=0.9,
            ),
            NewsAnalysis(
                news_id="n2",
                sentiment="positive",
                impact_score=0.72,
                importance="high",
                summary="요약",
                related_symbols=["000660"],
            ),
            StockNewsCache(symbol="005930", news_id="n1", published_at=now - timedelta(hours=1), rank_score=0.1),
            StockNewsCache(symbol="005930", news_id="n2", published_at=now, rank_score=0.9),
        ]
    )
    await session.commit()

    rows = await repo.list_cached_news("005930", limit=10)

    assert [r.news_id for r in rows] == ["n2", "n1"]
    assert rows[0].summary == "요약"
    assert rows[0].sentiment == "positive"
    assert rows[0].impact_score == 0.72
    assert rows[0].importance == "high"
    assert rows[1].sentiment == "neutral"
    assert rows[1].importance == "low"
