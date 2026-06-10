"""NewsAnalysisService — news_v2 라이브 스키마 기사로 감성 집계, 최근 7일 이내만 사용."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from stock_analysis import news_service
from stock_analysis.news_service import NewsAnalysisService

NOW = datetime(2026, 6, 10, tzinfo=timezone.utc)


def _article(days_ago: float, sentiment="negative", url="https://news.example.com/a",
             impact="low", title="테스트 기사"):
    return {
        "publishedAt": (NOW - timedelta(days=days_ago)).isoformat(),
        "sentiment": sentiment,
        "impactScore": 0.5,
        "importance": impact,
        "marketEffect": "",
        "url": url,
        "title": title,
    }


def _patch_articles(monkeypatch, articles):
    # _load_v2_articles는 look-ahead(as_of 이후 제외)까지 책임지므로 테스트도 동일하게 거른다.
    def fake(symbol, as_of, limit=30):
        out = []
        for a in articles:
            dt = NewsAnalysisService._parse_dt(a.get("publishedAt"))
            if dt is not None and dt <= as_of:
                out.append(a)
        return out

    monkeypatch.setattr(news_service, "_load_v2_articles", fake)


def test_uses_recent_article_within_window(monkeypatch):
    _patch_articles(monkeypatch, [_article(1.0)])
    result = NewsAnalysisService().analyze("005930", as_of=NOW)
    assert result.sentiment == "negative"
    assert result.source_url == "https://news.example.com/a"


def test_aggregates_positive_majority(monkeypatch):
    _patch_articles(monkeypatch, [
        _article(1.0, sentiment="positive", url="https://news.example.com/p"),
        _article(2.0, sentiment="positive", url="https://news.example.com/p2"),
        _article(3.0, sentiment="negative"),
    ])
    result = NewsAnalysisService().analyze("005930", as_of=NOW)
    assert result.sentiment == "positive"
    assert result.article_count == 3
    assert "긍정 2" in result.summary and "부정 1" in result.summary


def test_high_impact_negative_sets_risk_alert(monkeypatch):
    _patch_articles(monkeypatch, [_article(1.0, sentiment="negative", impact="high", title="리콜 사태")])
    result = NewsAnalysisService().analyze("005930", as_of=NOW)
    assert result.risk_alert_level == "high"
    assert "리콜 사태" in result.risk_factors


def test_high_impact_positive_is_not_a_risk(monkeypatch):
    _patch_articles(monkeypatch, [_article(1.0, sentiment="positive", impact="high")])
    result = NewsAnalysisService().analyze("005930", as_of=NOW)
    assert result.risk_alert_level is None
    assert result.risk_factors == []


def test_drops_news_when_only_old_articles(monkeypatch):
    # 7일을 넘긴 기사(10일·25일 전)만 있으면 뉴스 신호를 쓰지 않는다.
    _patch_articles(monkeypatch, [_article(25.0), _article(10.0)])
    result = NewsAnalysisService().analyze("005930", as_of=NOW)
    assert result.sentiment is None
    assert result.source_url is None
    assert result.summary is None
    assert result.risk_factors == []


def test_boundary_just_over_window_excluded(monkeypatch):
    _patch_articles(monkeypatch, [_article(7.5)])
    assert NewsAnalysisService().analyze("005930", as_of=NOW).sentiment is None


def test_unparseable_date_excluded(monkeypatch):
    _patch_articles(monkeypatch, [
        {"publishedAt": "", "sentiment": "negative", "url": "https://x", "title": "t"},
    ])
    assert NewsAnalysisService().analyze("005930", as_of=NOW).sentiment is None
