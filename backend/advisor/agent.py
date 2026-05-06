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

from .advice_evaluator import evaluate_advice
from .candidate_generator import generate_candidate_strategy
from .diagnoser import StrategyDiagnoser
from .experiment_learning import ExperimentLearningProvider, build_experiment_learning_advice
from .memory_retriever import retrieve_memory_context
from .news_adapter import NormalizedNewsSignals, adapt_news, build_news_summary
from .response_composer import compose_response_sections
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
        memory_context = self._build_memory_context(req)
        memory_body = self._build_memory_advice(memory_context)
        high_news_risk = "HIGH_NEWS_RISK_ALERT" in issue_codes and news.max_risk_level == "high"
        if memory_body and not high_news_risk:
            advice.insert(0, AdviceItem(
                severity="medium" if memory_context.get("confidence") != "low" else "low",
                title="유사 전략 경험 기반 점검",
                body=memory_body,
            ))
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
            if memory_context:
                memory_context.setdefault("warnings", []).insert(
                    0,
                    "뉴스 리스크가 high라 유사 전략 경험보다 뉴스 리스크 조언을 우선합니다.",
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

        candidate_strategy = generate_candidate_strategy(req.parsed_strategy, advice)
        advice_evaluation = None
        if req.backtest_result is not None and req.candidate_backtest_result is not None:
            advice_evaluation = evaluate_advice(
                req.backtest_result,
                req.candidate_backtest_result,
                req.evaluation_context or {},
            )
        response_sections = compose_response_sections(
            req=req,
            issues=issues,
            advice=advice,
            memory_context=memory_context or None,
            candidate_strategy=candidate_strategy,
            advice_evaluation=advice_evaluation,
            suggested_experiments=experiments,
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
            strategy_memory_context=memory_context or None,
            candidate_strategy=candidate_strategy,
            advice_evaluation=advice_evaluation,
            response_sections=response_sections,
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

    @staticmethod
    def _build_memory_context(req: AdvisorRequest) -> dict:
        strategy_cases = req.memory_strategy_cases or []
        experiences = req.memory_experiences or []
        if not strategy_cases and not experiences:
            return {}
        return retrieve_memory_context(
            req.user_prompt,
            req.parsed_strategy,
            strategy_cases,
            experiences,
        )

    @staticmethod
    def _build_memory_advice(memory_context: dict) -> str:
        if not memory_context:
            return ""
        retrieved = memory_context.get("retrieved_cases") or []
        if not retrieved:
            return (
                "유사 전략 검색 결과가 부족합니다. 현재 조언은 일반적인 퀀트 원칙에 기반한 낮은 신뢰도의 "
                "점검으로만 사용하고, 동일 조건의 재백테스트와 OOS 검증을 먼저 수행해야 합니다."
            )

        lessons = [case.get("lesson") for case in retrieved if case.get("lesson")]
        first_lesson = lessons[0] if lessons else "유사 전략의 개선 전후 성과를 함께 비교해야 합니다."
        return (
            f"유사 전략 {len(retrieved)}건의 Experience Memory를 확인했습니다. "
            f"재사용 가능한 핵심 교훈은 '{first_lesson}'입니다. 이 근거는 투자 추천이 아니라 "
            "현재 전략의 개선 후보를 재백테스트하기 위한 비교 기준입니다."
        )
