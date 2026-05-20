"""Tests for news_v2.priority — score computation + tier assignment."""

from news_v2.config import PriorityWeights, Settings
from news_v2.priority import (
    PriorityFeatures,
    assign_tier,
    compute_score,
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
        search_count_24h=0,
        ai_importance=0.0,
    )
    base.update(kw)
    return PriorityFeatures(symbol=symbol, **base)


def test_compute_score_hot_stock_higher_than_cold():
    cohort_features = [
        _features("HOT", turnover=1e10, view_count_24h=500, watchlist_count=50),
        _features("WARM", turnover=1e8, view_count_24h=20),
        _features("COLD"),
    ]
    cohort = recompute_cohort(cohort_features)
    weights = PriorityWeights()
    hot = compute_score(cohort_features[0], cohort, weights)
    cold = compute_score(cohort_features[2], cohort, weights)
    assert hot > cold
    assert 0 <= cold <= 100
    assert 0 <= hot <= 100


def test_compute_score_ai_importance_pure_signal():
    cohort_features = [_features("X", ai_importance=1.0), _features("Y", ai_importance=0.0)]
    cohort = recompute_cohort(cohort_features)
    weights = PriorityWeights()
    s_x = compute_score(cohort_features[0], cohort, weights)
    s_y = compute_score(cohort_features[1], cohort, weights)
    assert s_x > s_y


def test_assign_tier_thresholds():
    cfg = Settings()
    # tiers depend on actual config thresholds
    assert assign_tier(cfg.tier1_threshold + 1, cfg) == 1
    assert assign_tier(cfg.tier2_threshold + 1, cfg) == 2
    assert assign_tier(0, cfg) == 3
