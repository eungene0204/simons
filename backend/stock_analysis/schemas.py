"""Stock Analysis Agent 결과 스키마."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

DISCLAIMER = (
    "이 분석은 투자 판단을 위한 참고 정보이며, 최종 투자 결정은 본인의 책임입니다."
)

# 데이터가 없는 항목에 일관되게 노출할 문구.
NO_DATA = "데이터 없음"


class Recommendation(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    ACCUMULATE = "ACCUMULATE"
    HOLD = "HOLD"
    CAUTION = "CAUTION"
    AVOID = "AVOID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class StockSignals(BaseModel):
    # 각 신호는 규칙 엔진이 채우며, 데이터가 없으면 None(프론트에서 '데이터 없음' 표시).
    trend: Optional[str] = None            # strong_up | up | neutral_positive | neutral | neutral_negative | down | strong_down
    valuation: Optional[str] = None        # cheap | neutral | expensive
    news_sentiment: Optional[str] = None   # positive | neutral | negative
    forecast: Optional[str] = None         # positive | slightly_positive | neutral | slightly_negative | negative
    risk: Optional[str] = None             # low | medium | high


class StockMetrics(BaseModel):
    """UI 패널/핵심 지표용 수치. 없는 값은 None."""
    current_price: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    per: Optional[float] = None
    pbr: Optional[float] = None
    roe: Optional[float] = None
    debt_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    volatility_pct: Optional[float] = None   # 최근 변동성(연율화 %)
    as_of: Optional[str] = None              # 데이터 기준일(YYYY-MM-DD)


class AIForecastGauge(BaseModel):
    """AI 모델 보조 게이지 — 매매 결정에 쓰지 않는 참고용. 자기 시계열 퍼센타일 보정.

    검증상 방향 알파는 없고 약세장 하방 방어만 입증됐다(project_ai_auxiliary_usage).
    그래서 1차 메시지는 '하방 리스크 수준'이다.
    """
    down_risk_level: Optional[str] = None  # elevated | moderate | calm
    down_pctl: Optional[int] = None        # 오늘 하락확률의 자기 시계열 퍼센타일(0~100)
    up_pctl: Optional[int] = None          # 오늘 상승확률의 자기 시계열 퍼센타일


class StockAnalysisResult(BaseModel):
    intent: str = "STOCK_ANALYSIS"
    symbol: str
    name: str
    recommendation: Recommendation
    confidence: float = 0.0
    summary: str = ""                 # 규칙 기반 한 줄 요약(신호 집계)
    explanation: str = ""            # LLM 자연어 설명(스펙 §5 구조). 없으면 빈 문자열.
    signals: StockSignals = Field(default_factory=StockSignals)
    metrics: StockMetrics = Field(default_factory=StockMetrics)
    ai_forecast: Optional[AIForecastGauge] = None  # AI 보조 게이지(없으면 데이터 없음)
    news_summary: Optional[str] = None
    news_url: Optional[str] = None    # 대표 출처 기사 URL(설명의 '뉴스'에 링크)
    risk_factors: List[str] = Field(default_factory=list)
    missing_data: List[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


class StockAnalysisRequest(BaseModel):
    symbol: Optional[str] = None
    query: Optional[str] = None
    last_symbol: Optional[str] = None
