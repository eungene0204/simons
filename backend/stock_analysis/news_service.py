"""
NewsAnalysisService — 종목 뉴스 감성 집계(단일 책임: 뉴스 분석).

기존 `news.storage`의 per-symbol 헬퍼를 재사용한다(coach/advisor와 동일 소스).
뉴스가 없으면 sentiment=None, summary=None을 반환한다(환각 금지).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 오래된 뉴스로 종목을 판단하지 않는다 — 최근 N일 이내 기사만 사용한다.
# 2일 이내 기사가 없으면 뉴스 신호를 아예 쓰지 않는다(sentiment=None).
_MAX_NEWS_AGE_DAYS = 2


@dataclass
class NewsResult:
    sentiment: Optional[str] = None   # positive | neutral | negative
    summary: Optional[str] = None
    risk_alert_level: Optional[str] = None  # none | low | medium | high
    article_count: int = 0
    risk_factors: list[str] = field(default_factory=list)
    source_url: Optional[str] = None   # 대표 출처 기사 URL(설명의 '뉴스'에 링크용)
    source_title: Optional[str] = None


_VALID_SENTIMENTS = {"positive", "negative", "neutral"}


class NewsAnalysisService:
    def analyze(self, symbol: str, *, as_of: Optional[datetime] = None) -> NewsResult:
        try:
            from news import storage
        except Exception:
            logger.debug("news.storage import 실패 — 뉴스 데이터 없음", exc_info=True)
            return NewsResult()

        cutoff = as_of or datetime.now(timezone.utc)
        try:
            articles = storage.get_articles_for_symbol(symbol=symbol, as_of=cutoff, limit=10)
        except Exception:
            logger.debug("get_articles_for_symbol 실패 — 뉴스 데이터 없음", exc_info=True)
            return NewsResult()

        # 최근 2일 이내 기사만 남긴다. 없으면 뉴스 신호를 쓰지 않는다.
        min_published = cutoff - timedelta(days=_MAX_NEWS_AGE_DAYS)
        articles = [a for a in articles if self._is_recent(a.get("publishedAt"), min_published)]
        if not articles:
            return NewsResult()

        positive = sum(1 for a in articles if str(a.get("sentiment")) == "positive")
        negative = sum(1 for a in articles if str(a.get("sentiment")) == "negative")
        if positive > negative:
            sentiment = "positive"
        elif negative > positive:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        risk_levels = [str(a.get("riskAlertLevel") or "none") for a in articles]
        risk_alert = "high" if "high" in risk_levels else ("medium" if "medium" in risk_levels else "low")

        risk_factors: list[str] = []
        for a in articles:
            if str(a.get("riskAlertLevel")) in {"high", "medium"} and a.get("title"):
                risk_factors.append(str(a["title"]).strip())

        summary = f"최근 뉴스 {len(articles)}건 (긍정 {positive}, 부정 {negative})"
        source_url, source_title = self._pick_source(articles, sentiment)
        return NewsResult(
            sentiment=sentiment,
            summary=summary,
            risk_alert_level=risk_alert,
            article_count=len(articles),
            risk_factors=risk_factors[:3],
            source_url=source_url,
            source_title=source_title,
        )

    @staticmethod
    def _is_recent(published_at: Any, min_published: datetime) -> bool:
        """기사 publishedAt이 min_published 이후면 True. 파싱 실패 시 보수적으로 제외(False)."""
        if not published_at:
            return False
        text = str(published_at).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= min_published

    @staticmethod
    def _pick_source(articles: list, sentiment: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """대표 출처 기사를 고른다. 전체 감성과 같은 방향의 기사를 우선,
        없으면 URL이 있는 첫 기사를 쓴다."""
        def has_url(a) -> bool:
            return str(a.get("url") or "").strip().startswith("http")

        candidates = [a for a in articles if has_url(a)]
        if not candidates:
            return None, None
        if sentiment in {"positive", "negative"}:
            aligned = [a for a in candidates if str(a.get("sentiment")) == sentiment]
            if aligned:
                top = aligned[0]
                return str(top.get("url")).strip(), (str(top.get("title")).strip() or None)
        top = candidates[0]
        return str(top.get("url")).strip(), (str(top.get("title")).strip() or None)
