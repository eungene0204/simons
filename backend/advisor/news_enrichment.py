"""
Helpers for enriching advisor/coach requests with news context.

The frontend does not always send News Impact Agent output, so these helpers
derive a minimal per-symbol news context directly from the parsed strategy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from stock_analysis.news_service import NewsAnalysisService, load_articles_for_symbols

from .news_adapter import adapt_news, build_news_summary
from .schemas import NewsArticleSignal, NewsContext

logger = logging.getLogger(__name__)

_VALID_SENTIMENTS = {"positive", "negative", "neutral"}
_VALID_RISK_LEVELS = {"none", "low", "medium", "high"}
_MAX_AUTO_NEWS_SYMBOLS = 200


def _normalize_sentiment(value: Any) -> str:
    value = str(value or "neutral").lower()
    return value if value in _VALID_SENTIMENTS else "neutral"


def _normalize_risk_level(value: Any) -> str:
    value = str(value or "none").lower()
    return value if value in _VALID_RISK_LEVELS else "none"


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _extract_symbols(parsed_strategy: Dict[str, Any]) -> List[str]:
    symbols = parsed_strategy.get("symbols")
    if isinstance(symbols, list):
        cleaned = [str(symbol).strip() for symbol in symbols if str(symbol).strip()]
        return list(dict.fromkeys(cleaned))[:_MAX_AUTO_NEWS_SYMBOLS]

    markets = parsed_strategy.get("universe")
    if not isinstance(markets, list) or not markets:
        return []

    try:
        from engine.strategy_converter import _load_universe

        resolved = _load_universe([str(market) for market in markets if str(market).strip()])
        return resolved[:_MAX_AUTO_NEWS_SYMBOLS]
    except Exception:
        logger.exception("failed to resolve strategy universe for news enrichment")
        return []


def _direction_from_sentiment(sentiment: str) -> str:
    return {"positive": "up", "negative": "down"}.get(sentiment, "neutral")


def _signed_impact(raw: Any, sentiment: str) -> float:
    """news_v2 impactScore(크기)를 감성 방향으로 부호화해 -1..1로 클램프한다."""
    score = min(abs(_coerce_float(raw)), 1.0)
    if sentiment == "negative":
        return -score
    if sentiment == "positive":
        return score
    return 0.0


def build_news_context_from_strategy(
    parsed_strategy: Dict[str, Any],
    *,
    as_of: Optional[datetime] = None,
) -> List[NewsContext]:
    symbols = _extract_symbols(parsed_strategy or {})
    if not symbols:
        return []

    cutoff = as_of or datetime.now(timezone.utc)
    # 종목분석 에이전트와 동일한 news_v2 저장소(NEWSV2_DB_URL)를 읽는다 — 운영/로컬 단일 소스.
    articles_by_symbol = load_articles_for_symbols(symbols, cutoff, limit=3)

    contexts: List[NewsContext] = []
    for symbol in symbols:
        rows = articles_by_symbol.get(symbol) or []
        if not rows:
            continue

        risk_alert, _factors = NewsAnalysisService._risk_from_negatives(rows)
        risk_level = _normalize_risk_level(risk_alert)

        articles: List[NewsArticleSignal] = []
        for row in rows:
            sentiment = _normalize_sentiment(row.get("sentiment"))
            title = str(row.get("title") or "").strip() or None
            url = str(row.get("url") or "").strip() or None
            articles.append(
                NewsArticleSignal(
                    event_type="general_neutral",
                    sentiment=sentiment,
                    impact_direction=_direction_from_sentiment(sentiment),
                    impact_score=_signed_impact(row.get("impactScore"), sentiment),
                    confidence_score=0.5,
                    title=title,
                    url=url,
                )
            )

        contexts.append(
            NewsContext(
                symbol=symbol,
                latest_alpha=0.0,
                risk_alert_level=risk_level,
                articles=articles,
            )
        )

    return contexts


def build_coach_news_insight(news_contexts: List[NewsContext]) -> Optional[Dict[str, Any]]:
    if not news_contexts:
        return None

    aggregate = adapt_news(news_contexts)
    symbols: List[Dict[str, Any]] = []
    for ctx in news_contexts[:3]:
        positive_count = sum(1 for article in ctx.articles if article.sentiment == "positive")
        negative_count = sum(1 for article in ctx.articles if article.sentiment == "negative")
        summary = (
            f"최근 뉴스 {len(ctx.articles)}건 "
            f"(긍정 {positive_count}, 부정 {negative_count})"
        )
        symbols.append(
            {
                "symbol": ctx.symbol,
                "latest_alpha": ctx.latest_alpha,
                "risk_alert_level": ctx.risk_alert_level,
                "summary": summary,
                "articles": [
                    {
                        **article.model_dump(),
                        "expected_alpha_1d": ctx.latest_alpha,
                    }
                    for article in ctx.articles[:2]
                ],
            }
        )

    return {
        "market_news_available": True,
        "market_level_summary": build_news_summary(aggregate),
        "symbols": symbols,
    }
