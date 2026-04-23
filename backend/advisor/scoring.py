"""
Strategy Advisor — Scoring Engine.

Computes strategy_score (quality), risk_score, and overfit_risk
from the RuleContext and diagnosed Issues.

Scores are on 0–100 scale.  strategy_score starts at 100 and deducts
penalty points for each active issue.  risk_score accumulates risk signals.
"""

from __future__ import annotations

from typing import List

from .rules import RuleContext
from .schemas import Issue, OverfitRisk


# ─── Issue penalty table ──────────────────────────────────────────────────────

_PENALTY: dict = {
    "MISSING_EXIT_RULE": 25,
    "NO_STOP_LOSS": 20,
    "TOO_MANY_FILTERS": 10,
    "NO_LIQUIDITY_FILTER": 8,
    "NO_ENTRY_SIGNALS": 25,
    "TOO_TIGHT_STOP": 5,
    "POSITION_OVEREXPOSED": 8,
    "LOW_TRADE_COUNT": 15,
    "HIGH_MDD": 12,
    "OVERFIT_SUSPECT": 18,
    "LOW_SHARPE": 8,
    "NEGATIVE_NEWS_CLUSTER": 10,
    "HIGH_NEWS_RISK_ALERT": 12,
    "EVENT_DRIVEN_VOLATILITY": 6,
    "VALUE_TRAP_RISK": 8,
}

# ─── Risk contribution table ──────────────────────────────────────────────────

_RISK_CONTRIBUTION: dict = {
    "NO_STOP_LOSS": 25,
    "MISSING_EXIT_RULE": 20,
    "HIGH_MDD": 18,
    "HIGH_NEWS_RISK_ALERT": 15,
    "NEGATIVE_NEWS_CLUSTER": 12,
    "OVERFIT_SUSPECT": 10,
    "POSITION_OVEREXPOSED": 10,
    "EVENT_DRIVEN_VOLATILITY": 8,
    "TOO_TIGHT_STOP": 6,
    "VALUE_TRAP_RISK": 8,
    "LOW_TRADE_COUNT": 5,
    "LOW_SHARPE": 5,
}


def compute_strategy_score(issues: List[Issue]) -> float:
    """Start from 100 and deduct per-issue penalties. Floor at 0."""
    score = 100.0
    for issue in issues:
        score -= _PENALTY.get(issue.code, 5)
    return max(0.0, min(100.0, round(score, 1)))


def compute_risk_score(issues: List[Issue], ctx: RuleContext) -> float:
    """Accumulate risk contributions. Floor 0, cap 100."""
    risk = 0.0
    for issue in issues:
        risk += _RISK_CONTRIBUTION.get(issue.code, 3)

    # news sentiment pressure adds extra risk
    if ctx.news_available:
        if ctx.news_negative_ratio >= 0.7:
            risk += 10
        elif ctx.news_negative_ratio >= 0.5:
            risk += 5
        if ctx.news_weighted_impact < -0.4:
            risk += 8

    return max(0.0, min(100.0, round(risk, 1)))


def compute_overfit_risk(issues: List[Issue], ctx: RuleContext) -> OverfitRisk:
    """
    Heuristic overfit risk classifier.

    high  → OVERFIT_SUSPECT issue exists OR (CAGR > 40% AND trades < 50)
    medium → many filters OR low trade count
    low   → otherwise
    """
    issue_codes = {i.code for i in issues}

    if "OVERFIT_SUSPECT" in issue_codes:
        return "high"

    if ctx.backtest_available:
        high_cagr = ctx.cagr is not None and ctx.cagr > 0.35
        low_trades = ctx.trade_count is not None and ctx.trade_count < 50
        if high_cagr and low_trades:
            return "high"

    if ctx.filter_count >= 4 or ("LOW_TRADE_COUNT" in issue_codes):
        return "medium"

    return "low"
