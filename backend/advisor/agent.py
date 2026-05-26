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
        memory_body = self._build_memory_advice(memory_context, req.parsed_strategy)
        primary_learning_body = self._combine_learning_and_memory_advice(
            learning_body,
            memory_body,
        )
        high_news_risk = "HIGH_NEWS_RISK_ALERT" in issue_codes and news.max_risk_level == "high"
        if memory_body and not high_news_risk:
            advice.insert(0, AdviceItem(
                severity="medium" if memory_context.get("confidence") != "low" else "low",
                title="유사 전략 경험 기반 점검",
                body=memory_body,
            ))
        if primary_learning_body and not high_news_risk:
            advice.insert(0, AdviceItem(
                severity="medium" if learning_insight.get("confidence") != "low" else "low",
                title="전략 실험 근거 기반 개선",
                body=primary_learning_body,
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
    def _combine_learning_and_memory_advice(learning_body: Optional[str], memory_body: str) -> Optional[str]:
        if not learning_body:
            return None
        if not memory_body:
            return learning_body
        return (
            f"{learning_body} "
            f"유사 전략 경험까지 보면 {memory_body}"
        )

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
    @staticmethod
    def _metric_value(metrics: dict, key: str) -> Optional[float]:
        value = metrics.get(key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _improved_metrics(cls, case: dict) -> list[str]:
        before = case.get("before_metrics") or {}
        after = case.get("after_metrics") or {}
        improved: list[str] = []

        for key, label in (("cagr", "CAGR"), ("sharpe", "Sharpe")):
            before_value = cls._metric_value(before, key)
            after_value = cls._metric_value(after, key)
            if before_value is not None and after_value is not None and after_value > before_value:
                improved.append(label)

        before_mdd = cls._metric_value(before, "mdd")
        after_mdd = cls._metric_value(after, "mdd")
        if before_mdd is not None and after_mdd is not None and after_mdd > before_mdd:
            improved.append("MDD")

        return improved

    @staticmethod
    def _memory_experiment_candidates(parsed_strategy: dict) -> list[str]:
        candidates: list[str] = ["기본안 유지"]
        if parsed_strategy.get("stop_loss_pct") is None and parsed_strategy.get("trailing_stop_pct") is None:
            candidates.append("손절 8~10%")
        if parsed_strategy.get("take_profit_pct") is None and parsed_strategy.get("trailing_stop_pct") is None:
            candidates.append("익절 15%")
        if parsed_strategy.get("hold_period_days") is None:
            candidates.append("최대 보유기간 20일")

        max_positions = parsed_strategy.get("max_positions")
        if not isinstance(max_positions, (int, float)) or max_positions < 5:
            candidates.append("종목 수 5~10개 분산")

        lessons = " ".join(
            str(signal.get("indicator") or signal.get("id") or signal.get("metric") or "")
            for signal in parsed_strategy.get("entry_signals") or []
            if isinstance(signal, dict)
        )
        if "rsi" in lessons.lower():
            candidates.append("장기 추세 필터 추가")

        return candidates[:4]

    @classmethod
    def _build_memory_advice(cls, memory_context: dict, parsed_strategy: dict) -> str:
        if not memory_context:
            return ""
        retrieved = memory_context.get("retrieved_cases") or []
        if not retrieved:
            return ""

        successful_cases = [
            case
            for case in retrieved
            if case.get("advice_success") is True or cls._improved_metrics(case)
        ]
        failed_cases = [
            case
            for case in retrieved
            if case.get("advice_success") is False
        ]
        candidates = cls._memory_experiment_candidates(parsed_strategy)
        comparison_text = ", ".join(candidates)

        if successful_cases:
            improved = sorted({
                metric
                for case in successful_cases
                for metric in cls._improved_metrics(case)
            })
            metric_text = ", ".join(improved) if improved else "위험 대비 성과"
            return (
                f"유사한 과거 전략 중 {len(successful_cases)}건은 조정 후 {metric_text}가 개선되었습니다. "
                f"이번 백테스트에서는 {comparison_text}을 같은 기간과 비용 조건으로 비교하세요."
            )

        if failed_cases:
            return (
                f"유사한 과거 전략 {len(failed_cases)}건은 같은 구조의 조정에서 성과 개선이 제한적이었습니다. "
                f"이번에는 {comparison_text}을 각각 분리해서 돌리고, MDD와 Sharpe가 동시에 개선되는 조합만 후보로 남기세요."
            )

        return (
            "유사한 과거 전략은 개선 성공 여부가 아직 검증되지 않았습니다. "
            f"이번 백테스트에서는 {comparison_text}을 각각 분리해서 비교하고, 손실 축소 효과가 있는 조건만 다음 후보로 남기세요."
        )
