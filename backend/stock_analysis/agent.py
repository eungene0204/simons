"""
StockAnalysisAgent — 개별 종목 질문 처리 오케스트레이터.

파이프라인(각 단계는 단일 책임 서비스):
  StockDataService → TechnicalAnalysisService → FundamentalAnalysisService
  → NewsAnalysisService → ForecastModelService → RiskScoringService
  → RecommendationEngine(규칙 기반 판정) → LLMExplanationGenerator(설명만)

규칙: 매수/매도 결정은 RecommendationEngine만 내린다. LLM은 설명만 한다.
데이터가 없으면 환각 대신 missing_data/'데이터 없음'으로 명시한다.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .data_service import StockDataService
from .explanation import LLMExplanationGenerator
from .forecast_service import ForecastModelService
from .fundamental_service import FundamentalAnalysisService
from .news_service import NewsAnalysisService
from .recommendation_engine import RecommendationEngine
from .risk_service import RiskScoringService
from .schemas import (
    Recommendation,
    StockAnalysisResult,
    StockMetrics,
    StockSignals,
)
from .symbol_resolver import StockRef, resolve_by_symbol
from .technical_service import TechnicalAnalysisService

logger = logging.getLogger(__name__)

LLMFn = Callable[[str, str], str]

_SIGNAL_MISSING_LABEL = {
    "trend": "추세",
    "valuation": "밸류에이션",
    "news_sentiment": "뉴스 감성",
    "forecast": "AI 예측",
    "risk": "위험도",
}


class StockAnalysisAgent:
    def __init__(self, llm: Optional[LLMFn] = None, forecast_engine=None) -> None:
        self._data = StockDataService()
        self._technical = TechnicalAnalysisService()
        self._fundamental = FundamentalAnalysisService()
        self._news = NewsAnalysisService()
        self._forecast = ForecastModelService(engine=forecast_engine)
        self._risk = RiskScoringService()
        self._engine = RecommendationEngine()
        self._explainer = LLMExplanationGenerator(llm)

    def analyze(self, ref: StockRef | str) -> StockAnalysisResult:
        if isinstance(ref, str):
            ref = resolve_by_symbol(ref) or StockRef(symbol=ref, name=ref)

        data = self._data.load(ref)

        technical = self._technical.analyze(data.ohlcv)
        fundamental = self._fundamental.analyze(data.per, data.pbr, data.roe)
        news = self._news.analyze(data.symbol)
        forecast = self._forecast.analyze(data.ohlcv)
        risk = self._risk.score(
            volatility_pct=technical.volatility_pct,
            valuation=fundamental.valuation,
            news_sentiment=news.sentiment,
            news_risk_alert=news.risk_alert_level,
        )

        signals = StockSignals(
            trend=technical.trend,
            valuation=fundamental.valuation,
            news_sentiment=news.sentiment,
            forecast=forecast.forecast,
            risk=risk.risk,
        )
        outcome = self._engine.decide(signals)

        metrics = StockMetrics(
            current_price=data.current_price,
            change_pct=data.change_pct,
            volume=data.volume,
            per=data.per,
            pbr=data.pbr,
            roe=data.roe,
            debt_ratio=data.debt_ratio,
            market_cap=data.market_cap,
            sector=data.sector,
            volatility_pct=technical.volatility_pct,
            as_of=data.as_of,
        )

        risk_factors = list(dict.fromkeys([*risk.factors, *news.risk_factors]))
        missing = self._collect_missing(data.missing, signals)

        result = StockAnalysisResult(
            symbol=data.symbol,
            name=data.name,
            recommendation=outcome.recommendation,
            confidence=outcome.confidence,
            summary=self._summary(signals, outcome.recommendation),
            signals=signals,
            metrics=metrics,
            news_summary=news.summary,
            news_url=news.source_url,
            risk_factors=risk_factors,
            missing_data=missing,
        )
        result.explanation = self._explainer.generate(result)
        return result

    @staticmethod
    def _collect_missing(data_missing: list[str], signals: StockSignals) -> list[str]:
        missing: list[str] = []
        for field_name, label in _SIGNAL_MISSING_LABEL.items():
            if getattr(signals, field_name) is None:
                missing.append(label)
        missing.extend(data_missing)
        return list(dict.fromkeys(missing))

    @staticmethod
    def _summary(signals: StockSignals, rec: Recommendation) -> str:
        if rec == Recommendation.INSUFFICIENT_DATA:
            return "판단에 필요한 데이터가 부족합니다."
        trend_word = {
            "strong_up": "강한 상승", "up": "상승", "neutral_positive": "중립 이상",
            "neutral": "중립", "neutral_negative": "중립 이하", "down": "하락", "strong_down": "강한 하락",
        }.get(signals.trend or "", "중립")
        parts = [f"추세는 {trend_word}"]
        if signals.risk in {"medium", "high"}:
            parts.append("단기 변동성 리스크가 존재합니다")
        else:
            parts.append("리스크는 제한적입니다")
        return f"{parts[0]}이나 {parts[1]}." if len(parts) == 2 else f"{parts[0]}."
