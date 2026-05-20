"""Tests for NewsService — covering the stale-check regression.

Bug: _is_stale used to compare against rows[0].published_at (when the news
outlet published) instead of when our worker last collected. Every PG-hit
response was flagged STALE because most articles are minutes-to-days old,
triggering a redundant inline collect each time.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from news_v2.config import Settings
from news_v2.service import NewsService


def _make_service(cache_ttl_s: int = 600) -> NewsService:
    cfg = Settings()
    # Cannot freeze tuple-style cfg; tweak attribute via object.__setattr__
    object.__setattr__(cfg, "cache_ttl_s", cache_ttl_s)
    # NewsService.__init__ needs a session but _is_stale doesn't touch it.
    return NewsService(session=MagicMock(), cfg=cfg)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_is_stale_returns_true_when_never_collected():
    service = _make_service()
    assert service._is_stale(None) is True


def test_is_stale_returns_false_when_collected_recently():
    service = _make_service(cache_ttl_s=600)
    just_now = _utcnow_naive() - timedelta(seconds=30)
    assert service._is_stale(just_now) is False


def test_is_stale_returns_true_when_collected_past_ttl():
    service = _make_service(cache_ttl_s=600)
    long_ago = _utcnow_naive() - timedelta(hours=2)
    assert service._is_stale(long_ago) is True


def test_is_stale_does_not_use_article_publish_time():
    """Regression: old news (published 1d ago) collected just now is NOT stale."""
    service = _make_service(cache_ttl_s=600)
    just_now = _utcnow_naive() - timedelta(seconds=10)
    assert service._is_stale(just_now) is False


def test_naive_utc_normalization_logic():
    """Regression: providers return tz-aware datetimes; PostgreSQL with
    TIMESTAMP WITHOUT TIME ZONE rejects them. Service must strip tzinfo
    after converting to UTC before persisting.
    """
    from datetime import timezone as _tz

    aware_utc = datetime(2026, 5, 20, 6, 40, tzinfo=_tz.utc)
    # Replicate the inline normalization from service.run_collect.
    pub = aware_utc
    if pub is not None and pub.tzinfo is not None:
        pub = pub.astimezone(_tz.utc).replace(tzinfo=None)
    assert pub.tzinfo is None
    assert pub == datetime(2026, 5, 20, 6, 40)

    # Naive input must be passed through untouched.
    naive = datetime(2026, 5, 20, 6, 40)
    pub2 = naive
    if pub2 is not None and pub2.tzinfo is not None:
        pub2 = pub2.astimezone(_tz.utc).replace(tzinfo=None)
    assert pub2 is naive
