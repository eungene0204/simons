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
from pydantic import BaseModel, ValidationError

from advisor.agent import StrategyAdvisorAgent
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
        return _agent.review(req)
    except Exception as exc:
        logger.exception("advisor.review failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "agent": "StrategyAdvisorAgent"}
