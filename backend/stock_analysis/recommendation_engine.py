"""
RecommendationEngine — 규칙 기반 최종 판정(단일 책임: 지표 종합 '객관적 상태 등급' 결정).

[규제 안전] 매수/매도·시점을 지시하는 '추천'이 아니라, 지표가 현재 어떤 상태인지를
등급으로만 서술한다(FAVORABLE~HIGH_RISK). 행동 지시 라벨(STRONG_BUY 등)은 제거됐다.

**LLM을 사용하지 않는다.** signals(추세/밸류/뉴스/예측/리스크)를 결정적 규칙으로
집계해 Recommendation enum과 confidence를 산출한다. 핵심 데이터(추세·밸류 둘 다
없음)가 부족하면 INSUFFICIENT_DATA를 반환한다.

가중치 원칙:
- 추세(기술적)와 밸류에이션이 1차 근거.
- 뉴스는 보조.
- AI 예측(forecast)은 **추천을 결정하지 않는다** — 검증상 방향 알파가 없어
  점수에서 제외하고 순수 보조 게이지로만 노출한다(project_ai_auxiliary_usage).
- 위험도(risk)는 점수가 아니라 '상한 게이트' — high면 공격적 추천을 막는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import Recommendation, StockSignals

_TREND_SCORE = {
    "strong_up": 2.0,
    "up": 1.0,
    "neutral_positive": 0.5,
    "neutral": 0.0,
    "neutral_negative": -0.5,
    "down": -1.0,
    "strong_down": -2.0,
}
_VALUATION_SCORE = {"cheap": 1.0, "neutral": 0.0, "expensive": -1.0}
_NEWS_SCORE = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
# 신호 충실도(coverage) 분모 — 점수에 반영되는 신호 수(추세·밸류·뉴스). forecast 제외.
_MAX_SIGNALS = 3


@dataclass
class RecommendationOutcome:
    recommendation: Recommendation
    confidence: float


class RecommendationEngine:
    def decide(self, signals: StockSignals) -> RecommendationOutcome:
        # 핵심 데이터 부족 — 추세와 밸류에이션이 모두 없으면 판정 불가.
        if signals.trend is None and signals.valuation is None:
            return RecommendationOutcome(Recommendation.INSUFFICIENT_DATA, 0.0)

        score = 0.0
        present = 0
        score += _TREND_SCORE.get(signals.trend or "", 0.0)
        if signals.trend is not None:
            present += 1
        score += _VALUATION_SCORE.get(signals.valuation or "", 0.0)
        if signals.valuation is not None:
            present += 1
        score += _NEWS_SCORE.get(signals.news_sentiment or "", 0.0)
        if signals.news_sentiment is not None:
            present += 1
        # AI 예측(forecast)은 점수에 반영하지 않는다 — 보조 게이지 전용.

        base = self._score_to_recommendation(score)
        gated = self._apply_risk_gate(base, signals.risk)
        confidence = self._confidence(score, present, signals.risk, gated)
        return RecommendationOutcome(gated, confidence)

    @staticmethod
    def _score_to_recommendation(score: float) -> Recommendation:
        if score >= 2.5:
            return Recommendation.FAVORABLE
        if score >= 1.2:
            return Recommendation.MILDLY_FAVORABLE
        if score >= -0.5:
            return Recommendation.NEUTRAL
        if score >= -1.5:
            return Recommendation.ELEVATED_RISK
        return Recommendation.HIGH_RISK

    @staticmethod
    def _apply_risk_gate(rec: Recommendation, risk: str | None) -> Recommendation:
        """위험도 high는 긍정적 상태 등급을 한 단계 보수화한다(상한 게이트)."""
        if risk != "high":
            return rec
        downgrade = {
            Recommendation.FAVORABLE: Recommendation.MILDLY_FAVORABLE,
            Recommendation.MILDLY_FAVORABLE: Recommendation.NEUTRAL,
            Recommendation.NEUTRAL: Recommendation.ELEVATED_RISK,
        }
        return downgrade.get(rec, rec)

    @staticmethod
    def _confidence(score: float, present: int, risk: str | None, rec: Recommendation) -> float:
        if rec == Recommendation.INSUFFICIENT_DATA:
            return 0.0
        # 신호 충실도(추세·밸류·뉴스) + 점수 강도.
        coverage = present / _MAX_SIGNALS
        strength = min(abs(score) / 2.5, 1.0)
        conf = 0.35 + 0.4 * coverage + 0.25 * strength
        if risk == "high":
            conf -= 0.1
        return round(max(0.3, min(conf, 0.9)), 2)
