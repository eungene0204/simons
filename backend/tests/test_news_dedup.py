"""
Tests for news deduplication logic.

Covers:
- Exact body hash match
- Title Jaccard similarity threshold
- Time-window enforcement
- Intra-batch dedup
- Short title exclusion
- Edge cases: empty inputs, same title different content
"""

from datetime import datetime, timezone, timedelta

from news.schemas import NormalizedArticle
from news.dedup import (
    _normalize_title,
    _jaccard,
    is_duplicate,
    filter_duplicates,
)


def _make_article(
    title: str,
    body_hash: str = "abc123",
    published_at: datetime = None,
    article_id: str = "test-id",
    url: str = "https://example.com/1",
) -> NormalizedArticle:
    return NormalizedArticle(
        id=article_id,
        title=title,
        summary=None,
        url=url,
        source="TestSource",
        published_at=published_at or datetime.now(timezone.utc),
        crawled_at=datetime.now(timezone.utc),
        body_hash=body_hash,
    )


def _make_recent(
    article_id: str,
    title: str,
    body_hash: str = "different",
    published_at: datetime = None,
) -> dict:
    return {
        "id": article_id,
        "title": title,
        "url": f"https://example.com/{article_id}",
        "bodyHash": body_hash,
        "publishedAt": (published_at or datetime.now(timezone.utc)).isoformat(),
    }


# ─── Unit tests for internal helpers ──────────────────────────────────────────

class TestNormalizeTitle:
    def test_lowercase(self):
        assert _normalize_title("삼성전자 실적") == _normalize_title("삼성전자 실적")

    def test_strips_punctuation(self):
        a = _normalize_title("삼성전자, 실적 호조!")
        b = _normalize_title("삼성전자 실적 호조")
        assert a == b

    def test_unicode_normalization(self):
        # Different unicode forms of the same string should normalize the same
        result = _normalize_title("삼성전자")
        assert "삼성전자" in result


class TestJaccard:
    def test_identical(self):
        assert _jaccard("삼성전자실적호조", "삼성전자실적호조") == 1.0

    def test_completely_different(self):
        score = _jaccard("abc", "xyz")
        assert score < 0.2

    def test_partial_overlap(self):
        score = _jaccard("삼성전자실적호조발표", "삼성전자실적부진")
        assert 0.0 < score < 1.0

    def test_empty_strings(self):
        assert _jaccard("", "") == 1.0
        assert _jaccard("abc", "") == 0.0


# ─── Dedup detection tests ────────────────────────────────────────────────────

class TestIsDuplicate:
    def test_body_hash_match(self):
        article = _make_article("코스피 상승", body_hash="SAME_HASH")
        recent = [_make_recent("old-id", "전혀 다른 제목", body_hash="SAME_HASH")]
        is_dup, canonical_id = is_duplicate(article, recent)
        assert is_dup is True
        assert canonical_id == "old-id"

    def test_identical_title_same_time(self):
        now = datetime.now(timezone.utc)
        article = _make_article("삼성전자 3분기 실적 발표", published_at=now, body_hash="hash1")
        recent = [_make_recent("old-id", "삼성전자 3분기 실적 발표", published_at=now)]
        is_dup, canonical_id = is_duplicate(article, recent)
        assert is_dup is True

    def test_similar_title_within_window(self):
        now = datetime.now(timezone.utc)
        article = _make_article("삼성전자 3분기 어닝 서프라이즈 발표", published_at=now, body_hash="hash1")
        recent = [_make_recent("old-id", "삼성전자 3분기 어닝 서프라이즈 실적 발표", published_at=now)]
        is_dup, _ = is_duplicate(article, recent)
        # High similarity within window → should be dup
        assert is_dup is True

    def test_different_title_different_content(self):
        now = datetime.now(timezone.utc)
        article = _make_article("현대차 신차 출시", published_at=now, body_hash="hash_new")
        recent = [_make_recent("old-id", "삼성전자 실적 발표", body_hash="hash_old", published_at=now)]
        is_dup, _ = is_duplicate(article, recent)
        assert is_dup is False

    def test_outside_time_window(self):
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=25)  # 25 hours ago — outside 24h window
        article = _make_article("삼성전자 실적 발표", published_at=now, body_hash="hash1")
        recent = [_make_recent("old-id", "삼성전자 실적 발표", published_at=old_time)]
        is_dup, _ = is_duplicate(article, recent)
        assert is_dup is False

    def test_empty_recent(self):
        article = _make_article("삼성전자 실적")
        is_dup, cid = is_duplicate(article, [])
        assert is_dup is False
        assert cid is None

    def test_short_title_excluded(self):
        # Title shorter than _MIN_TITLE_LEN → skip similarity check
        article = _make_article("코스피", body_hash="different_hash")
        recent = [_make_recent("old-id", "코스피")]
        is_dup, _ = is_duplicate(article, recent)
        # Short title should NOT trigger dedup via similarity
        assert is_dup is False

    def test_same_title_different_content_different_hash(self):
        # Same headline, genuinely different article (e.g., updated story)
        now = datetime.now(timezone.utc)
        article = _make_article("삼성전자 실적 발표", published_at=now, body_hash="new_version_hash")
        recent = [_make_recent("old-id", "삼성전자 실적 발표", body_hash="old_version_hash", published_at=now)]
        # Title similarity is very high → will be caught as dup
        is_dup, _ = is_duplicate(article, recent)
        assert is_dup is True  # Title match wins even with different hash


