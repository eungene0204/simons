"""
NewsService — the public surface used by FastAPI handlers and Celery tasks.

Hot path (tab view):
    get_for_symbol(symbol) → Redis → PG → COLLECTING (enqueue background job)

Collect path (worker):
    run_collect(symbol) → providers.fetch → normalize → dedup → persist → analyze

Analysis path (worker):
    run_analyze(news_id) → AINewsAgent → persist analysis fields → update cache
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from news_v2 import dedup as dedup_mod
from news_v2 import observability as metrics
from news_v2.agent import AINewsAgent, build_agent
from news_v2.cache import NewsCache
from news_v2.config import Settings, get_settings
from news_v2.logging_setup import get_logger
from news_v2.models import Status
from news_v2.providers import fetch_for_symbol
from news_v2.repository import CachedNewsDTO, NewsRepository
from news_v2.symbol_mapping import map_symbols_from_text

log = get_logger(__name__)
_STOCKS_JSON_PATH = Path(__file__).resolve().parents[2] / "data" / "korea-stocks.json"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _needs_body_preview_hydration(items: list[CachedNewsDTO]) -> bool:
    return any(item.summary and not item.body_preview for item in items)


@lru_cache(maxsize=1)
def _load_stock_name_map() -> dict[str, str]:
    try:
        with _STOCKS_JSON_PATH.open("r", encoding="utf-8") as f:
            rows = json.load(f)
    except Exception:
        return {}
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("symbol")): str(row.get("name"))
        for row in rows
        if isinstance(row, dict) and row.get("symbol") and row.get("name")
    }


@dataclass
class NewsResponse:
    status: str
    source: str
    stale: bool
    items: list[CachedNewsDTO]
    fetched_at: Optional[datetime]
    message: Optional[str] = None


# ─── Queue abstraction (Celery preferred, in-process fallback) ─────────────────


class Queue:
    """Lightweight queue façade. Uses Celery if available, else logs + no-op.

    The fallback exists so dev environments without a broker can still use the
    rest of the pipeline (cache miss → COLLECTING → user re-checks later).
    """

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self._celery_app = None
        if cfg.queue_enabled:
            try:
                from news_v2.celery_app import celery_app

                self._celery_app = celery_app
            except Exception as e:  # pragma: no cover
                log.warning("celery_unavailable", error=str(e))

    @property
    def enabled(self) -> bool:
        return self._celery_app is not None

    def enqueue_collect(self, symbol: str, priority: str = "default") -> Optional[str]:
        if not self.enabled:
            log.info("queue_disabled_enqueue_skip", task="collect_news", symbol=symbol)
            return None
        queue = "news.collect.high" if priority == "high" else "news.collect.default"
        result = self._celery_app.send_task(
            "news_v2.tasks.collect_news", args=[symbol], queue=queue
        )
        return result.id

    def enqueue_refresh(self, symbol: str) -> Optional[str]:
        if not self.enabled:
            return None
        result = self._celery_app.send_task(
            "news_v2.tasks.refresh_stale_news", args=[symbol], queue="news.maintenance"
        )
        return result.id

    def enqueue_analyze(self, news_id: str) -> Optional[str]:
        if not self.enabled:
            return None
        result = self._celery_app.send_task(
            "news_v2.tasks.analyze_news", args=[news_id], queue="news.analyze"
        )
        return result.id


# ─── Service ───────────────────────────────────────────────────────────────────


class NewsService:
    def __init__(
        self,
        session: AsyncSession,
        cache: Optional[NewsCache] = None,
        queue: Optional[Queue] = None,
        agent: Optional[AINewsAgent] = None,
        cfg: Optional[Settings] = None,
    ) -> None:
        self.cfg = cfg or get_settings()
        self.repo = NewsRepository(session)
        self.cache = cache or NewsCache(self.cfg)
        self.queue = queue or Queue(self.cfg)
        self.agent = agent or build_agent(self.cfg)
        self.session = session

    def _collection_paused_response(
        self, symbol: str, fetched_at: Optional[datetime] = None
    ) -> NewsResponse:
        metrics.request_total.labels(status=Status.NOT_COLLECTED, source="queue").inc()
        return NewsResponse(
            status=Status.NOT_COLLECTED,
            source="queue",
            stale=False,
            items=[],
            fetched_at=fetched_at,
            message="뉴스 수집이 일시 중지되었습니다.",
        )

    # ─── public: read path ─────────────────────────────────────────────────────

    async def get_for_symbol(
        self, symbol: str, company_name: Optional[str] = None, limit: Optional[int] = None
    ) -> NewsResponse:
        page_size = min(limit or self.cfg.default_page_size, self.cfg.max_page_size)

        # 1) Redis HIT. This is a prepared cache store, so it is safe for the tab hot path.
        cached = await self.cache.get_articles(symbol)
        if cached is not None and not _needs_body_preview_hydration(cached):
            metrics.cache_hits.labels(layer="redis").inc()
            status = await self.cache.get_status(symbol) or Status.READY
            stale = status == Status.STALE
            if stale and self.cfg.collection_enabled:
                self.queue.enqueue_refresh(symbol)
            metrics.request_total.labels(status=status, source="redis").inc()
            return NewsResponse(
                status=status,
                source="redis",
                stale=stale,
                items=cached[:page_size],
                fetched_at=_utcnow(),
            )

        # 2) DB cache HIT. Read only the final stock_news_cache projection.
        rows = await self.repo.list_cached_news(symbol, limit=page_size)
        if rows:
            metrics.cache_hits.labels(layer="postgres").inc()
            last_updated = await self.repo.get_cache_last_updated(symbol)
            stale = self._is_stale(last_updated)
            await self.cache.set_articles(
                symbol,
                rows,
                ttl_s=self._cache_ttl_for(symbol),
            )
            status = Status.STALE if stale else Status.READY
            await self.cache.set_status(symbol, status)
            if stale and self.cfg.collection_enabled:
                self.queue.enqueue_refresh(symbol)
            metrics.request_total.labels(status=status, source="postgres").inc()
            return NewsResponse(
                status=status,
                source="postgres",
                stale=stale,
                items=rows,
                fetched_at=last_updated,
            )

        status_row = await self.repo.get_status(symbol)
        if status_row and status_row.status == Status.NO_NEWS_FOUND and not self._is_stale(status_row.last_success_at):
            metrics.request_total.labels(status=Status.NO_NEWS_FOUND, source="queue").inc()
            return NewsResponse(
                status=Status.NO_NEWS_FOUND,
                source="queue",
                stale=False,
                items=[],
                fetched_at=status_row.last_success_at,
                message="최근 뉴스를 찾지 못했습니다.",
            )

        if not self.cfg.collection_enabled:
            await self.repo.set_status(symbol, Status.NOT_COLLECTED)
            await self.session.commit()
            await self.cache.set_status(symbol, Status.NOT_COLLECTED)
            return self._collection_paused_response(
                symbol,
                fetched_at=status_row.last_success_at if status_row else None,
            )

        # 3) MISS → enqueue only. Never collect/analyze inline on the UI request path.
        if await self.cache.acquire_collect_lock(symbol):
            job_id = self.queue.enqueue_collect(symbol, priority="high")
            await self.repo.set_status(symbol, Status.COLLECTING, job_id=job_id)
            await self.session.commit()

        await self.cache.set_status(symbol, Status.COLLECTING)
        metrics.request_total.labels(status=Status.COLLECTING, source="queue").inc()
        return NewsResponse(
            status=Status.COLLECTING,
            source="queue",
            stale=False,
            items=[],
            fetched_at=None,
            message="뉴스를 수집하고 있습니다.",
        )

    # ─── public: worker path ───────────────────────────────────────────────────

    async def run_collect(
        self, symbol: str, *, company_name: Optional[str] = None, job_id: Optional[str] = None
    ) -> int:
        """Collect from providers, dedup, map symbols, and update the tab cache."""
        if not self.cfg.collection_enabled:
            log.info("collection_disabled_skip", symbol=symbol)
            return 0

        started = _utcnow()
        job_id = job_id or uuid.uuid4().hex
        await self.repo.set_status(symbol, Status.COLLECTING, job_id=job_id)
        await self.session.commit()

        name = company_name or await self._resolve_company_name(symbol) or symbol
        try:
            articles = await fetch_for_symbol(symbol, name, max_articles=30)
        except Exception as e:
            log.exception("collect_fetch_failed", symbol=symbol)
            await self.repo.set_status(symbol, Status.FAILED, error=str(e), job_id=job_id)
            await self.repo.log_ingestion(
                symbol=symbol,
                provider="google_news",
                job_id=job_id,
                started_at=started,
                finished_at=_utcnow(),
                fetched=0,
                deduped=0,
                inserted=0,
                status="error",
                error=str(e),
            )
            await self.session.commit()
            return 0

        fetched = len(articles)
        inserted_ids: list[str] = []
        deduped = 0

        if articles:
            await self.repo.delete_stock_news_cache(symbol)

        for a in articles:
            normalized_title = dedup_mod.normalize_title(a.title)
            h = dedup_mod.title_hash(a.title)
            # Storage uses naive-UTC. Providers occasionally hand back tz-aware
            # datetimes; PostgreSQL with TIMESTAMP WITHOUT TIME ZONE rejects
            # those outright. Drop the tzinfo after converting to UTC.
            pub = a.published_at
            if pub is not None and pub.tzinfo is not None:
                pub = pub.astimezone(timezone.utc).replace(tzinfo=None)
            raw_content = a.body or a.summary
            content_quality = _content_quality(a.title, raw_content)
            payload = {
                "title": a.title,
                "normalized_title": normalized_title,
                "title_hash": h,
                "source": a.source,
                "url": a.url,
                "published_at": pub,
                "raw_content": raw_content,
                "content_quality": content_quality,
            }
            news_id, inserted = await self.repo.upsert_raw_news(payload)
            mapped = await self._map_symbols(news_id, symbol, name, a.title, raw_content)
            await self.repo.upsert_news_symbol_maps(news_id, mapped)
            for item in mapped:
                await self.repo.upsert_stock_news_cache(
                    symbol=item["symbol"],
                    news_id=news_id,
                    published_at=pub,
                    rank_score=_rank_score(pub, content_quality, None),
                )
            if inserted:
                inserted_ids.append(news_id)
            else:
                deduped += 1

        finished = _utcnow()
        status = Status.NO_NEWS_FOUND if fetched == 0 else Status.READY
        await self.repo.set_status(symbol, status, job_id=job_id)
        await self.repo.set_priority(symbol, last_collected=finished)
        await self.repo.log_ingestion(
            symbol=symbol,
            provider="google_news",
            job_id=job_id,
            started_at=started,
            finished_at=finished,
            fetched=fetched,
            deduped=deduped,
            inserted=len(inserted_ids),
            status="success",
        )
        await self.session.commit()
        metrics.collect_runs.labels(provider="google_news", status="success").inc()

        # Invalidate cache so the next read populates with fresh PG content.
        await self.cache.invalidate(symbol)
        await self.cache.release_collect_lock(symbol)

        # Enqueue analysis for newly inserted articles (or run inline in worker/scheduler mode).
        for news_id in inserted_ids:
            if self.queue.enabled:
                self.queue.enqueue_analyze(news_id)
            else:
                await self.run_analyze(news_id)

        return len(inserted_ids)

    async def run_analyze(self, news_id: str, *, raise_on_failure: bool = False) -> None:
        raw = await self.repo.get_raw_news(str(news_id))
        if raw is None:
            return

        maps = await self.repo.get_symbols_for_news(raw.news_id)
        primary_symbol = maps[0].symbol if maps else ""
        try:
            result = await self.agent.analyze(
                title=raw.title, body=raw.raw_content, symbol=primary_symbol
            )
            impact_score = abs(float(result.sentiment_score or 0.0))
            importance = result.impact_level if result.impact_level in {"low", "medium", "high"} else "low"
            await self.repo.upsert_news_analysis(
                raw.news_id,
                {
                    "sentiment": result.sentiment,
                    "impact_score": max(0.0, min(1.0, impact_score)),
                    "importance": importance,
                    "summary": result.summary,
                    "market_effect": result.market_effect,
                    "related_symbols": result.related_symbols,
                    "status": "analyzed",
                    "error": None,
                },
            )
            for m in maps:
                await self.repo.upsert_stock_news_cache(
                    symbol=m.symbol,
                    news_id=raw.news_id,
                    published_at=raw.published_at,
                    rank_score=_rank_score(raw.published_at, raw.content_quality, importance),
                )
                await self.cache.invalidate(m.symbol)
            await self.session.commit()
        except Exception as exc:
            log.exception("analyze_failed", news_id=raw.news_id)
            symbol_for_log = primary_symbol or "__unknown__"
            await self.repo.upsert_news_analysis(
                raw.news_id,
                {
                    "sentiment": None,
                    "impact_score": None,
                    "importance": None,
                    "summary": None,
                    "market_effect": None,
                    "related_symbols": [],
                    "status": "failed",
                    "error": str(exc),
                },
            )
            await self.repo.log_ingestion(
                symbol=symbol_for_log,
                provider="news_agent_analysis",
                job_id=raw.news_id,
                started_at=_utcnow(),
                finished_at=_utcnow(),
                fetched=0,
                deduped=0,
                inserted=0,
                status="retry",
                error=str(exc),
            )
            await self.session.commit()
            if raise_on_failure:
                raise

    # ─── helpers ───────────────────────────────────────────────────────────────

    def _is_stale(self, last_collected: Optional[datetime]) -> bool:
        """Stale when we haven't collected for longer than cache TTL.

        Note: published_at is the news outlet's publish time — irrelevant for
        freshness of our pipeline. last_collected (from PriorityScore) reflects
        when our worker last ran.
        """
        if last_collected is None:
            return True
        age_s = (_utcnow() - last_collected.replace(tzinfo=None)).total_seconds()
        return age_s > self.cfg.cache_ttl_s

    def _cache_ttl_for(self, _symbol: str) -> int:
        return self.cfg.cache_ttl_s

    async def _resolve_company_name(self, symbol: str) -> Optional[str]:
        """Look up company name from existing Stock table (Prisma)."""
        try:
            from sqlalchemy import text

            row = (
                await self.session.execute(
                    text('SELECT name FROM "Stock" WHERE symbol = :s LIMIT 1'),
                    {"s": symbol},
                )
            ).first()
            if row and row[0]:
                return row[0]
        except Exception:
            pass
        return _load_stock_name_map().get(symbol)

    async def _map_symbols(
        self,
        news_id: str,
        symbol: str,
        company_name: str,
        title: str,
        body: Optional[str],
    ) -> list[dict]:
        text = f"{title} {body or ''}"
        return [
            {"news_id": news_id, **item}
            for item in map_symbols_from_text(
                text=text,
                target_symbol=symbol,
                target_name=company_name,
            )
        ]


def _content_quality(title: str, body: Optional[str]) -> float:
    length = len((body or "").strip())
    title_bonus = min(len((title or "").strip()) / 120.0, 1.0)
    body_score = min(length / 1500.0, 1.0)
    return round((title_bonus * 0.35) + (body_score * 0.65), 4)


def _rank_score(published_at: datetime, content_quality: float, importance: Optional[str]) -> float:
    importance_bonus = {"high": 0.35, "medium": 0.18, "low": 0.0}.get(importance or "low", 0.0)
    age_hours = max((_utcnow() - published_at.replace(tzinfo=None)).total_seconds() / 3600.0, 0.0)
    recency = max(0.0, 1.0 - min(age_hours / 168.0, 1.0))
    return round((recency * 0.55) + (content_quality * 0.10) + importance_bonus, 4)
