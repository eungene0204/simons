"""
FastAPI routes — Query Intent 분류 + 개별 종목 분석.

POST /query/classify  — 사용자 입력을 QueryIntent로 분류
POST /stock/analyze   — STOCK_ANALYSIS 질문에 대한 종목 분석(규칙 기반 추천 + LLM 설명)
POST /query/general   — GENERAL_INVESTMENT 일반 투자 지식 답변(LLM)

LLM은 coach와 동일한 공유 Qwen MLX 모델을 inference lock 안에서 사용한다.
LLM이 없으면 결정적 템플릿/폴백으로 동작한다(기능 항상 보장).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from intent.classifier import classify
from intent.schemas import IntentRequest, IntentResult
from stock_analysis import guardrails
from stock_analysis.agent import StockAnalysisAgent
from stock_analysis.schemas import (
    DISCLAIMER,
    Recommendation,
    StockAnalysisRequest,
    StockAnalysisResult,
)
from stock_analysis.symbol_resolver import find_in_text, resolve_by_symbol

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stock-analysis"])


# ─── 공유 MLX LLM 어댑터 ────────────────────────────────────────────────────────

# 서버가 이미 로드한 main 모듈만 사용한다(sys.modules). standalone/테스트에서 main을
# 새로 import해 전체 앱을 부트스트랩하는 부작용을 피한다 → 그 경우 LLM 미사용(템플릿 폴백).
def _main_module():
    return sys.modules.get("main")


def _mlx_llm(system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
    """coach와 동일한 공유 parser를 inference lock 안에서 호출한다. 없으면 빈 문자열."""
    main_mod = _main_module()
    if main_mod is None:
        return ""
    try:
        parser = getattr(main_mod, "_nl_parsers", {}).get("mlx")
        lock = getattr(main_mod, "_mlx_inference_lock", None)
        if parser is None or lock is None:
            return ""
        with lock.priority(1):
            return parser.chat(system_prompt, user_msg, max_tokens=max_tokens, temperature=0.3, top_p=0.9) or ""
    except Exception:
        logger.debug("stock-analysis MLX 호출 실패 — 폴백", exc_info=True)
        return ""


def _llm_available() -> bool:
    main_mod = _main_module()
    if main_mod is None:
        return False
    return getattr(main_mod, "_nl_parsers", {}).get("mlx") is not None


# ─── /query/classify ────────────────────────────────────────────────────────────

@router.post("/query/classify", response_model=IntentResult)
async def classify_query(req: IntentRequest) -> IntentResult:
    llm = (lambda s, u: _mlx_llm(s, u, max_tokens=40)) if _llm_available() else None
    return await asyncio.to_thread(classify, req.query, last_symbol=req.last_symbol, llm=llm)


# ─── /stock/analyze ──────────────────────────────────────────────────────────────

def _resolve_target(req: StockAnalysisRequest):
    if req.symbol:
        return resolve_by_symbol(req.symbol) or _bare(req.symbol)
    if req.query:
        found = find_in_text(req.query)
        if found:
            return found[0]
    if req.last_symbol:
        return resolve_by_symbol(req.last_symbol) or _bare(req.last_symbol)
    return None


def _bare(symbol: str):
    from stock_analysis.symbol_resolver import StockRef
    return StockRef(symbol=symbol, name=symbol)


@router.post("/stock/analyze", response_model=StockAnalysisResult)
async def analyze_stock(req: StockAnalysisRequest) -> StockAnalysisResult:
    ref = _resolve_target(req)
    if ref is None:
        raise HTTPException(status_code=422, detail="분석할 종목을 찾을 수 없습니다. 종목명을 알려주세요.")
    llm = _mlx_llm if _llm_available() else None
    # 예측 엔진은 v1에서 미연결(알파 없음·polars 데드락 리스크) → forecast '데이터 없음'.
    agent = StockAnalysisAgent(llm=llm)
    try:
        return await asyncio.to_thread(agent.analyze, ref)
    except Exception as exc:
        logger.exception("stock.analyze 실패: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─── /query/general ──────────────────────────────────────────────────────────────

class GeneralQueryRequest(BaseModel):
    query: str


class GeneralQueryResponse(BaseModel):
    answer: str
    disclaimer: str = DISCLAIMER


_GENERAL_SYSTEM_PROMPT = (
    "당신은 투자 용어와 일반 투자 지식을 쉽게 설명하는 도우미입니다. "
    "사용자의 질문에 2~4문장으로 간결하고 정확하게 답하십시오. "
    "특정 종목의 매수·매도를 권하지 말고, 확정적 수익 표현을 쓰지 마십시오. "
    "JSON 없이 평문으로만 답하십시오."
)


@router.post("/query/general", response_model=GeneralQueryResponse)
async def general_answer(req: GeneralQueryRequest) -> GeneralQueryResponse:
    if _llm_available():
        raw = await asyncio.to_thread(_mlx_llm, _GENERAL_SYSTEM_PROMPT, req.query, max_tokens=300)
        answer = guardrails.sanitize(raw)
        if answer:
            return GeneralQueryResponse(answer=answer)
    return GeneralQueryResponse(
        answer="해당 주제에 대한 일반적인 설명을 준비하지 못했습니다. 질문을 좀 더 구체적으로 입력해 주세요."
    )
