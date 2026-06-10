"""RecommendationEngine 규칙 테스트 — 결정적 판정, 위험 게이트, 데이터 부족."""

from __future__ import annotations

from stock_analysis.recommendation_engine import RecommendationEngine
from stock_analysis.schemas import Recommendation, StockSignals

engine = RecommendationEngine()


def test_insufficient_when_core_signals_missing():
    out = engine.decide(StockSignals())
    assert out.recommendation == Recommendation.INSUFFICIENT_DATA
    assert out.confidence == 0.0


def test_strong_buy_when_all_positive_low_risk():
    out = engine.decide(StockSignals(
        trend="strong_up", valuation="cheap", news_sentiment="positive",
        forecast="positive", risk="low",
    ))
    assert out.recommendation == Recommendation.STRONG_BUY
    assert out.confidence > 0.7


def test_avoid_when_all_negative():
    out = engine.decide(StockSignals(
        trend="strong_down", valuation="expensive", news_sentiment="negative", risk="medium",
    ))
    assert out.recommendation == Recommendation.AVOID


def test_hold_when_mixed_neutral():
    out = engine.decide(StockSignals(trend="neutral", valuation="neutral", risk="low"))
    assert out.recommendation == Recommendation.HOLD


def test_high_risk_gate_downgrades_strong_buy():
    base = StockSignals(trend="strong_up", valuation="cheap", news_sentiment="positive", forecast="positive")
    low = engine.decide(base.model_copy(update={"risk": "low"}))
    high = engine.decide(base.model_copy(update={"risk": "high"}))
    assert low.recommendation == Recommendation.STRONG_BUY
    # high risk는 한 단계 보수화.
    assert high.recommendation == Recommendation.ACCUMULATE


def test_partial_data_still_decides():
    # 추세만 있어도 판정 가능(INSUFFICIENT 아님).
    out = engine.decide(StockSignals(trend="up"))
    assert out.recommendation != Recommendation.INSUFFICIENT_DATA


def test_forecast_does_not_affect_recommendation():
    # AI 예측은 매매를 결정하지 않는다(점수 제외) — forecast 유무가 추천·confidence를 바꾸지 않는다.
    base = StockSignals(trend="up", valuation="neutral", news_sentiment="neutral", risk="low")
    without = engine.decide(base)
    with_pos = engine.decide(base.model_copy(update={"forecast": "positive"}))
    with_neg = engine.decide(base.model_copy(update={"forecast": "negative"}))
    assert with_pos.recommendation == without.recommendation
    assert with_neg.recommendation == without.recommendation
    assert with_pos.confidence == without.confidence == with_neg.confidence
