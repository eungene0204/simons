"""
FastAPI routes for the News Impact AI Agent.

All endpoints proxy through the news.service orchestrator.
Pagination: page/page_size query params (default: page=1, page_size=20).
Caching: in-process TTL cache for read endpoints (60s for lists, 300s for top).
No look-ahead: as_of param defaults to now(); backtests pass a specific date.

Route prefix: /news  (registered in main.py via app.include_router)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from news import service as news_service
from news import storage
from news.schemas import (
    NewsIngestRequest,
    NewsIngestResponse,
    NewsItemResponse,
    NewsListResponse,
    NewsSignalResponse,
    NewsAnalyzeRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/news", tags=["news"])

# ─── Simple in-process TTL cache ──────────────────────────────────────────────

_CACHE: Dict[str, tuple] = {}  # key → (value, expire_at)


def _cache_get(key: str) -> Optional[Any]:
    entry = _CACHE.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    return None


def _cache_set(key: str, value: Any, ttl: int = 60) -> None:
    _CACHE[key] = (value, time.time() + ttl)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_as_of(as_of: Optional[str]) -> Optional[datetime]:
    if not as_of:
        return None
    try:
        dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid as_of format: {as_of}")


def _sanitize(text: Optional[str]) -> Optional[str]:
    """Strip HTML tags and decode entities from stored text."""
    if not text:
        return None
    import re
    from html import unescape
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip() or None


def _row_to_response(row: Dict) -> NewsItemResponse:
    import json

    def _safe_dt(val) -> Optional[datetime]:
        if not val:
            return None
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        except Exception:
            return None

    risk_flags: List[str] = []
    try:
        flags_raw = row.get("riskFlags") or "[]"
        risk_flags = json.loads(flags_raw)
    except Exception:
        pass

    symbols_raw = row.get("symbols") or row.get("symbol") or ""
    symbols = [s for s in str(symbols_raw).split(",") if s and not s.startswith("__")]

    return NewsItemResponse(
        id=row["id"],
        title=row.get("title", ""),
        summary=_sanitize(row.get("eventSummary") or row.get("summary")),
        body=_sanitize(row.get("summary")),
        url=row.get("url", ""),
        source=row.get("source", ""),
        published_at=_safe_dt(row.get("publishedAt")) or datetime.now(timezone.utc),
        category=row.get("category"),
        symbols=symbols,
        scope=row.get("scope"),
        sector=row.get("sector"),
        event_type=row.get("eventType"),
        sentiment=row.get("sentiment"),
        severity=row.get("severity"),
        credibility=row.get("credibility"),
        risk_flags=risk_flags,
        impact_direction=row.get("impactDirection"),
        impact_score=row.get("impactScore"),
        confidence_score=row.get("confidenceScore"),
        risk_alert_level=row.get("riskAlertLevel"),
        expected_alpha_1d=row.get("expectedAlpha1d"),
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/top", response_model=NewsListResponse, summary="Top recent news with impact analysis")
async def get_top_news(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    scope: Optional[str] = Query(default=None, description="Filter by scope: stock | sector | macro"),
    as_of: Optional[str] = Query(default=None, description="ISO datetime for look-ahead-safe queries"),
):
    cache_key = f"news:top:{page}:{page_size}:{scope}:{as_of}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    as_of_dt = _parse_as_of(as_of)
    rows = storage.get_top_articles(as_of=as_of_dt, limit=page_size, page=page, scope=scope)
    items = [_row_to_response(r) for r in rows]

    resp = NewsListResponse(items=items, total=len(items), page=page, page_size=page_size)
    _cache_set(cache_key, resp, ttl=60)
    return resp


@router.get("/symbol/{symbol}", response_model=NewsListResponse, summary="News for a specific stock symbol")
async def get_news_for_symbol(
    symbol: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    as_of: Optional[str] = Query(default=None),
):
    cache_key = f"news:symbol:{symbol}:{page}:{page_size}:{as_of}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    as_of_dt = _parse_as_of(as_of)
    rows = storage.get_articles_for_symbol(symbol=symbol, as_of=as_of_dt, limit=page_size, page=page)
    total = storage.count_articles_for_symbol(symbol=symbol, as_of=as_of_dt)
    items = [_row_to_response(r) for r in rows]

    resp = NewsListResponse(items=items, total=total, page=page, page_size=page_size)
    _cache_set(cache_key, resp, ttl=60)
    return resp


@router.get("/item/{article_id}", response_model=NewsItemResponse, summary="Single article with full analysis")
async def get_news_item(article_id: str):
    cache_key = f"news:item:{article_id}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    row = storage.get_article_by_id(article_id)
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")

    # Merge event + impact into row
    event_row = storage.get_event_for_article(article_id)
    impact_row = storage.get_impact_for_article(article_id)
    sym_rows = storage.get_symbols_for_article(article_id)

    merged = dict(row)
    if event_row:
        merged.update({k: v for k, v in event_row.items() if k not in merged or merged[k] is None})
    if impact_row:
        merged.update({k: v for k, v in impact_row.items() if k not in merged or merged[k] is None})
    if sym_rows:
        merged["symbols"] = ",".join(s["symbol"] for s in sym_rows if not s["symbol"].startswith("__"))
        for s in sym_rows:
            if not s["symbol"].startswith("__"):
                merged.setdefault("scope", s.get("scope"))
                merged.setdefault("sector", s.get("sector"))

    resp = _row_to_response(merged)
    _cache_set(cache_key, resp, ttl=300)
    return resp


@router.get("/signals/{symbol}", response_model=NewsSignalResponse, summary="News-derived trading signals for a symbol")
async def get_signals_for_symbol(
    symbol: str,
    signal_type: Optional[str] = Query(default=None, description="news_event | news_sentiment | news_risk_alert | news_alpha_score"),
    as_of: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    as_of_dt = _parse_as_of(as_of)
    cutoff = as_of_dt or datetime.now(timezone.utc)

    rows = storage.get_signals_for_symbol(
        symbol=symbol,
        as_of=cutoff,
        signal_type=signal_type,
        limit=limit,
    )

    from news.schemas import NewsSignalRecord
    import json

    signals = []
    for r in rows:
        try:
            meta = json.loads(r.get("metadata") or "{}")
        except Exception:
            meta = {}

        def _safe_dt(v):
            if not v:
                return None
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except Exception:
                return None

        signals.append(
            NewsSignalRecord(
                article_id=r["articleId"],
                symbol=r["symbol"],
                signal_type=r["signalType"],
                value=r["value"],
                direction=r["direction"],
                confidence=r["confidence"],
                valid_from=_safe_dt(r["validFrom"]) or cutoff,
                valid_until=_safe_dt(r.get("validUntil")),
                metadata=meta,
                model_version=r.get("modelVersion", "v1"),
            )
        )

    return NewsSignalResponse(symbol=symbol, signals=signals, as_of=cutoff)


@router.get("/impact/{symbol}", summary="Current impact summary for a symbol")
async def get_impact_for_symbol(
    symbol: str,
    as_of: Optional[str] = Query(default=None),
):
    as_of_dt = _parse_as_of(as_of)
    cutoff = as_of_dt or datetime.now(timezone.utc)

    # Get most recent alpha signal
    alpha_sigs = storage.get_signals_for_symbol(symbol=symbol, as_of=cutoff, signal_type="news_alpha_score", limit=5)
    risk_sigs = storage.get_signals_for_symbol(symbol=symbol, as_of=cutoff, signal_type="news_risk_alert", limit=5)

    if not alpha_sigs and not risk_sigs:
        return {"symbol": symbol, "as_of": cutoff.isoformat(), "signals": [], "risk_alert_level": "none"}

    import json

    def _parse_sig(sigs):
        if not sigs:
            return None
        s = sigs[0]
        meta = {}
        try:
            meta = json.loads(s.get("metadata") or "{}")
        except Exception:
            pass
        return {
            "value": s.get("value"),
            "direction": s.get("direction"),
            "confidence": s.get("confidence"),
            "valid_from": s.get("validFrom"),
            "event_type": meta.get("event_type"),
            "risk_alert": meta.get("risk_alert"),
            "article_title": s.get("title"),
            "article_url": s.get("url"),
        }

    latest_alpha = _parse_sig(alpha_sigs)
    latest_risk = _parse_sig(risk_sigs)

    risk_level = "none"
    if latest_risk and latest_risk.get("value", 0) > 0:
        risk_level = latest_risk.get("risk_alert") or "low"

    return {
        "symbol": symbol,
        "as_of": cutoff.isoformat(),
        "latest_alpha": latest_alpha,
        "latest_risk": latest_risk,
        "risk_alert_level": risk_level,
    }


@router.get("/events/{symbol}", summary="Structured event history for a symbol")
async def get_events_for_symbol(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
    as_of: Optional[str] = Query(default=None),
):
    as_of_dt = _parse_as_of(as_of)
    rows = storage.get_articles_for_symbol(symbol=symbol, as_of=as_of_dt, limit=limit)

    events = []
    for row in rows:
        if row.get("eventType") is None:
            continue
        import json
        risk_flags = []
        try:
            risk_flags = json.loads(row.get("riskFlags") or "[]")
        except Exception:
            pass

        events.append({
            "article_id": row["id"],
            "title": row["title"],
            "published_at": row.get("publishedAt"),
            "source": row.get("source"),
            "event_type": row.get("eventType"),
            "sentiment": row.get("sentiment"),
            "severity": row.get("severity"),
            "credibility": row.get("credibility"),
            "risk_flags": risk_flags,
            "impact_direction": row.get("impactDirection"),
            "impact_score": row.get("impactScore"),
            "risk_alert_level": row.get("riskAlertLevel"),
            "expected_alpha_1d": row.get("expectedAlpha1d"),
            "summary": row.get("eventSummary"),
        })

    return {"symbol": symbol, "events": events, "total": len(events)}


# ─── Write endpoints ───────────────────────────────────────────────────────────

@router.post("/ingest", response_model=NewsIngestResponse, summary="Trigger news ingestion")
async def trigger_ingest(
    req: NewsIngestRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger news ingestion from configured providers.
    Runs synchronously (for small batches) or can be moved to background.
    """
    logs = await news_service.ingest(req)
    total = sum(log.inserted for log in logs)
    return NewsIngestResponse(logs=logs, total_inserted=total)


