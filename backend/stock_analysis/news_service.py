"""
NewsAnalysisService — 종목 뉴스 감성 집계(단일 책임: 뉴스 분석).

라이브 뉴스 에이전트(news_v2)가 분석해 둔 기사를 재사용한다. news_v2 에이전트는
종목별 기사를 `stock_news_cache`(symbol↔newsId)에 캐싱하고, 본문은 `news_raw`,
감성/영향도는 `news_analysis`(sentiment/importance)에 적재한다. 여기서는 이 라이브
스키마를 조인해 읽어 긍정/부정/중립으로 집계만 한다.

저장소는 news_v2 설정(`NEWSV2_DB_URL`)을 그대로 따른다 — 운영은 PostgreSQL,
개발은 sqlite일 수 있어 둘 다 async 드라이버(asyncpg/aiosqlite)로 읽는다.
뉴스가 없으면 sentiment=None, summary=None을 반환한다(환각 금지).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 오래된 뉴스로 종목을 판단하지 않는다 — 최근 N일 이내 기사만 사용한다.
# 뉴스 감성은 추천 점수의 1/3을 차지하므로 거래 일주일(7일)을 한도로 둔다.
# 그 안에 기사가 없으면 뉴스 신호를 아예 쓰지 않는다(sentiment=None).
_MAX_NEWS_AGE_DAYS = 7


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


# camelCase 컬럼은 PostgreSQL에서 폴딩을 막기 위해 큰따옴표로 인용한다(sqlite도 동일 허용).
_ARTICLES_SQL = """
    SELECT r."publishedAt"  AS "publishedAt",
           a.sentiment      AS sentiment,
           a.importance     AS importance,
           a."impactScore"  AS "impactScore",
           a."marketEffect" AS "marketEffect",
           r.title          AS title,
           r.url            AS url
    FROM stock_news_cache c
    JOIN news_raw r ON r."newsId" = c."newsId"
    LEFT JOIN news_analysis a ON a."newsId" = c."newsId"
    WHERE c.symbol = :symbol
    ORDER BY c."publishedAt" DESC
    LIMIT :limit
"""


async def _async_load(url: str, symbol: str, limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text(_ARTICLES_SQL), {"symbol": symbol, "limit": limit})
            return [dict(row._mapping) for row in res]
    finally:
        await engine.dispose()


def _load_v2_articles(symbol: str, as_of: datetime, limit: int = 30) -> list[dict[str, Any]]:
    """news_v2 라이브 스키마에서 종목별 최근 기사를 읽는다.

    `stock_news_cache`(종목→기사 매핑) + `news_raw`(본문/발행일) + `news_analysis`
    (감성/영향도)를 조인한다. 저장소 URL은 news_v2 설정에서 그대로 가져와
    에이전트가 쓰는 바로 그 DB(운영 PostgreSQL / 개발 sqlite)를 읽는다.
    look-ahead(as_of) 및 최신순 정렬은 호출부(파이썬)에서 처리한다.

    동기 컨텍스트(에이전트는 asyncio.to_thread로 실행됨)에서 호출되므로
    asyncio.run으로 비동기 조회를 돌린다 — 실행 중 루프가 없는 워커 스레드 전제.
    """
    try:
        from news_v2.config import get_settings

        url = get_settings().db_url
    except Exception:
        logger.debug("news_v2 설정 로드 실패 — 뉴스 데이터 없음", exc_info=True)
        return []

    try:
        articles = asyncio.run(_async_load(url, symbol, limit))
    except Exception:
        logger.debug("news_v2 store 조회 실패 — 뉴스 데이터 없음", exc_info=True)
        return []

    # look-ahead 차단: as_of 이후 기사는 제외(백테스트 안전).
    return [a for a in articles if _published_at_or_none(a.get("publishedAt"), as_of) is not None]


def _published_at_or_none(published_at: Any, as_of: datetime) -> Optional[datetime]:
    dt = NewsAnalysisService._parse_dt(published_at)
    if dt is None or dt > as_of:
        return None
    return dt


class NewsAnalysisService:
    def analyze(self, symbol: str, *, as_of: Optional[datetime] = None) -> NewsResult:
        cutoff = as_of or datetime.now(timezone.utc)
        articles = _load_v2_articles(symbol, cutoff, limit=30)

        # 최근 N일 이내 기사만 남긴다. 없으면 뉴스 신호를 쓰지 않는다.
        min_published = cutoff - timedelta(days=_MAX_NEWS_AGE_DAYS)
        articles = [a for a in articles if self._is_recent(a.get("publishedAt"), min_published)][:10]
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

        risk_alert, risk_factors = self._risk_from_negatives(articles)

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
    def _risk_from_negatives(articles: list[dict]) -> tuple[Optional[str], list[str]]:
        """부정 기사의 영향도(importance)로 위험 경보를 산정한다.

        긍정·중립 기사의 high impact는 위험이 아니므로 부정 기사만 본다.
        """
        negatives = [a for a in articles if str(a.get("sentiment")) == "negative"]
        impacts = {str(a.get("importance") or "low") for a in negatives}
        if "high" in impacts:
            risk_alert: Optional[str] = "high"
        elif "medium" in impacts:
            risk_alert = "medium"
        else:
            risk_alert = None
        risk_factors = [
            str(a["title"]).strip()
            for a in negatives
            if str(a.get("importance")) in {"high", "medium"} and a.get("title")
        ]
        return risk_alert, risk_factors

    @staticmethod
    def _parse_dt(published_at: Any) -> Optional[datetime]:
        """publishedAt을 tz-aware datetime으로 파싱. 실패 시 None.

        PostgreSQL은 datetime 객체를, sqlite는 ISO 문자열을 돌려준다 — 둘 다 처리한다.
        naive(타임존 없음)는 UTC로 간주한다(news_v2 저장 규약).
        """
        if not published_at:
            return None
        if isinstance(published_at, datetime):
            dt = published_at
        else:
            text = str(published_at).strip().replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @classmethod
    def _is_recent(cls, published_at: Any, min_published: datetime) -> bool:
        """기사 publishedAt이 min_published 이후면 True. 파싱 실패 시 보수적으로 제외(False)."""
        dt = cls._parse_dt(published_at)
        return dt is not None and dt >= min_published

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
