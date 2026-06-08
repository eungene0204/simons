"""Priority scoring + queue assignment for news_v2.

The engine deliberately prioritizes user demand over market-size data:
current views > watchlists/holdings > recent views/searches > market/news
signals. Market cap is a weak fallback signal only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from news_v2.config import PriorityWeights, Settings, get_settings

HOT = "hot"
WARM = "warm"
COLD = "cold"
QUEUES = {HOT, WARM, COLD}

EVENT_STOCK_VIEW = "stock_view"
EVENT_CURRENT_VIEW = "current_view"
EVENT_WATCHLIST_ADD = "watchlist_add"
EVENT_WATCHLIST_REMOVE = "watchlist_remove"
EVENT_HOLDING_BUY = "holding_buy"
EVENT_HOLDING_SELL = "holding_sell"
EVENT_STOCK_SEARCH = "stock_search"


@dataclass
class PriorityFeatures:
    symbol: str
    turnover: float
    volatility: float
    view_count_24h: int
    watchlist_count: int
    holding_count: int
    search_count_24h: int
    trading_value: float
    market_cap: float
    news_count_1h: int
    news_count_24h: int
    news_velocity: float
    index_member: int
    ai_importance: float
    last_viewed: datetime | None = None
    current_view_until: datetime | None = None


@dataclass(frozen=True)
class PriorityDecision:
    symbol: str
    score: float
    queue: str
    tier: int
    is_trending: bool
    news_velocity: float
    reason: str


def percentile_rank(values: list[float], target: float) -> float:
    """0~100 percentile rank of `target` within `values`."""
    if not values:
        return 0.0
    below = sum(1 for v in values if v < target)
    equal = sum(1 for v in values if v == target)
    return (below + 0.5 * equal) / len(values) * 100.0


def compute_score(feature: PriorityFeatures, cohort: dict, weights: PriorityWeights) -> float:
    """`cohort` holds per-feature lists for percentile-rank normalization."""
    current_view = 1.0 if _is_currently_viewed(feature) else 0.0
    score = current_view * weights.current_view
    score += min(feature.watchlist_count, 10) * weights.watchlist
    score += min(feature.holding_count, 10) * weights.holding
    score += min(feature.view_count_24h, 100) * weights.view_count
    score += min(feature.search_count_24h, 30) * weights.search_count
    score += _pct(cohort, "trading_value", feature.trading_value) / 100.0 * weights.turnover
    score += _pct(cohort, "turnover", feature.turnover) / 100.0 * weights.turnover
    score += min(max(feature.news_velocity, 0.0), 8.0) / 8.0 * weights.news_velocity
    score += min(max(feature.ai_importance, 0.0), 1.0) * weights.ai_importance
    score += _pct(cohort, "volatility", feature.volatility) / 100.0 * weights.volatility
    score += _pct(cohort, "market_cap", feature.market_cap) / 100.0 * weights.market_cap
    if feature.index_member:
        score += weights.index_member
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
        "holding_count": [float(f.holding_count) for f in items],
        "search_count_24h": [float(f.search_count_24h) for f in items],
        "trading_value": [float(f.trading_value) for f in items],
        "market_cap": [float(f.market_cap) for f in items],
        "news_velocity": [float(f.news_velocity) for f in items],
    }


def news_velocity_score(news_count_1h: int, news_count_24h: int) -> float:
    """Recent 1h count divided by the hourly average of the previous 24h."""
    if news_count_1h <= 0:
        return 0.0
    hourly_average = max(news_count_24h / 24.0, 0.25)
    return round(news_count_1h / hourly_average, 4)


def is_trending(feature: PriorityFeatures, cohort: dict) -> bool:
    return any(
        [
            feature.view_count_24h >= 20 and _pct(cohort, "view_count_24h", feature.view_count_24h) >= 90,
            feature.news_velocity >= 3.0 and feature.news_count_1h >= 2,
            feature.trading_value > 0 and _pct(cohort, "trading_value", feature.trading_value) >= 95,
            feature.watchlist_count >= 3 and _pct(cohort, "watchlist_count", feature.watchlist_count) >= 90,
        ]
    )


def decide_priority(
    feature: PriorityFeatures,
    cohort: dict,
    cfg: Settings | None = None,
) -> PriorityDecision:
    cfg = cfg or get_settings()
    velocity = news_velocity_score(feature.news_count_1h, feature.news_count_24h)
    enriched = PriorityFeatures(**{**feature.__dict__, "news_velocity": velocity})
    score = compute_score(enriched, cohort, cfg.priority_weights)
    trending = is_trending(enriched, cohort)

    if (
        _is_currently_viewed(enriched)
        or enriched.watchlist_count > 0
        or enriched.holding_count > 0
        or trending
        or score >= cfg.tier1_threshold
    ):
        queue = HOT
        tier = 1
    elif (
        score >= cfg.tier2_threshold
        or enriched.trading_value > 0
        or enriched.market_cap > 0
        or enriched.index_member
    ):
        queue = WARM
        tier = 2
    else:
        queue = COLD
        tier = 3

    return PriorityDecision(
        symbol=enriched.symbol,
        score=round(score, 4),
        queue=queue,
        tier=tier,
        is_trending=trending,
        news_velocity=velocity,
        reason=_reason(enriched, trending),
    )


def rescale_with_thresholds(score: float, view_count_24h: int) -> float:
    return score + view_count_24h


def _pct(cohort: dict, key: str, value: float) -> float:
    return percentile_rank(cohort.get(key, []), float(value or 0.0))


def _is_currently_viewed(feature: PriorityFeatures) -> bool:
    if feature.current_view_until is None:
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return feature.current_view_until.replace(tzinfo=None) >= now


def _reason(feature: PriorityFeatures, trending: bool) -> str:
    reasons: list[str] = []
    if _is_currently_viewed(feature):
        reasons.append("current_view")
    if feature.watchlist_count > 0:
        reasons.append("watchlist")
    if feature.holding_count > 0:
        reasons.append("holding")
    if feature.view_count_24h > 0:
        reasons.append("recent_view")
    if feature.search_count_24h > 0:
        reasons.append("search")
    if feature.news_velocity >= 3.0:
        reasons.append("news_velocity")
    if trending:
        reasons.append("trending")
    if feature.index_member:
        reasons.append("index_member")
    if feature.trading_value > 0:
        reasons.append("trading_value")
    if feature.market_cap > 0:
        reasons.append("market_cap_fallback")
    return ",".join(reasons) or "cold_rotation"
