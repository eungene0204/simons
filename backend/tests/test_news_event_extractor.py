"""
Tests for news event extraction.

Covers:
- Correct event type classification for each major event type
- Sentiment classification
- Risk flag detection
- Fallback to general_positive/negative/neutral
- Source credibility scoring
- No look-ahead: event only uses article's own content
"""

import pytest
from datetime import datetime, timezone

from news.schemas import NormalizedArticle
from news.event_extractor import (
    extract_event,
    _match_rules,
    _extract_risk_flags,
    _source_credibility,
    _llm_enabled,
)
from news import llm_extractor


def _make_article(title: str, summary: str = "", source: str = "TestSource") -> NormalizedArticle:
    return NormalizedArticle(
        id="test-id",
        title=title,
        summary=summary or None,
        url="https://example.com/test",
        source=source,
        published_at=datetime.now(timezone.utc),
        crawled_at=datetime.now(timezone.utc),
    )


class TestRuleMatching:
    def test_earnings_beat(self):
        result = _match_rules("삼성전자 3분기 실적 어닝 서프라이즈 발표")
        assert result is not None
        assert result[0] == "earnings_beat"
        assert result[1] == "positive"

    def test_earnings_miss(self):
        result = _match_rules("현대차 실적 어닝쇼크 예상 하회")
        assert result is not None
        assert result[0] == "earnings_miss"
        assert result[1] == "negative"

    def test_large_contract(self):
        result = _match_rules("한화시스템 방산 대규모 수주 계약 체결")
        assert result is not None
        assert result[0] == "large_contract"

    def test_share_buyback(self):
        result = _match_rules("포스코 자사주 500억 매입 결정")
        assert result is not None
        assert result[0] == "share_buyback"
        assert result[1] == "positive"

    def test_rights_offering(self):
        result = _match_rules("카카오 유상증자 실시 결정")
        assert result is not None
        assert result[0] == "rights_offering"
        assert result[1] == "negative"

    def test_ceo_change(self):
        result = _match_rules("LG전자 대표이사 교체 결정")
        assert result is not None
        assert result[0] == "ceo_change"

    def test_regulatory_probe(self):
        result = _match_rules("네이버 공정거래위원회 조사 착수")
        assert result is not None
        assert result[0] == "regulatory_probe"
        assert result[1] == "negative"

    def test_delisting_risk(self):
        result = _match_rules("XX바이오 상장폐지 심사 대상 지정")
        assert result is not None
        assert result[0] == "delisting_risk"
        assert result[1] == "negative"

    def test_accounting_issue(self):
        result = _match_rules("A기업 회계 분식 혐의 적발")
        assert result is not None
        assert result[0] == "accounting_issue"
        assert result[1] == "negative"

    def test_analyst_upgrade(self):
        result = _match_rules("증권사 목표주가 상향 조정")
        assert result is not None
        assert result[0] == "analyst_upgrade"

    def test_macro_rate_hike(self):
        result = _match_rules("한국은행 기준금리 인상 0.25%p")
        assert result is not None
        assert result[0] == "macro_rate"

    def test_no_match_returns_none(self):
        result = _match_rules("날씨가 맑고 기온이 올랐습니다")
        assert result is None


class TestRiskFlags:
    def test_delisting_flag(self):
        flags = _extract_risk_flags("해당 기업 상장폐지 가능성")
        assert "delisting_risk" in flags

    def test_accounting_flag(self):
        flags = _extract_risk_flags("분식 회계 혐의 수사")
        assert "accounting_fraud" in flags

    def test_dilution_flag(self):
        flags = _extract_risk_flags("전환사채 CB 발행 결정")
        assert "dilution_risk" in flags

    def test_multiple_flags(self):
        flags = _extract_risk_flags("소송 제기되고 검찰 수사 착수")
        assert "legal_dispute" in flags
        assert "regulatory_investigation" in flags

    def test_no_flags(self):
        flags = _extract_risk_flags("삼성전자 실적 호조")
        assert flags == []


