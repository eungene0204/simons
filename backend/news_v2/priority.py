"""
Priority scoring + tier assignment for news_v2.

Inputs (from PriorityScore row): turnover, volatility, view_count_24h,
watchlist_count, search_count_24h, ai_importance.
Output: float score, plus a tier in {1, 2, 3}.

We use percentile-rank normalization per input across the full cohort so the
score stays bounded (0~100) regardless of absolute scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from news_v2.config import PriorityWeights, Settings, get_settings


@dataclass
class PriorityFeatures:
    symbol: str
    turnover: float
    volatility: float
    view_count_24h: int
    watchlist_count: int
    search_count_24h: int
    ai_importance: float


def percentile_rank(values: list[float], target: float) -> float:
    """0~100 percentile rank of `target` within `values`."""
    if not values:
        return 0.0
    below = sum(1 for v in values if v < target)
    equal = sum(1 for v in values if v == target)
    return (below + 0.5 * equal) / len(values) * 100.0


def compute_score(feature: PriorityFeatures, cohort: dict, weights: PriorityWeights) -> float:
    """`cohort` holds per-feature lists for percentile-rank normalization."""
    score = (
        weights.turnover * percentile_rank(cohort["turnover"], feature.turnover)
        + weights.volatility * percentile_rank(cohort["volatility"], feature.volatility)
        + weights.view_count * percentile_rank(cohort["view_count_24h"], feature.view_count_24h)
        + weights.watchlist * percentile_rank(cohort["watchlist_count"], feature.watchlist_count)
        + weights.search_count * percentile_rank(cohort["search_count_24h"], feature.search_count_24h)
        + weights.ai_importance * 100.0 * feature.ai_importance  # already 0~1
    )
    return float(score)


def assign_tier(score: float, cfg: Settings) -> int:
    if score >= cfg.tier1_threshold:
        return 1
    if score >= cfg.tier2_threshold:
        return 2
    return 3


def recompute_cohort(features: Iterable[PriorityFeatures]) -> dict:
    items = list(features)
    return {
        "turnover": [f.turnover for f in items],
        "volatility": [f.volatility for f in items],
        "view_count_24h": [float(f.view_count_24h) for f in items],
        "watchlist_count": [float(f.watchlist_count) for f in items],
        "search_count_24h": [float(f.search_count_24h) for f in items],
    }


def rescale_with_thresholds(score: float, view_count_24h: int) -> float:
    """The score is 0~100; multiply for human-readable rankings on the API side."""
    # Each view adds the view_bonus directly to the persisted score in the repo;
    # this helper just exposes a stable "effective score" callers can compare.
    return score * 10.0 + view_count_24h
