"""
Context-aware Strategy Advisor Agent — Orchestrator.

Pipeline:
  1. news_adapter  — normalize raw NewsContext list
  2. diagnoser     — run all rules → Issue list
  3. scoring       — compute strategy_score, risk_score, overfit_risk
  4. suggestion    — build Recommendations, experiments, ai_rec
  5. assemble      — return AdvisorResponse

No LLM is called in Phase 1 (MVP).  The architecture is designed so that
a Phase 2 LLM explanation layer can be inserted after step 2 without
touching the rule or scoring modules.
"""

from __future__ import annotations

import logging
from typing import Optional

from .diagnoser import StrategyDiagnoser
from .news_adapter import NormalizedNewsSignals, adapt_news, build_news_summary
from .schemas import AdvisorRequest, AdvisorResponse, NewsAnalysis
from .scoring import compute_overfit_risk, compute_risk_score, compute_strategy_score
from .suggestion_engine import SuggestionEngine

logger = logging.getLogger(__name__)


class StrategyAdvisorAgent:
    """
    Stateless agent.  Instantiate once at app startup and reuse.

    Usage:
        agent = StrategyAdvisorAgent()
        response = agent.review(request)
    """

    def __init__(self) -> None:
        self._diagnoser = StrategyDiagnoser()
        self._suggestion = SuggestionEngine()

    def review(self, req: AdvisorRequest) -> AdvisorResponse:
        # ── Step 1: normalize news ─────────────────────────────────────────
        news: NormalizedNewsSignals = adapt_news(req.news_context)

        # ── Step 2: diagnose ───────────────────────────────────────────────
        issues = self._diagnoser.diagnose(req, news)
        ctx = self._diagnoser.build_context(req, news)

        # ── Step 3: score ──────────────────────────────────────────────────
        strategy_score = compute_strategy_score(issues)
        risk_score = compute_risk_score(issues, ctx)
        overfit_risk = compute_overfit_risk(issues, ctx)

        # ── Step 4: suggest ────────────────────────────────────────────────
        advice, experiments, ai_rec = self._suggestion.generate(issues, ctx, news, overfit_risk)

        # ── Step 5: news analysis summary ─────────────────────────────────
        news_analysis: Optional[NewsAnalysis] = None
        if news.available:
            news_analysis = NewsAnalysis(
                summary=build_news_summary(news),
                risk_level=news.overall_risk_level,
                key_events=news.key_events,
            )

        logger.info(
            "advisor.review done | score=%.1f risk=%.1f overfit=%s advice=%d",
            strategy_score, risk_score, overfit_risk, len(advice),
        )

        return AdvisorResponse(
            strategy_score=strategy_score,
            risk_score=risk_score,
            overfit_risk=overfit_risk,
            advice=advice,
            news_analysis=news_analysis,
            suggested_experiments=experiments,
            ai_model_recommendation=ai_rec,
        )