@router.post("/analyze", summary="Analyze a single stored article")
async def analyze_article(req: NewsAnalyzeRequest):
    """
    Run event extraction + impact estimation for a specific article.
    Useful for re-processing or forced re-analysis.
    """
    success = await news_service.analyze_article(req.article_id, force=req.force)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Article {req.article_id} not found or already analyzed (use force=true to re-run)",
        )
    return {"status": "ok", "article_id": req.article_id}


@router.post("/ingest-and-analyze", summary="Ingest + analyze pipeline (one shot)")
async def ingest_and_analyze(req: NewsIngestRequest):
    """
    Convenience endpoint: fetch, normalize, dedup, store, then analyze all new articles.
    Suitable for scheduled cron runs.
    """
    logs, analyzed = await news_service.ingest_and_analyze(req)
    total_inserted = sum(log.inserted for log in logs)
    return {
        "status": "ok",
        "total_inserted": total_inserted,
        "total_analyzed": analyzed,
        "logs": [log.model_dump() for log in logs],
    }


@router.get("/risk-alerts", summary="Active risk alerts across symbols (for virtual trading)")
async def get_risk_alerts(
    symbols: str = Query(..., description="Comma-separated symbol list"),
    as_of: Optional[str] = Query(default=None),
):
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="symbols must be non-empty")

    as_of_dt = _parse_as_of(as_of)
    alerts = news_service.get_risk_alerts_for_virtual_trading(symbol_list, as_of=as_of_dt)
    return {"alerts": alerts, "as_of": (as_of_dt or datetime.now(timezone.utc)).isoformat()}


@router.get("/fetch-body", summary="Scrape first paragraphs from a news article URL")
async def fetch_article_body(url: str = Query(...)):
    import httpx
    import re
    from html import unescape

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    def _extract(html: str) -> str:
        # Remove script/style blocks
        html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Extract <p> tag contents
        paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
        texts = []
        for p in paras:
            text = re.sub(r"<[^>]+>", "", p)
            text = unescape(text)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 30:
                texts.append(text)
            if len(" ".join(texts)) > 300:
                break
        return " ".join(texts)[:400]

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=8.0, follow_redirects=True) as client:
            res = await client.get(url)
        if res.status_code != 200:
            return {"body": None}
        body = _extract(res.text)
        return {"body": body or None}
    except Exception:
        return {"body": None}
