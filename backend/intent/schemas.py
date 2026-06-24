"""Query intent 분류 결과 스키마."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    STRATEGY_ADVICE = "STRATEGY_ADVICE"
    STOCK_ANALYSIS = "STOCK_ANALYSIS"
    # 특정 종목을 골라/추천해 달라는 열린 요청 — 추천 대신 전략 설계로 전환(suggested_reply).
    STOCK_PICK = "STOCK_PICK"
    # 무엇을 해야 할지 모르는 막연한 도움 요청('어떻게 시작하지?') — 전략 빌더로 유도(suggested_reply).
    ONBOARDING = "ONBOARDING"
    GENERAL_INVESTMENT = "GENERAL_INVESTMENT"
    GREETING = "GREETING"
    OFF_TOPIC = "OFF_TOPIC"
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
    # GREETING/OFF_TOPIC처럼 곧바로 보여줄 정해진 응답 문구(없으면 None).
    suggested_reply: Optional[str] = None


class IntentRequest(BaseModel):
    query: str
    # 직전 분석 종목 등 anaphora('이 종목') 해석을 돕는 보조 컨텍스트.
    last_symbol: Optional[str] = None
