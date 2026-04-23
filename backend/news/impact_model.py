"""
Market impact estimation model.

Translates structured event information → expected price impact estimates.

Design: rule-based scoring model (interpretable baseline).
The output ImpactEstimate is versioned so a future ML model can be swapped in
without changing the downstream schema.

Impact score ∈ [-1, 1]:
  positive → expected price increase
  negative → expected price decrease
  magnitude → expected % move proxy

Confidence score ∈ [0, 1]:
  driven by credibility × (1 - uncertainty) × novelty weight

Risk alert level: none | low | medium | high
  set independently of impact direction — a positive event can still carry
  execution risk (e.g., large buyback may indicate insiders know bad news).

Look-ahead note:
  This model only uses information embedded in the article itself (event type,
  sentiment, severity, credibility, novelty). No future price data is used.
  Integration with market context (volatility, trend) uses only data available
  at publish_time of the article.
"""

from __future__ import annotations

from typing import Dict, Optional

from news.schemas import (
    ExtractedEvent,
    ImpactEstimate,
    ImpactDirection,
    RiskAlertLevel,
    Horizon,
    NewsSignalRecord,
    SignalType,
    SignalDirection,
    NormalizedArticle,
    ArticleSymbolMap,
)

# ─── Event type → base impact direction and magnitude ─────────────────────────
# (impact_direction, base_impact_magnitude, horizon_multiplier)
_EVENT_IMPACT_TABLE: Dict[str, tuple] = {
    "earnings_beat":      ("up",      0.6,  1.0),
    "earnings_miss":      ("down",    0.6,  1.0),
    "guidance_up":        ("up",      0.5,  0.8),
    "guidance_down":      ("down",    0.5,  0.8),
    "large_contract":     ("up",      0.5,  0.9),
    "share_buyback":      ("up",      0.4,  0.7),
    "rights_offering":    ("down",    0.45, 0.9),
    "convertible_bond":   ("down",    0.3,  0.7),
    "ceo_change":         ("neutral", 0.2,  0.5),
    "regulatory_probe":   ("down",    0.65, 0.9),
    "lawsuit_loss":       ("down",    0.5,  0.9),
    "lawsuit_win":        ("up",      0.4,  0.9),
    "factory_fire":       ("down",    0.7,  1.0),
    "product_launch":     ("up",      0.35, 0.6),
    "product_failure":    ("down",    0.5,  0.9),
    "dividend_increase":  ("up",      0.3,  0.5),
    "dividend_cut":       ("down",    0.4,  0.8),
    "mna":                ("up",      0.4,  0.7),
    "delisting_risk":     ("down",    0.9,  1.0),
    "accounting_issue":   ("down",    0.85, 1.0),
    "analyst_upgrade":    ("up",      0.3,  0.7),
    "analyst_downgrade":  ("down",    0.3,  0.7),
    "macro_rate":         ("neutral", 0.25, 0.6),
    "policy_change":      ("neutral", 0.2,  0.6),
    "sector_tailwind":    ("up",      0.25, 0.5),
    "sector_headwind":    ("down",    0.25, 0.5),
    "general_positive":   ("up",      0.15, 0.4),
    "general_negative":   ("down",    0.15, 0.4),
    "general_neutral":    ("neutral", 0.05, 0.3),
}

# Risk alert thresholds (based on final impact_score magnitude)
_RISK_HIGH_THRESHOLD = 0.55
_RISK_MEDIUM_THRESHOLD = 0.35
_RISK_LOW_THRESHOLD = 0.15

# High-risk event types that trigger alert regardless of score magnitude
_HIGH_RISK_EVENTS = {
    "delisting_risk", "accounting_issue", "factory_fire", "regulatory_probe",
}
_MEDIUM_RISK_EVENTS = {
    "rights_offering", "lawsuit_loss", "earnings_miss", "product_failure",
    "dividend_cut", "convertible_bond",
}

# Expected alpha proxy (% move): scaled by impact_score
_ALPHA_1D_SCALE = 0.05   # 5% max expected 1-day alpha
_ALPHA_5D_SCALE = 0.08   # 8% max expected 5-day alpha


def _determine_risk_alert(
    event: ExtractedEvent,
    impact_score: float,
) -> RiskAlertLevel:
    abs_score = abs(impact_score)

    if event.event_type in _HIGH_RISK_EVENTS:
        return "high"
    if event.event_type in _MEDIUM_RISK_EVENTS and abs_score >= _RISK_LOW_THRESHOLD:
        return "medium"
    if abs_score >= _RISK_HIGH_THRESHOLD:
        return "high"
    if abs_score >= _RISK_MEDIUM_THRESHOLD:
        return "medium"
    if abs_score >= _RISK_LOW_THRESHOLD:
        return "low"
    return "none"


