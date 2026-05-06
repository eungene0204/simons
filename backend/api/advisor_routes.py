"""
FastAPI routes for the Context-aware Strategy Advisor Agent.

POST /advisor/review   — full strategy review
GET  /advisor/health   — liveness check

The agent instance is created once at module import and reused across requests.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from advisor.agent import StrategyAdvisorAgent
from advisor.memory_repository import load_advisor_memory, save_advisor_experience
from advisor.news_enrichment import build_news_context_from_strategy
from advisor.schemas import AdvisorRequest, AdvisorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/advisor", tags=["advisor"])

_agent = StrategyAdvisorAgent()


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/review", response_model=AdvisorResponse)
async def review_strategy(req: AdvisorRequest) -> AdvisorResponse:
    """
    전략 리뷰 요청.

    - parsed_strategy: NLStrategyParser가 반환한 dict (필수)
    - backtest_result: 백테스트 결과 요약 (선택)
    - news_context:    News Impact AI Agent 출력 (선택)
    """
    try:
        effective_req = req
        if not req.news_context:
            news_context = build_news_context_from_strategy(req.parsed_strategy)
            if news_context:
                effective_req = req.model_copy(update={"news_context": news_context})
        if (
            effective_req.memory_strategy_cases is None
            and effective_req.memory_experiences is None
        ):
            strategy_cases, experiences = load_advisor_memory()
            if strategy_cases or experiences:
                effective_req = effective_req.model_copy(
                    update={
                        "memory_strategy_cases": strategy_cases,
                        "memory_experiences": experiences,
                    }
                )
        response = _agent.review(effective_req)
        save_advisor_experience(effective_req, response)
        return response
    except Exception as exc:
        logger.exception("advisor.review failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "agent": "StrategyAdvisorAgent"}
