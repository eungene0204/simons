"""Tests for news_v2.priority — score computation + tier assignment."""

from datetime import datetime, timedelta, timezone

from news_v2.config import PriorityWeights, Settings
from news_v2.priority import (
    PriorityFeatures,
    assign_tier,
    compute_score,
    decide_priority,
    news_velocity_score,
    percentile_rank,
    recompute_cohort,
)


def test_percentile_rank_basic():
    assert percentile_rank([], 1.0) == 0.0
    # below 4, equal 1 of 5 → (4 + 0.5) / 5 * 100 == 90
    assert percentile_rank([1, 2, 3, 4, 5], 5) == 90.0
    assert percentile_rank([1, 1, 1, 1], 1) == 50.0  # all equal
    assert percentile_rank([1, 2, 3], 0) == 0.0


def _features(symbol: str, **kw) -> PriorityFeatures:
    base = dict(
        turnover=0.0,
        volatility=0.0,
        view_count_24h=0,
        watchlist_count=0,
        holding_count=0,
        search_count_24h=0,
        trading_value=0.0,
        market_cap=0.0,
        news_count_1h=0,
        news_count_24h=0,
        news_velocity=0.0,
        index_member=0,
        ai_importance=0.0,
        last_viewed=None,
        current_view_until=None,
    )
    base.update(kw)
    return PriorityFeatures(symbol=symbol, **base)


def test_compute_score_current_view_is_highest_signal():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cohort_features = [
        _features("CURRENT", current_view_until=now + timedelta(minutes=5)),
        _features("MARKET_CAP", market_cap=1e14, trading_value=1e12),
    ]
    cohort = recompute_cohort(cohort_features)
    weights = PriorityWeights()
    current = compute_score(cohort_features[0], cohort, weights)
    market_cap_only = compute_score(cohort_features[1], cohort, weights)
    assert current > market_cap_only


def test_watchlist_and_holding_beat_market_cap_fallback():
    cohort_features = [
        _features("USER", watchlist_count=1, holding_count=1),
        _features("BIG", market_cap=1e14, trading_value=1e12),
    ]
    cohort = recompute_cohort(cohort_features)
    weights = PriorityWeights()
    user = compute_score(cohort_features[0], cohort, weights)
    market = compute_score(cohort_features[1], cohort, weights)
    assert user > market


def test_news_velocity_and_trending_promote_to_hot():
    features = [_features("SPIKE", news_count_1h=6, news_count_24h=12), _features("BASE")]
    cohort = recompute_cohort(features)
    decision = decide_priority(features[0], cohort, Settings())
    assert news_velocity_score(6, 12) == 12.0
    assert decision.is_trending is True
    assert decision.queue == "hot"


def test_assign_tier_thresholds():
    cfg = Settings()
    # tiers depend on actual config thresholds
    assert assign_tier(cfg.tier1_threshold + 1, cfg) == 1
    assert assign_tier(cfg.tier2_threshold + 1, cfg) == 2
    assert assign_tier(0, cfg) == 3
