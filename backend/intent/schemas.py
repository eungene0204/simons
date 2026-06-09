"""Query intent 분류 결과 스키마."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    STRATEGY_ADVICE = "STRATEGY_ADVICE"
    STOCK_ANALYSIS = "STOCK_ANALYSIS"
    GENERAL_INVESTMENT = "GENERAL_INVESTMENT"
    UNKNOWN = "UNKNOWN"


class DetectedSymbol(BaseModel):
    symbol: str
    name: str
    overseas: bool = False


class IntentResult(BaseModel):
    intent: QueryIntent
    symbols: List[DetectedSymbol] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    # 결정적 규칙으로 끝났는지(테스트/디버깅용). LLM 폴백을 거쳤으면 False.
    deterministic: bool = True


class IntentRequest(BaseModel):
    query: str
    # 직전 분석 종목 등 anaphora('이 종목') 해석을 돕는 보조 컨텍스트.
    last_symbol: Optional[str] = None