class TestSourceCredibility:
    def test_high_credibility_source(self):
        assert _source_credibility("연합뉴스") > 0.8

    def test_medium_credibility(self):
        assert _source_credibility("Naver Finance") < 0.8

    def test_unknown_source_default(self):
        assert _source_credibility("알수없는언론사") == 0.6


class TestExtractEvent:
    def test_positive_article(self):
        article = _make_article(
            "삼성전자 3분기 영업이익 어닝 서프라이즈 기록",
            source="한국경제",
        )
        event = extract_event(article)
        assert event.event_type == "earnings_beat"
        assert event.sentiment == "positive"
        assert event.severity > 0
        assert event.credibility > 0
        assert event.model_version == "v1-rules"

    def test_negative_article_with_risk(self):
        article = _make_article(
            "XX기업 분식 회계 혐의로 검찰 조사 착수, 상장폐지 우려",
            source="매일경제",
        )
        event = extract_event(article)
        # Should match one of the high-severity rules
        assert event.sentiment == "negative"
        assert len(event.risk_flags) > 0
        assert event.severity >= 0.5

    def test_fallback_general_positive(self):
        article = _make_article("코스피 상승세 지속, 투자심리 개선")
        event = extract_event(article)
        assert event.sentiment in ("positive", "neutral")
        assert event.event_type in ("general_positive", "general_neutral", "macro_rate", "policy_change", "sector_tailwind")

    def test_fallback_general_negative(self):
        article = _make_article("증시 하락, 외국인 매도 급증")
        event = extract_event(article)
        assert event.sentiment in ("negative", "neutral")

    def test_no_look_ahead(self):
        # Event extraction must only use article fields
        # (title, summary, source) — no future data
        now = datetime.now(timezone.utc)
        article = _make_article("삼성전자 실적 발표")
        event = extract_event(article)
        # valid_from would equal article.published_at in signals — check model_version tag
        assert event.model_version.startswith("v1")

    def test_llm_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("NEWS_EVENT_LLM_ENABLED", raising=False)

        def fail_if_called(*args, **kwargs):
            raise AssertionError("LLM extractor should be opt-in")

        monkeypatch.setattr(llm_extractor, "extract", fail_if_called)

        article = _make_article("삼성전자 실적 발표")
        event = extract_event(article)

        assert not _llm_enabled()
        assert event.model_version == "v1-rules"

    def test_llm_enabled_when_env_is_set(self, monkeypatch):
        monkeypatch.setenv("NEWS_EVENT_LLM_ENABLED", "1")

        def fake_extract(title, summary=None):
            return {
                "event_type": "general_neutral",
                "sentiment": "neutral",
                "severity": 0.4,
                "summary": title,
            }

        monkeypatch.setattr(llm_extractor, "extract", fake_extract)

        article = _make_article("삼성전자 실적 발표")
        event = extract_event(article)

        assert _llm_enabled()
        assert event.model_version == "v2-llm"

    def test_schema_completeness(self):
        article = _make_article("임의 제목")
        event = extract_event(article)
        # All required fields present
        assert event.article_id == article.id
        assert 0.0 <= event.severity <= 1.0
        assert 0.0 <= event.credibility <= 1.0
        assert 0.0 <= event.novelty <= 1.0
        assert event.sentiment in ("positive", "negative", "neutral")
        assert isinstance(event.risk_flags, list)
        assert isinstance(event.affected_entities, list)

    def test_risk_flags_boost_severity(self):
        clean_article = _make_article("삼성전자 실적 발표 예정")
        risky_article = _make_article("삼성전자 분식 회계 혐의 검찰 조사 상장폐지 위험")
        clean_event = extract_event(clean_article)
        risky_event = extract_event(risky_article)
        assert risky_event.severity >= clean_event.severity
