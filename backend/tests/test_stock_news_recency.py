"""NewsAnalysisService — 최근 2일 이내 기사만 사용, 없으면 뉴스 신호 미사용."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from stock_analysis.news_service import NewsAnalysisService

NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def _article(days_ago: float, sentiment="negative", url="https://news.example.com/a", risk="low"):
    return {
        "publishedAt": (NOW - timedelta(days=days_ago)).isoformat(),
        "sentiment": sentiment,
        "url": url,
        "title": "테스트 기사",
        "riskAlertLevel": risk,
    }


def _patch_storage(monkeypatch, articles):
    import news.storage as storage
    monkeypatch.setattr(storage, "get_articles_for_symbol", lambda **kw: articles)


def test_uses_recent_article_within_2_days(monkeypatch):
    _patch_storage(monkeypatch, [_article(1.0)])
    result = NewsAnalysisService().analyze("005930", as_of=NOW)
    assert result.sentiment == "negative"
    assert result.source_url == "https://news.example.com/a"


def test_drops_news_when_only_old_articles(monkeypatch):
    # 5월 16일자(약 25일 전)처럼 오래된 기사만 있으면 뉴스 신호를 쓰지 않는다.
    _patch_storage(monkeypatch, [_article(25.0), _article(10.0)])
    result = NewsAnalysisService().analyze("005930", as_of=NOW)
    assert result.sentiment is None
    assert result.source_url is None
    assert result.summary is None
    assert result.risk_factors == []


def test_boundary_just_over_2_days_excluded(monkeypatch):
    _patch_storage(monkeypatch, [_article(2.5)])
    assert NewsAnalysisService().analyze("005930", as_of=NOW).sentiment is None


def test_unparseable_date_excluded(monkeypatch):
    _patch_storage(monkeypatch, [{"publishedAt": "", "sentiment": "negative", "url": "https://x", "title": "t"}])
    assert NewsAnalysisService().analyze("005930", as_of=NOW).sentiment is None
