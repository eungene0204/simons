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
    id: int
    title: str
    summary: Optional[str] = None
    source: str
    url: str
    published_at: datetime
    sentiment: Optional[Literal["positive", "neutral", "negative"]] = None
    sentiment_score: Optional[float] = None
    impact_level: Optional[Literal["low", "medium", "high"]] = None
    market_effect: Optional[str] = None
    related_symbols: list[str] = Field(default_factory=list)
    ai_summary: Optional[str] = None


class NewsResponseOut(BaseModel):
    status: Literal["READY", "STALE", "COLLECTING", "NOT_COLLECTED", "NO_NEWS_FOUND", "FAILED"]
    source: Literal["redis", "postgres", "queue"]
    stale: bool
    items: list[NewsItemOut]
    fetched_at: Optional[datetime] = None
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
    limit: int = Query(20, ge=1, le=100),
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
        status=result.status,
        source=result.source,
        stale=result.stale,
        items=[
            NewsItemOut(
                id=a.id,
                title=a.title,
                summary=a.summary,
                source=a.source,
                url=a.url,
                published_at=a.published_at,
                sentiment=a.sentiment,  # type: ignore[arg-type]
                sentiment_score=a.sentiment_score,
                impact_level=a.impact_level,  # type: ignore[arg-type]
                market_effect=a.market_effect,
                related_symbols=a.related_symbols,
                ai_summary=a.ai_summary,
            )
            for a in result.items
        ],
        fetched_at=result.fetched_at,
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
