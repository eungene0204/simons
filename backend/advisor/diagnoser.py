"""
Strategy Advisor — Rule-based Diagnoser.

Converts AdvisorRequest into a RuleContext and runs all registered rules.
Pure deterministic logic — no LLM calls.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .news_adapter import NormalizedNewsSignals
from .rules import ALL_RULES, RuleContext
from .schemas import AdvisorRequest, Issue


_UNIVERSE_SIZE: Dict[str, int] = {
    "KOSPI200": 200,
    "KOSPI": 838,
    "KOSDAQ": 1781,
}

_LIQUIDITY_METRICS = {"trading_value"}


def _build_rule_context(
    req: AdvisorRequest,
    news: NormalizedNewsSignals,
) -> RuleContext:
    ps: Dict[str, Any] = req.parsed_strategy
    bt = req.backtest_result

    # ── universe size estimate ──────────────────────────────────────────────
    universe: List[str] = ps.get("universe") or ["KOSPI200"]
    universe_size = sum(_UNIVERSE_SIZE.get(u, 200) for u in universe)

    # ── filter analysis ─────────────────────────────────────────────────────
    filters: List[Dict] = ps.get("fundamental_filters") or []
    has_liquidity = any(f.get("metric") in _LIQUIDITY_METRICS for f in filters)
    has_fundamental = len(filters) > 0

    # ── entry / exit signals ────────────────────────────────────────────────
    entry_signals: List[Dict] = ps.get("entry_signals") or []
    exit_signals: List[Dict] = ps.get("exit_signals") or []
    has_ai = any(
        s.get("indicator") in ("ai_model", "ai_drop_model")
        for s in (entry_signals + exit_signals)
    )

    # ── risk management ─────────────────────────────────────────────────────
    sl_pct: Optional[float] = ps.get("stop_loss_pct")
    tp_pct: Optional[float] = ps.get("take_profit_pct")
    ts_pct: Optional[float] = ps.get("trailing_stop_pct")
    hold_days: Optional[int] = ps.get("hold_period_days")

    return RuleContext(
        # structure
        has_exit_signals=len(exit_signals) > 0,
        filter_count=len(filters),
        has_liquidity_filter=has_liquidity,
        has_fundamental_filters=has_fundamental,
        entry_signal_count=len(entry_signals),
        has_ai_signal=has_ai,
        max_positions=ps.get("max_positions"),
        universe_size_estimate=universe_size,
        hold_period_days=hold_days,
        initial_capital=ps.get("initial_capital"),
        # risk
        has_stop_loss=sl_pct is not None,
        stop_loss_pct=sl_pct,
        has_take_profit=tp_pct is not None,
        take_profit_pct=tp_pct,
        has_trailing_stop=ts_pct is not None,
        # backtest
        backtest_available=bt is not None,
        cagr=bt.cagr if bt else None,
        mdd=bt.mdd if bt else None,
        sharpe=bt.sharpe if bt else None,
        profit_factor=bt.profit_factor if bt else None,
        trade_count=bt.trade_count if bt else None,
        win_rate=bt.win_rate if bt else None,
        # news
        news_available=news.available,
        news_negative_ratio=news.negative_ratio,
        news_positive_ratio=news.positive_ratio,
        news_weighted_impact=news.weighted_impact,
        news_max_risk_level=news.max_risk_level,
        news_event_types=news.event_types,
        news_high_confidence_negative=news.high_confidence_negative,
    )


class StrategyDiagnoser:
    """
    Runs all registered rules against a strategy request and returns
    a sorted list of Issues (high → medium → low).
    """

    _SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

    def diagnose(
        self,
        req: AdvisorRequest,
        news: NormalizedNewsSignals,
    ) -> List[Issue]:
        ctx = _build_rule_context(req, news)
        issues: List[Issue] = []
        for rule_fn in ALL_RULES:
            issue = rule_fn(ctx)
            if issue is not None:
                issues.append(issue)

        issues.sort(key=lambda i: self._SEVERITY_ORDER.get(i.severity, 9))
        return issues

    def build_context(
        self,
        req: AdvisorRequest,
        news: NormalizedNewsSignals,
    ) -> RuleContext:
        """Expose context so scoring / suggestion modules can reuse it."""
        return _build_rule_context(req, news)
