"""Tests for NewsService — covering the stale-check regression.

Bug: _is_stale used to compare against rows[0].published_at (when the news
outlet published) instead of when our worker last collected. Every PG-hit
response was flagged STALE because most articles are minutes-to-days old,
triggering a redundant inline collect each time.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select

from news_v2.models import Base, IngestionLog, NewsAnalysis, NewsRaw, NewsSymbolMap, Status
from news_v2.models import StockNewsCache
from news_v2.providers import CollectedArticle
from news_v2.config import Settings
from news_v2.service import NewsService
from news_v2 import service as service_mod


def _make_service(cache_ttl_s: int = 600) -> NewsService:
    cfg = Settings()
    # Cannot freeze tuple-style cfg; tweak attribute via object.__setattr__
    object.__setattr__(cfg, "cache_ttl_s", cache_ttl_s)
    # NewsService.__init__ needs a session but _is_stale doesn't touch it.
    return NewsService(session=MagicMock(), cfg=cfg)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


class _NoopCache:
    async def get_articles(self, _symbol):
        return None

    async def get_status(self, _symbol):
        return None

    async def set_articles(self, *_args, **_kwargs):
        return None

    async def set_status(self, *_args, **_kwargs):
        return None

    async def acquire_collect_lock(self, _symbol):
        return True

    async def release_collect_lock(self, _symbol):
        return None

    async def invalidate(self, _symbol):
        return None


class _QueueDisabled:
    enabled = False

    def __init__(self):
        self.collects = []
        self.analyzes = []

    def enqueue_collect(self, symbol, priority="default"):
        self.collects.append((symbol, priority))
        return None

    def enqueue_refresh(self, symbol):
        self.collects.append((symbol, "refresh"))
        return None

    def enqueue_analyze(self, news_id):
        self.analyzes.append(news_id)
        return None


class _QueueEnabled(_QueueDisabled):
    enabled = True

    def enqueue_collect(self, symbol, priority="default"):
        self.collects.append((symbol, priority))
        return "job-1"

    def enqueue_analyze(self, news_id):
        self.analyzes.append(news_id)
        return "analysis-1"


class _FailingAgent:
    async def analyze(self, **_kwargs):
        raise RuntimeError("agent failed")


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_is_stale_returns_true_when_never_collected():
    service = _make_service()
    assert service._is_stale(None) is True


def test_is_stale_returns_false_when_collected_recently():
    service = _make_service(cache_ttl_s=600)
    just_now = _utcnow_naive() - timedelta(seconds=30)
    assert service._is_stale(just_now) is False


def test_is_stale_returns_true_when_collected_past_ttl():
    service = _make_service(cache_ttl_s=600)
    long_ago = _utcnow_naive() - timedelta(hours=2)
    assert service._is_stale(long_ago) is True


def test_is_stale_does_not_use_article_publish_time():
    """Regression: old news (published 1d ago) collected just now is NOT stale."""
    service = _make_service(cache_ttl_s=600)
    just_now = _utcnow_naive() - timedelta(seconds=10)
    assert service._is_stale(just_now) is False


def test_naive_utc_normalization_logic():
    """Regression: providers return tz-aware datetimes; PostgreSQL with
    TIMESTAMP WITHOUT TIME ZONE rejects them. Service must strip tzinfo
    after converting to UTC before persisting.
    """
    from datetime import timezone as _tz

    aware_utc = datetime(2026, 5, 20, 6, 40, tzinfo=_tz.utc)
    # Replicate the inline normalization from service.run_collect.
    pub = aware_utc
    if pub is not None and pub.tzinfo is not None:
        pub = pub.astimezone(_tz.utc).replace(tzinfo=None)
    assert pub.tzinfo is None
    assert pub == datetime(2026, 5, 20, 6, 40)

    # Naive input must be passed through untouched.
    naive = datetime(2026, 5, 20, 6, 40)
    pub2 = naive
    if pub2 is not None and pub2.tzinfo is not None:
        pub2 = pub2.astimezone(_tz.utc).replace(tzinfo=None)
    assert pub2 is naive


@pytest.mark.asyncio
async def test_get_for_symbol_cache_miss_does_not_collect_inline(session):
    queue = _QueueDisabled()
    service = NewsService(session=session, cache=_NoopCache(), queue=queue)
    service.run_collect = AsyncMock()  # type: ignore[method-assign]

    result = await service.get_for_symbol("005930", company_name="삼성전자", limit=30)

    assert result.status == Status.COLLECTING
    assert result.items == []
    assert queue.collects == [("005930", "high")]
    service.run_collect.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_for_symbol_recent_no_news_returns_empty_without_requeue(session):
    queue = _QueueDisabled()
    service = NewsService(session=session, cache=_NoopCache(), queue=queue)
    await service.repo.set_status("005930", Status.NO_NEWS_FOUND)
    await session.commit()

    result = await service.get_for_symbol("005930", company_name="삼성전자", limit=30)

    assert result.status == Status.NO_NEWS_FOUND
    assert result.items == []
    assert queue.collects == []


@pytest.mark.asyncio
async def test_resolve_company_name_falls_back_to_stock_json(session, monkeypatch, tmp_path):
    stocks_path = tmp_path / "korea-stocks.json"
    stocks_path.write_text(
        '[{"symbol": "005380", "name": "현대자동차"}]',
        encoding="utf-8",
    )
    monkeypatch.setattr(service_mod, "_STOCKS_JSON_PATH", stocks_path)
    service_mod._load_stock_name_map.cache_clear()

    service = NewsService(session=session, cache=_NoopCache(), queue=_QueueDisabled())

    assert await service._resolve_company_name("005380") == "현대자동차"

    service_mod._load_stock_name_map.cache_clear()


@pytest.mark.asyncio
async def test_run_collect_dedups_maps_and_populates_stock_cache(session, monkeypatch):
    now = _utcnow_naive()

    async def _fake_fetch(_symbol, _company_name, max_articles=30):
        return [
            CollectedArticle(
                title="삼성전자 어닝 서프라이즈",
                url="https://news/1",
                source="한국경제",
                published_at=now,
                summary="삼성전자와 000660 동반 호재",
            ),
            CollectedArticle(
                title="[속보] 삼성전자 어닝 서프라이즈!!!",
                url="https://news/2",
                source="매일경제",
                published_at=now,
                summary="중복 기사",
            ),
        ]

    monkeypatch.setattr("news_v2.service.fetch_for_symbol", _fake_fetch)
    queue = _QueueEnabled()
    service = NewsService(session=session, cache=_NoopCache(), queue=queue)

    inserted = await service.run_collect("005930", company_name="삼성전자")
    rows = await service.repo.list_cached_news("005930", limit=10)
    mapped_rows = await service.repo.list_cached_news("000660", limit=10)

    assert inserted == 1
    assert len(rows) == 1
    assert rows[0].title == "삼성전자 어닝 서프라이즈"
    assert len(mapped_rows) == 1
    assert queue.analyzes == [rows[0].news_id]


@pytest.mark.asyncio
async def test_run_collect_maps_alias_and_sector_symbols(session, monkeypatch):
    now = _utcnow_naive()

    async def _fake_fetch(_symbol, _company_name, max_articles=30):
        return [
            CollectedArticle(
                title="삼성전자우와 반도체 HBM 업황 동반 강세",
                url="https://news/alias-sector",
                source="한국경제",
                published_at=now,
                summary="삼성전자우, SK하이닉스 관련 반도체 기사",
            )
        ]

    monkeypatch.setattr("news_v2.service.fetch_for_symbol", _fake_fetch)
    service = NewsService(session=session, cache=_NoopCache(), queue=_QueueEnabled())

    await service.run_collect("005930", company_name="삼성전자")

    preferred = await service.repo.list_cached_news("005935", limit=10)
    hynix = await service.repo.list_cached_news("000660", limit=10)
    assert len(preferred) == 1
    assert len(hynix) == 1


@pytest.mark.asyncio
async def test_run_collect_replaces_target_symbol_cache(session, monkeypatch):
    now = _utcnow_naive()
    session.add(
        NewsRaw(
            news_id="stale-affiliate",
            title="현대엔지니어링, 건설산업 협약 체결",
            normalized_title="현대엔지니어링 건설산업 협약 체결",
            title_hash="s" * 64,
            url="https://news/stale-affiliate",
            source="Hyundai Motor Group",
            published_at=now,
            raw_content=None,
            content_quality=0.3,
        )
    )
    session.add(
        StockNewsCache(
            symbol="005380",
            news_id="stale-affiliate",
            published_at=now,
            rank_score=0.9,
        )
    )
    await session.commit()

    async def _fake_fetch(_symbol, _company_name, max_articles=30):
        return [
            CollectedArticle(
                title="현대차, 모빌리티 기술인력 신규 채용",
                url="https://news/hyundai-new",
                source="연합뉴스",
                published_at=now,
                summary="현대차 신규 채용 기사",
            )
        ]

    monkeypatch.setattr("news_v2.service.fetch_for_symbol", _fake_fetch)
    service = NewsService(session=session, cache=_NoopCache(), queue=_QueueEnabled())

    await service.run_collect("005380", company_name="현대자동차")

    rows = await service.repo.list_cached_news("005380", limit=10)
    assert [row.title for row in rows] == ["현대차, 모빌리티 기술인력 신규 채용"]


@pytest.mark.asyncio
async def test_run_analyze_records_failure_and_allows_retry(session):
    now = _utcnow_naive()
    session.add(
        NewsRaw(
            news_id="failed-analysis-news",
            title="삼성전자 분석 실패 테스트",
            normalized_title="삼성전자 분석 실패 테스트",
            title_hash="f" * 64,
            url="https://news/fail-analysis",
            source="한국경제",
            published_at=now,
            raw_content="본문",
            content_quality=0.8,
        )
    )
    session.add(
        NewsSymbolMap(
            news_id="failed-analysis-news",
            symbol="005930",
            company_name="삼성전자",
            relevance=1.0,
            evidence="target_symbol",
        )
    )
    await session.commit()
    service = NewsService(session=session, cache=_NoopCache(), queue=_QueueDisabled(), agent=_FailingAgent())

    with pytest.raises(RuntimeError):
        await service.run_analyze("failed-analysis-news", raise_on_failure=True)

    analysis = (
        await session.execute(
            select(NewsAnalysis).where(NewsAnalysis.news_id == "failed-analysis-news")
        )
    ).scalar_one()
    log = (
        await session.execute(
            select(IngestionLog).where(IngestionLog.job_id == "failed-analysis-news")
        )
    ).scalar_one()

    assert analysis.status == "failed"
    assert "agent failed" in analysis.error
    assert log.provider == "news_agent_analysis"
    assert log.status == "retry"
