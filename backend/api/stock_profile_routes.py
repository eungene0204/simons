"""단일 종목 연구 프로파일 API (FR-STR-068b).

GET /stock/{symbol}/research-profile — 종목 선택 직후 프론트가 호출한다.
결정론 StockProfileService의 결과만 노출하며(LLM 미사용), 질문이 제안/제외된 이유를
데이터 근거와 함께 돌려준다. 전체 프로파일 원본은 노출하지 않는다(요약 계약만).
"""
from __future__ import annotations

import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stock-profile"])

_SYMBOL_RE = re.compile(r"^[0-9A-Z]{6}$")


@router.get("/stock/{symbol}/research-profile")
async def stock_research_profile(symbol: str, include_advanced: bool = False):
    """종목 프로파일 요약 + 노출/제외 질문 목록. 데이터가 없으면 404."""
    if not _SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=404, detail="유효한 종목 코드가 아닙니다.")

    from engine.single_asset_review import profile_summary_payload
    from engine.stock_profile import get_stock_profile

    profile = await asyncio.to_thread(get_stock_profile, symbol)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail="해당 종목의 백테스트 데이터가 없어 프로파일을 생성할 수 없습니다.",
        )
    payload = profile_summary_payload(profile, include_advanced=include_advanced)
    logger.info(
        "[stock-profile] symbol=%s version=%s recommended=%d excluded=%d warnings=%d",
        symbol, profile.profile_version,
        len(payload["recommended_questions"]), len(payload["excluded_questions"]),
        len(payload["profile_summary"]["warnings"]),
    )
    return payload
