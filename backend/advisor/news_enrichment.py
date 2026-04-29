"""
Helpers for enriching advisor/coach requests with news context.

The frontend does not always send News Impact Agent output, so these helpers
derive a minimal per-symbol news context directly from the parsed strategy.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from news import storage

from .news_adapter import adapt_news, build_news_summary
from .schemas import NewsArticleSignal, NewsContext

logger = logging.getLogger(__name__)

_VALID_SENTIMENTS = {"positive", "negative", "neutral"}
_VALID_DIRECTIONS = {"up", "down", "neutral"}
_VALID_RISK_LEVELS = {"none", "low", "medium", "high"}
_MAX_AUTO_NEWS_SYMBOLS = 200


def _normalize_sentiment(value: Any) -> str:
    value = str(value or "neutral").lower()
    return value if value in _VALID_SENTIMENTS else "neutral"


def _normalize_direction(value: Any) -> str:
    value = str(value or "neutral").lower()
    return value if value in _VALID_DIRECTIONS else "neutral"


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


def build_news_context_from_strategy(
    parsed_strategy: Dict[str, Any],
    *,
    as_of: Optional[datetime] = None,
) -> List[NewsContext]:
    symbols = _extract_symbols(parsed_strategy or {})
    if not symbols:
        return []

    cutoff = as_of or datetime.now(timezone.utc)
    contexts: List[NewsContext] = []

    for symbol in symbols:
        alpha_signals = storage.get_signals_for_symbol(
            symbol=symbol,
            as_of=cutoff,
            signal_type="news_alpha_score",
            limit=3,
        )
        risk_signals = storage.get_signals_for_symbol(
            symbol=symbol,
            as_of=cutoff,
            signal_type="news_risk_alert",
            limit=3,
        )
        article_rows = storage.get_articles_for_symbol(symbol=symbol, as_of=cutoff, limit=3)

        latest_alpha = _coerce_float(alpha_signals[0].get("value")) if alpha_signals else 0.0
        risk_level = "none"
        if risk_signals:
            try:
                metadata = json.loads(risk_signals[0].get("metadata") or "{}")
            except Exception:
                metadata = {}
            risk_level = _normalize_risk_level(metadata.get("risk_alert"))
        elif article_rows:
            risk_level = _normalize_risk_level(article_rows[0].get("riskAlertLevel"))

        articles: List[NewsArticleSignal] = []
        for row in article_rows:
            articles.append(
                NewsArticleSignal(
                    event_type=str(row.get("eventType") or "general_neutral"),
                    sentiment=_normalize_sentiment(row.get("sentiment")),
                    impact_direction=_normalize_direction(row.get("impactDirection")),
                    impact_score=_coerce_float(row.get("impactScore")),
                    confidence_score=_coerce_float(row.get("confidenceScore"), 0.5),
                )
            )

        if not articles and risk_level == "none" and latest_alpha == 0.0:
            continue

        contexts.append(
            NewsContext(
                symbol=symbol,
                latest_alpha=latest_alpha,
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