def estimate_impact(
    article: NormalizedArticle,
    event: ExtractedEvent,
    symbol: Optional[str] = None,
) -> ImpactEstimate:
    """
    Estimate expected market impact from extracted event data.

    All inputs are available at article.published_at — no look-ahead.
    """
    row = _EVENT_IMPACT_TABLE.get(event.event_type, ("neutral", 0.1, 0.3))
    base_direction, base_magnitude, horizon_mult = row

    # Override direction based on sentiment if event type is sentiment-agnostic
    if base_direction == "neutral" and event.sentiment != "neutral":
        base_direction = "up" if event.sentiment == "positive" else "down"

    # Compute raw impact score: magnitude × severity × horizon_multiplier
    raw_score = base_magnitude * event.severity * horizon_mult

    # Apply credibility and novelty as discount factors
    credibility_weight = 0.5 + 0.5 * event.credibility
    novelty_weight = 0.4 + 0.6 * event.novelty
    adjusted_score = raw_score * credibility_weight * novelty_weight

    # Clip to [-1, 1] with directional sign
    signed_score = adjusted_score if base_direction == "up" else (
        -adjusted_score if base_direction == "down" else 0.0
    )
    impact_score = max(-1.0, min(1.0, signed_score))

    # Confidence: how sure we are about the direction
    confidence = (event.credibility * 0.4 + event.novelty * 0.3 + event.severity * 0.3)
    confidence = round(min(1.0, confidence), 3)

    # Expected alpha proxies (not calibrated; scale from score)
    abs_score = abs(impact_score)
    expected_alpha_1d = round(impact_score * _ALPHA_1D_SCALE, 4)
    expected_alpha_5d = round(impact_score * _ALPHA_5D_SCALE, 4)

    # Volatility jump risk: high-severity negative events spike vol
    vol_jump = abs_score * event.severity * 0.8
    if event.risk_flags:
        vol_jump = min(1.0, vol_jump + 0.1 * len(event.risk_flags))

    risk_alert = _determine_risk_alert(event, impact_score)

    final_direction: ImpactDirection = "neutral" if abs(impact_score) < 0.05 else (
        "up" if impact_score > 0 else "down"
    )

    return ImpactEstimate(
        article_id=article.id,
        symbol=symbol,
        impact_direction=final_direction,
        impact_score=round(impact_score, 4),
        confidence_score=confidence,
        expected_horizon=event.expected_horizon,
        expected_alpha_1d=expected_alpha_1d,
        expected_alpha_5d=expected_alpha_5d,
        volatility_jump_risk=round(vol_jump, 3),
        risk_alert_level=risk_alert,
        model_version="v1-rules",
    )


def build_signals(
    article: NormalizedArticle,
    event: ExtractedEvent,
    impact: ImpactEstimate,
    symbol_maps: list,
) -> list:
    """
    Build NewsSignalRecord list from impact estimate.

    valid_from = article.published_at (strict look-ahead enforcement).
    One signal record per (symbol, signal_type) pair.
    """
    from datetime import timedelta
    signals = []

    _horizon_days: Dict[str, int] = {
        "intraday": 0, "1d": 1, "5d": 5, "1m": 22, "3m": 66,
    }
    hold_days = _horizon_days.get(impact.expected_horizon, 1)
    valid_until = (
        article.published_at + timedelta(days=hold_days) if hold_days > 0 else None
    )

    direction: SignalDirection = (
        "long" if impact.impact_direction == "up"
        else "short" if impact.impact_direction == "down"
        else "neutral"
    )

    for sym_map in symbol_maps:
        symbol = sym_map.symbol
        if symbol.startswith("__"):
            continue   # Skip pseudo-symbols (sector/macro placeholders)

        for sig_type, value in [
            ("news_event", event.severity if event.sentiment == "positive" else -event.severity),
            ("news_sentiment", 1.0 if event.sentiment == "positive" else (-1.0 if event.sentiment == "negative" else 0.0)),
            ("news_risk_alert", 1.0 if impact.risk_alert_level in ("high", "medium") else 0.0),
            ("news_alpha_score", impact.impact_score),
        ]:
            signals.append(
                NewsSignalRecord(
                    article_id=article.id,
                    symbol=symbol,
                    signal_type=sig_type,
                    value=round(float(value), 4),
                    direction=direction,
                    confidence=impact.confidence_score,
                    valid_from=article.published_at,
                    valid_until=valid_until,
                    metadata={
                        "event_type": event.event_type,
                        "risk_alert": impact.risk_alert_level,
                        "source": article.source,
                    },
                    model_version="v1-rules",
                )
            )

    return signals
