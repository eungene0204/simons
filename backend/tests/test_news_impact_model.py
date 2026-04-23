"""
Tests for news impact model.

Covers:
- Impact direction and score consistency with event type
- Confidence score bounds
- Risk alert level thresholds
- Signal generation from impact
- No look-ahead: valid_from = article.published_at
- Expected alpha sign matches direction
"""

from datetime import datetime, timezone, timedelta

from news.schemas import (
    ExtractedEvent,
    NormalizedArticle,
    ArticleSymbolMap,
)
from news.impact_model import estimate_impact, build_signals


def _make_article(article_id: str = "a1") -> NormalizedArticle:
    return NormalizedArticle(
        id=article_id,
        title="Test article",
        url="https://example.com",
        source="TestSource",
        published_at=datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        crawled_at=datetime(2024, 1, 15, 9, 5, 0, tzinfo=timezone.utc),
    )


def _make_event(
    article_id: str = "a1",
    event_type: str = "earnings_beat",
    sentiment: str = "positive",
    severity: float = 0.75,
    credibility: float = 0.85,
    novelty: float = 0.7,
    risk_flags: list = None,
    expected_horizon: str = "1d",
) -> ExtractedEvent:
    return ExtractedEvent(
        article_id=article_id,
        event_type=event_type,
        sentiment=sentiment,
        severity=severity,
        surprise=0.0,
        credibility=credibility,
        novelty=novelty,
        relevance=0.5,
        summary="Test",
        risk_flags=risk_flags or [],
        affected_entities=[],
        expected_horizon=expected_horizon,
    )


def _make_sym_map(symbol: str = "005930", article_id: str = "a1") -> ArticleSymbolMap:
    return ArticleSymbolMap(
        article_id=article_id,
        symbol=symbol,
        company_name="삼성전자",
        scope="stock",
        relevance=0.9,
    )


class TestEstimateImpact:
    def test_positive_event_direction(self):
        article = _make_article()
        event = _make_event(event_type="earnings_beat", sentiment="positive")
        impact = estimate_impact(article, event, symbol="005930")
        assert impact.impact_direction == "up"
        assert impact.impact_score > 0

    def test_negative_event_direction(self):
        article = _make_article()
        event = _make_event(event_type="earnings_miss", sentiment="negative")
        impact = estimate_impact(article, event, symbol="005930")
        assert impact.impact_direction == "down"
        assert impact.impact_score < 0

    def test_neutral_event(self):
        article = _make_article()
        event = _make_event(event_type="ceo_change", sentiment="neutral", severity=0.2)
        impact = estimate_impact(article, event)
        # Low severity neutral → either neutral or directional based on score
        assert impact.impact_score >= -1.0 and impact.impact_score <= 1.0

    def test_score_bounds(self):
        article = _make_article()
        for event_type in ["earnings_beat", "delisting_risk", "accounting_issue", "analyst_upgrade"]:
            sentiment = "negative" if "miss" in event_type or "risk" in event_type or "issue" in event_type else "positive"
            event = _make_event(event_type=event_type, sentiment=sentiment, severity=1.0)
            impact = estimate_impact(article, event)
            assert -1.0 <= impact.impact_score <= 1.0, f"Score out of bounds for {event_type}"

    def test_confidence_bounds(self):
        article = _make_article()
        event = _make_event()
        impact = estimate_impact(article, event)
        assert 0.0 <= impact.confidence_score <= 1.0

    def test_high_risk_events_alert_high(self):
        article = _make_article()
        for event_type in ["delisting_risk", "accounting_issue", "factory_fire"]:
            event = _make_event(event_type=event_type, sentiment="negative", severity=0.8)
            impact = estimate_impact(article, event)
            assert impact.risk_alert_level == "high", f"Expected high alert for {event_type}"

    def test_low_severity_no_alert(self):
        article = _make_article()
        event = _make_event(event_type="general_neutral", sentiment="neutral", severity=0.05)
        impact = estimate_impact(article, event)
        assert impact.risk_alert_level in ("none", "low")

    def test_rights_offering_negative_score(self):
        article = _make_article()
        event = _make_event(event_type="rights_offering", sentiment="negative", severity=0.65)
        impact = estimate_impact(article, event)
        assert impact.impact_score < 0
        assert impact.risk_alert_level in ("low", "medium")

    def test_expected_alpha_sign_matches_direction(self):
        article = _make_article()
        pos_event = _make_event(event_type="earnings_beat", sentiment="positive", severity=0.8)
        neg_event = _make_event(event_type="earnings_miss", sentiment="negative", severity=0.8)

        pos_impact = estimate_impact(article, pos_event)
        neg_impact = estimate_impact(article, neg_event)

        assert pos_impact.expected_alpha_1d > 0
        assert neg_impact.expected_alpha_1d < 0

    def test_high_credibility_boosts_confidence(self):
        article = _make_article()
        high_cred_event = _make_event(credibility=0.95, severity=0.7)
        low_cred_event = _make_event(credibility=0.3, severity=0.7)

        hi = estimate_impact(article, high_cred_event)
        lo = estimate_impact(article, low_cred_event)
        assert hi.confidence_score > lo.confidence_score

    def test_model_version_tagged(self):
        article = _make_article()
        event = _make_event()
        impact = estimate_impact(article, event)
        assert impact.model_version != ""


