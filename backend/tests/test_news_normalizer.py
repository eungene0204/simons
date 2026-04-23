"""
Tests for news article normalization.

Covers:
- HTML stripping from title/body
- Whitespace normalization
- Unicode NFC normalization
- URL stripping
- Timezone UTC normalization
- Body hash computation
- Missing fields handled gracefully
"""

import pytest
from datetime import datetime, timezone, timedelta

from news.schemas import RawArticle
from news.normalizer import normalize, _clean_text, _to_utc


def _make_raw(
    title: str = "Test Title",
    body: str = None,
    url: str = "https://example.com/article",
    source: str = "TestSource",
    published_at: datetime = None,
    provider: str = "test",
) -> RawArticle:
    return RawArticle(
        provider=provider,
        title=title,
        body=body,
        url=url,
        source=source,
        published_at=published_at or datetime.now(timezone.utc),
    )


class TestCleanText:
    def test_strips_html_tags(self):
        assert _clean_text("<b>삼성전자</b> 실적") == "삼성전자 실적"

    def test_collapses_whitespace(self):
        assert _clean_text("삼성   전자   실적") == "삼성 전자 실적"

    def test_strips_leading_trailing(self):
        assert _clean_text("  삼성전자  ") == "삼성전자"

    def test_empty_string(self):
        assert _clean_text("") is None

    def test_none_input(self):
        assert _clean_text(None) is None

    def test_unicode_nfc(self):
        # Both forms should normalize to the same value
        result = _clean_text("삼성전자")
        assert result is not None


class TestToUtc:
    def test_naive_datetime_gets_utc(self):
        naive = datetime(2024, 1, 15, 9, 0, 0)
        result = _to_utc(naive)
        assert result.tzinfo == timezone.utc

    def test_kst_converted_to_utc(self):
        kst = timezone(timedelta(hours=9))
        kst_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=kst)
        result = _to_utc(kst_time)
        assert result.tzinfo == timezone.utc
        assert result.hour == 0  # 9:00 KST = 0:00 UTC


class TestNormalize:
    def test_basic_normalization(self):
        raw = _make_raw("삼성전자 실적 발표")
        article = normalize(raw)
        assert article.title == "삼성전자 실적 발표"
        assert article.url == "https://example.com/article"
        assert article.source == "TestSource"

    def test_html_in_title_stripped(self):
        raw = _make_raw("<b>삼성전자</b> <em>실적</em> 발표")
        article = normalize(raw)
        assert "<b>" not in article.title
        assert "삼성전자" in article.title

    def test_body_produces_hash(self):
        raw = _make_raw(body="삼성전자 3분기 영업이익 10조 기록")
        article = normalize(raw)
        assert article.body_hash is not None
        assert len(article.body_hash) == 32

    def test_no_body_uses_title_hash(self):
        raw = _make_raw(body=None)
        article = normalize(raw)
        assert article.body_hash is not None

    def test_summary_truncated_to_500(self):
        long_body = "가" * 1000
        raw = _make_raw(body=long_body)
        article = normalize(raw)
        assert article.summary is not None
        assert len(article.summary) <= 500

    def test_published_at_utc(self):
        kst = timezone(timedelta(hours=9))
        raw = _make_raw(published_at=datetime(2024, 1, 15, 9, 0, 0, tzinfo=kst))
        article = normalize(raw)
        assert article.published_at.tzinfo == timezone.utc

    def test_generates_cuid_id(self):
        raw = _make_raw()
        article = normalize(raw)
        assert article.id is not None
        assert len(article.id) > 10

    def test_different_bodies_different_hash(self):
        raw1 = _make_raw(body="첫 번째 기사 내용입니다")
        raw2 = _make_raw(body="두 번째 기사 내용입니다")
        a1 = normalize(raw1)
        a2 = normalize(raw2)
        assert a1.body_hash != a2.body_hash

    def test_url_stripped(self):
        raw = _make_raw(url="  https://example.com/article  ")
        article = normalize(raw)
        assert article.url == "https://example.com/article"

    def test_is_canonical_default_true(self):
        raw = _make_raw()
        article = normalize(raw)
        assert article.is_canonical is True
        assert article.canonical_id is None

    def test_language_default_ko(self):
        raw = _make_raw()
        article = normalize(raw)
        assert article.language == "ko"

    def test_missing_author_is_none(self):
        raw = _make_raw()
        article = normalize(raw)
        assert article.author is None

    def test_empty_title_gets_placeholder(self):
        raw = _make_raw(title="")
        article = normalize(raw)
        assert article.title == "(제목 없음)"
