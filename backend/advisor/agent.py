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
from .experiment_learning import ExperimentLearningProvider, build_experiment_learning_advice
from .news_adapter import NormalizedNewsSignals, adapt_news, build_news_summary
from .schemas import AdviceItem, AdvisorRequest, AdvisorResponse, NewsAnalysis
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

    def __init__(self, learning_provider: Optional[ExperimentLearningProvider] = None) -> None:
        self._diagnoser = StrategyDiagnoser()
        self._suggestion = SuggestionEngine()
        self._learning = learning_provider or ExperimentLearningProvider()

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
        issue_codes = {issue.code for issue in issues}

        # ── Step 4.5: attach prompt-experiment evidence ────────────────────
        learning_insight = self._learning.build_insight(req.parsed_strategy, req.user_prompt)
        learning_body = build_experiment_learning_advice(learning_insight)
        high_news_risk = "HIGH_NEWS_RISK_ALERT" in issue_codes and news.max_risk_level == "high"
        if learning_body and not high_news_risk:
            advice.insert(0, AdviceItem(
                severity="medium" if learning_insight.get("confidence") != "low" else "low",
                title="전략 실험 근거 기반 개선",
                body=learning_body,
            ))
        elif high_news_risk:
            learning_insight.setdefault("warnings", []).insert(
                0,
                "뉴스 리스크가 high라 실험 근거보다 뉴스 리스크 조언을 우선합니다.",
            )
            advice = self._prioritize_news_advice(advice)

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
            strategy_experiment_learning=learning_insight,
            suggested_experiments=experiments,
            ai_model_recommendation=ai_rec,
        )

    @staticmethod
    def _prioritize_news_advice(advice: list[AdviceItem]) -> list[AdviceItem]:
        risk_items = [item for item in advice if "뉴스 리스크" in item.title or "뉴스 리스크" in item.body]
        other_news_items = [
            item
            for item in advice
            if item not in risk_items and ("뉴스" in item.title or "뉴스" in item.body)
        ]
        other_items = [item for item in advice if item not in risk_items and item not in other_news_items]
        return risk_items + other_news_items + other_items
