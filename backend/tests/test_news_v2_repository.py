"""Tests for news_v2.repository — DB CRUD against an in-memory SQLite engine."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