class TestBuildSignals:
    def test_signals_generated_per_symbol(self):
        article = _make_article()
        event = _make_event()
        impact = estimate_impact(article, event, symbol="005930")
        sym_maps = [_make_sym_map("005930"), _make_sym_map("000660")]
        signals = build_signals(article, event, impact, sym_maps)
        # 4 signal types × 2 symbols = 8
        assert len(signals) == 8

    def test_no_signals_for_pseudo_symbols(self):
        article = _make_article()
        event = _make_event(event_type="sector_tailwind", sentiment="positive")
        impact = estimate_impact(article, event)
        # Only macro/sector pseudo-symbol maps
        sym_maps = [
            ArticleSymbolMap(article_id=article.id, symbol="__macro__", scope="macro"),
            ArticleSymbolMap(article_id=article.id, symbol="__sector__", scope="sector"),
        ]
        signals = build_signals(article, event, impact, sym_maps)
        assert len(signals) == 0

    def test_valid_from_equals_published_at(self):
        article = _make_article()
        event = _make_event()
        impact = estimate_impact(article, event, symbol="005930")
        sym_maps = [_make_sym_map("005930")]
        signals = build_signals(article, event, impact, sym_maps)
        for sig in signals:
            # No look-ahead: signal is valid from article publish time
            assert sig.valid_from == article.published_at

    def test_signal_types_present(self):
        article = _make_article()
        event = _make_event()
        impact = estimate_impact(article, event, symbol="005930")
        sym_maps = [_make_sym_map("005930")]
        signals = build_signals(article, event, impact, sym_maps)
        types = {s.signal_type for s in signals}
        assert "news_event" in types
        assert "news_sentiment" in types
        assert "news_alpha_score" in types
        assert "news_risk_alert" in types

    def test_direction_consistency(self):
        article = _make_article()
        pos_event = _make_event(event_type="earnings_beat", sentiment="positive", severity=0.8)
        pos_impact = estimate_impact(article, pos_event, symbol="005930")
        sym_maps = [_make_sym_map("005930")]
        signals = build_signals(article, pos_event, pos_impact, sym_maps)
        alpha_sigs = [s for s in signals if s.signal_type == "news_alpha_score"]
        assert all(s.direction == "long" for s in alpha_sigs)

    def test_high_risk_signal_value(self):
        article = _make_article()
        event = _make_event(event_type="delisting_risk", sentiment="negative", severity=0.9,
                            risk_flags=["delisting_risk"])
        impact = estimate_impact(article, event, symbol="000000")
        sym_maps = [_make_sym_map("000000")]
        signals = build_signals(article, event, impact, sym_maps)
        risk_sigs = [s for s in signals if s.signal_type == "news_risk_alert"]
        assert all(s.value > 0 for s in risk_sigs)

    def test_no_look_ahead_valid_until(self):
        article = _make_article()
        event = _make_event(expected_horizon="5d")
        impact = estimate_impact(article, event, symbol="005930")
        sym_maps = [_make_sym_map("005930")]
        signals = build_signals(article, event, impact, sym_maps)
        for sig in signals:
            if sig.valid_until:
                # valid_until must be after valid_from
                assert sig.valid_until >= sig.valid_from
                # And not too far in the future (5d horizon)
                delta = (sig.valid_until - sig.valid_from).days
                assert 0 <= delta <= 10


class TestNoLookAheadEnforcement:
    """Critical: verify that signal timestamps respect look-ahead constraints."""

    def test_signal_valid_from_is_publish_time(self):
        publish_time = datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
        article = NormalizedArticle(
            id="la-test",
            title="어닝 서프라이즈",
            url="https://example.com",
            source="Test",
            published_at=publish_time,
            crawled_at=datetime(2024, 3, 15, 11, 0, 0, tzinfo=timezone.utc),
        )
        event = _make_event(article_id=article.id, event_type="earnings_beat", sentiment="positive")
        impact = estimate_impact(article, event, symbol="005930")
        sym_maps = [ArticleSymbolMap(article_id=article.id, symbol="005930", scope="stock")]
        signals = build_signals(article, event, impact, sym_maps)

        for sig in signals:
            assert sig.valid_from == publish_time, (
                f"Signal valid_from {sig.valid_from} != article published_at {publish_time}"
            )

    def test_after_market_article_for_next_session(self):
        # Article published at 17:00 KST (after market close)
        # valid_from should still be 17:00 — no signal available before that
        after_market = datetime(2024, 3, 15, 8, 0, 0, tzinfo=timezone.utc)  # 17:00 KST
        article = NormalizedArticle(
            id="am-test",
            title="장마감 후 실적 발표 어닝 서프라이즈",
            url="https://example.com",
            source="Test",
            published_at=after_market,
            crawled_at=after_market + timedelta(minutes=5),
        )
        event = _make_event(article_id=article.id)
        impact = estimate_impact(article, event, symbol="005930")
        sym_maps = [ArticleSymbolMap(article_id=article.id, symbol="005930", scope="stock")]
        signals = build_signals(article, event, impact, sym_maps)
        for sig in signals:
            assert sig.valid_from == after_market