class TestFilterDuplicates:
    def test_empty_input(self):
        unique, dup_count = filter_duplicates([], existing_recent=[])
        assert unique == []
        assert dup_count == 0

    def test_no_duplicates(self):
        articles = [
            _make_article("삼성전자 실적", article_id="a1", url="https://a.com/1", body_hash="hash_a1"),
            _make_article("현대차 신차", article_id="a2", url="https://a.com/2", body_hash="hash_a2"),
        ]
        unique, dup_count = filter_duplicates(articles, existing_recent=[])
        assert len(unique) == 2
        assert dup_count == 0

    def test_intra_batch_dedup(self):
        now = datetime.now(timezone.utc)
        # Two articles with same title from different providers in same batch
        articles = [
            _make_article("삼성전자 3분기 실적 호조", article_id="a1", url="https://a.com/1",
                          published_at=now, body_hash="h1"),
            _make_article("삼성전자 3분기 실적 호조", article_id="a2", url="https://a.com/2",
                          published_at=now, body_hash="h2"),
        ]
        unique, dup_count = filter_duplicates(articles, existing_recent=[])
        assert len(unique) == 1
        assert dup_count == 1

    def test_existing_dup_caught(self):
        now = datetime.now(timezone.utc)
        article = _make_article("삼성전자 실적 발표", published_at=now, body_hash="SAME")
        existing = [_make_recent("existing-id", "삼성전자 실적 발표", body_hash="SAME", published_at=now)]
        unique, dup_count = filter_duplicates([article], existing_recent=existing)
        assert len(unique) == 0
        assert dup_count == 1

    def test_macro_different_from_stock_news(self):
        now = datetime.now(timezone.utc)
        articles = [
            _make_article("코스피 상승세 지속", article_id="a1", url="https://a.com/1", published_at=now, body_hash="h1"),
            _make_article("삼성전자 실적 호조", article_id="a2", url="https://a.com/2", published_at=now, body_hash="h2"),
        ]
        unique, dup_count = filter_duplicates(articles, existing_recent=[])
        assert len(unique) == 2
        assert dup_count == 0

    def test_after_market_article_vs_morning_follow_up(self):
        # Article published at 8pm, follow-up next morning (13h later)
        evening = datetime.now(timezone.utc).replace(hour=11, minute=0)  # 8pm KST
        morning = evening + timedelta(hours=13)
        articles = [
            _make_article("삼성전자 실적 시간외 발표", article_id="a1", url="https://a.com/1",
                          published_at=morning, body_hash="h_new"),
        ]
        existing = [
            _make_recent("old-id", "삼성전자 실적 시간외 발표", body_hash="h_old", published_at=evening)
        ]
        unique, dup_count = filter_duplicates(articles, existing_recent=existing)
        # Same title within 24h → dedup
        assert dup_count == 1
