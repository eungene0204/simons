"""
FastAPI router for news_v2.

Mounted at /v2/news. Public endpoints:
  GET  /v2/news/{symbol}        — main tab response (cache → PG → enqueue)
  GET  /v2/news/{symbol}/status — lightweight status poll (used by SWR fast loop)
  POST /v2/news/{symbol}/refresh — force-enqueue collect (admin/dev)
  GET  /v2/news/_health         — liveness probe
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from news_v2 import observability as metrics
from news_v2.config import get_settings
from news_v2.db import get_session
from news_v2.logging_setup import get_logger
from news_v2.models import Status
from news_v2.service import NewsService

log = get_logger(__name__)

router = APIRouter(prefix="/v2/news", tags=["news_v2"])


# ─── Schemas ───────────────────────────────────────────────────────────────────


class NewsItemOut(BaseModel):
    newsId: str
    title: str
    url: str
    source: str
    publishedAt: datetime
    summary: Optional[str] = None
    sentiment: Optional[Literal["positive", "neutral", "negative"]] = None
    impactScore: float = Field(ge=0.0, le=1.0)
    importance: Literal["high", "medium", "low"] = "low"


class NewsResponseOut(BaseModel):
    symbol: str
    items: list[NewsItemOut]
    lastUpdatedAt: Optional[datetime] = None
    isStale: bool
    status: Literal["READY", "STALE", "COLLECTING", "NOT_COLLECTED", "NO_NEWS_FOUND", "FAILED"]
    source: Literal["redis", "postgres", "queue"]
    message: Optional[str] = None


class StatusOut(BaseModel):
    symbol: str
    status: str
    last_success_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    attempt_count: int = 0


class HealthOut(BaseModel):
    enabled: bool
    cache_enabled: bool
    queue_enabled: bool
    db_ok: bool


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/_health", response_model=HealthOut)
async def health(session: AsyncSession = Depends(get_session)) -> HealthOut:
    cfg = get_settings()
    try:
        from sqlalchemy import text

        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return HealthOut(
        enabled=cfg.enabled,
        cache_enabled=cfg.cache_enabled,
        queue_enabled=cfg.queue_enabled,
        db_ok=db_ok,
    )


@router.get("/{symbol}", response_model=NewsResponseOut)
async def get_news(
    symbol: str = Path(..., min_length=1, max_length=16, description="KR ticker"),
    limit: int = Query(30, ge=1, le=100),
    company_name: Optional[str] = Query(None, description="Optional override"),
    session: AsyncSession = Depends(get_session),
) -> NewsResponseOut:
    cfg = get_settings()
    if not cfg.enabled:
        raise HTTPException(status_code=503, detail="news_v2 is disabled")

    service = NewsService(session)
    started = time.perf_counter()
    try:
        result = await service.get_for_symbol(
            symbol=symbol, company_name=company_name, limit=limit
        )
    finally:
        metrics.request_latency.labels(route="get_news").observe(time.perf_counter() - started)

    return NewsResponseOut(
        symbol=symbol,
        items=[
            NewsItemOut(
                newsId=a.news_id,
                title=a.title,
                url=a.url,
                source=a.source,
                publishedAt=a.published_at,
                summary=a.summary,
                sentiment=a.sentiment,  # type: ignore[arg-type]
                impactScore=a.impact_score,
                importance=a.importance,  # type: ignore[arg-type]
            )
            for a in result.items
        ],
        lastUpdatedAt=result.fetched_at,
        isStale=result.stale,
        status=result.status,
        source=result.source,
        message=result.message,
    )


@router.get("/{symbol}/status", response_model=StatusOut)
async def get_status(
    symbol: str = Path(..., min_length=1, max_length=16),
    session: AsyncSession = Depends(get_session),
) -> StatusOut:
    from news_v2.repository import NewsRepository

    repo = NewsRepository(session)
    row = await repo.get_status(symbol)
    if row is None:
        return StatusOut(symbol=symbol, status=Status.NOT_COLLECTED, attempt_count=0)
    return StatusOut(
        symbol=symbol,
        status=row.status,
        last_success_at=row.last_success_at,
        last_attempt_at=row.last_attempt_at,
        attempt_count=row.attempt_count or 0,
    )


@router.post("/{symbol}/refresh", response_model=StatusOut)
async def force_refresh(
    symbol: str = Path(..., min_length=1, max_length=16),
    session: AsyncSession = Depends(get_session),
) -> StatusOut:
    cfg = get_settings()
    if not cfg.enabled:
        raise HTTPException(status_code=503, detail="news_v2 is disabled")

    service = NewsService(session)
    # Bypass cache lock entirely — admin-style action.
    inserted = await service.run_collect(symbol)
    log.info("manual_refresh", symbol=symbol, inserted=inserted)

    from news_v2.repository import NewsRepository

    repo = NewsRepository(session)
    row = await repo.get_status(symbol)
    return StatusOut(
        symbol=symbol,
        status=row.status if row else Status.READY,
        last_success_at=row.last_success_at if row else None,
        last_attempt_at=row.last_attempt_at if row else None,
        attempt_count=row.attempt_count if row else 0,
    )
