"""
Strategy Advisor — News Adapter.

Converts raw NewsContext list (from News Impact AI Agent) into
flat, normalized signals that the RuleContext and scoring layer can consume.
No LLM calls here — pure deterministic aggregation.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Optional

from .schemas import NewsContext


class NormalizedNewsSignals:
    """Flat aggregated view of all news signals across all symbols."""

    def __init__(self) -> None:
        self.negative_ratio: float = 0.0        # 0-1
        self.positive_ratio: float = 0.0        # 0-1
        self.weighted_impact: float = 0.0       # signed, -1 to +1
        self.max_risk_level: str = "none"       # none/low/medium/high
        self.event_types: List[str] = []
        self.high_confidence_negative: int = 0  # count
        self.symbol_summaries: List[str] = []
        self.key_events: List[str] = []
        self.available: bool = False

    @property
    def overall_risk_level(self) -> str:
        """Translate max_risk_level → low/medium/high (drop 'none')."""
        if self.max_risk_level in ("medium", "high"):
            return self.max_risk_level
        if self.negative_ratio >= 0.5 or self.weighted_impact < -0.3:
            return "medium"
        return "low"


_RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}


def adapt_news(news_contexts: Optional[List[NewsContext]]) -> NormalizedNewsSignals:
    """
    Aggregate a list of per-symbol NewsContext into a single NormalizedNewsSignals.

    Weight formula per article:  weight = impact_score × confidence_score
    Positive/negative ratio is computed over articles that are not neutral.
    """
    out = NormalizedNewsSignals()
    if not news_contexts:
        return out

    out.available = True

    total_weighted_pos = 0.0
    total_weighted_neg = 0.0
    total_weight = 0.0
    event_counter: Counter = Counter()

    for ctx in news_contexts:
        # track max risk level across symbols
        if _RISK_ORDER.get(ctx.risk_alert_level, 0) > _RISK_ORDER.get(out.max_risk_level, 0):
            out.max_risk_level = ctx.risk_alert_level

        for art in ctx.articles:
            w = abs(art.impact_score) * art.confidence_score  # 0-1 weight
            if w == 0.0:
                w = art.confidence_score * 0.2  # still counts, just low weight

            if art.sentiment == "positive":
                total_weighted_pos += w
            elif art.sentiment == "negative":
                total_weighted_neg += w
                if art.confidence_score >= 0.7:
                    out.high_confidence_negative += 1

            total_weight += w
            out.weighted_impact += art.impact_score * art.confidence_score
            event_counter[art.event_type] += 1

    if total_weight > 0:
        out.negative_ratio = total_weighted_neg / total_weight
        out.positive_ratio = total_weighted_pos / total_weight
        out.weighted_impact /= total_weight  # normalize to -1..+1

    out.event_types = list(event_counter.keys())

    # build key events: top-3 most frequent non-neutral event types
    out.key_events = [
        f"{evt} ({cnt}건)"
        for evt, cnt in event_counter.most_common(5)
        if evt not in ("general_neutral",)
    ][:3]

    # per-symbol summary lines
    for ctx in news_contexts:
        neg_count = sum(1 for a in ctx.articles if a.sentiment == "negative")
        pos_count = sum(1 for a in ctx.articles if a.sentiment == "positive")
        total = len(ctx.articles)
        if total > 0:
            out.symbol_summaries.append(
                f"{ctx.symbol}: 기사 {total}건 (긍정 {pos_count}, 부정 {neg_count}), "
                f"alpha={ctx.latest_alpha:+.3f}, risk={ctx.risk_alert_level}"
            )

    return out


def build_news_summary(signals: NormalizedNewsSignals) -> str:
    """Generate a Korean-language summary string for AdvisorResponse.news_analysis."""
    if not signals.available:
        return "뉴스 데이터가 제공되지 않았습니다."

    parts: List[str] = []

    if signals.negative_ratio >= 0.6:
        parts.append(f"부정 뉴스 비중 {signals.negative_ratio*100:.0f}%로 높습니다.")
    elif signals.positive_ratio >= 0.6:
        parts.append(f"긍정 뉴스 비중 {signals.positive_ratio*100:.0f}%로 우호적입니다.")
    else:
        parts.append("긍정/부정 뉴스가 혼재합니다.")

    if signals.max_risk_level == "high":
        parts.append("하나 이상의 종목에서 심각한 리스크 경보가 발생했습니다.")
    elif signals.max_risk_level == "medium":
        parts.append("일부 종목에서 중간 수준의 리스크가 감지됩니다.")

    if signals.weighted_impact < -0.3:
        parts.append(f"가중 임팩트 점수 {signals.weighted_impact:+.2f}로 하방 압력이 큽니다.")
    elif signals.weighted_impact > 0.3:
        parts.append(f"가중 임팩트 점수 {signals.weighted_impact:+.2f}로 상방 모멘텀이 감지됩니다.")

    if signals.symbol_summaries:
        parts.append("종목별 요약: " + " | ".join(signals.symbol_summaries[:3]))

    return " ".join(parts)
