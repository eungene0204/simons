"""StockAnalysisAgent 스모크 테스트 — 안전장치(LLM 설명 전용, 면책, 데이터 없음)."""

from __future__ import annotations

import pandas as pd

from stock_analysis import guardrails
from stock_analysis.agent import StockAnalysisAgent
from stock_analysis.data_service import StockData
from stock_analysis.forecast_service import ForecastResult
from stock_analysis.fundamental_service import FundamentalResult
from stock_analysis.news_service import NewsResult
from stock_analysis.schemas import Recommendation
from stock_analysis.symbol_resolver import StockRef
from stock_analysis.technical_service import TechnicalResult


class _FakeData:
    def __init__(self, data: StockData):
        self._data = data

    def load(self, ref):
        return self._data


def _wire(agent, *, data, technical=None, fundamental=None, news=None, forecast=None):
    agent._data = _FakeData(data)
    agent._technical = type("T", (), {"analyze": lambda self, df: technical or TechnicalResult()})()
    agent._fundamental = type("F", (), {"analyze": lambda self, *a: fundamental or FundamentalResult()})()
    agent._news = type("N", (), {"analyze": lambda self, s: news or NewsResult()})()
    agent._forecast = type("Fc", (), {"analyze": lambda self, df: forecast or ForecastResult()})()


def _good_data():
    df = pd.DataFrame({"close": [1.0] * 30, "volume": [100.0] * 30})
    return StockData(symbol="005930", name="삼성전자", ohlcv=df, current_price=70000.0,
                     change_pct=1.2, volume=1000.0, per=12.0, pbr=1.1, roe=14.0, missing=["시가총액"])


def test_disclaimer_always_present():
    agent = StockAnalysisAgent()
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=20.0),
          fundamental=FundamentalResult(valuation="neutral"))
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert "본인의 책임" in result.explanation


def test_recommendation_enum_has_no_action_directives():
    # [규제 회귀] 개별 종목 매수/매도/보유 '행동 지시' 등급은 금지된다(CLAUDE.md 유사투자자문 회피).
    # enum은 객관적 상태 등급(FAVORABLE~HIGH_RISK)만 가진다 — STRONG_BUY/ACCUMULATE/HOLD 재도입 방지.
    values = {r.value for r in Recommendation}
    assert {"STRONG_BUY", "ACCUMULATE", "HOLD", "CAUTION", "AVOID"}.isdisjoint(values)
    assert values == {
        "FAVORABLE", "MILDLY_FAVORABLE", "NEUTRAL", "ELEVATED_RISK", "HIGH_RISK", "INSUFFICIENT_DATA",
    }


def test_explanation_never_contains_buy_sell_timing_directive():
    # [규제 회귀] 긍정 신호(상승+저평가)로 가장 우호적인 등급이 나와도, 설명에 매수/매도/시점
    # 행동 지시가 남으면 안 된다. LLM이 지시체를 뱉어도 guardrails가 문장째 제거한다.
    def rogue_llm(system, user):
        return (
            "삼성전자는 추세가 강한 상승세입니다. "
            "지금이 매수 시점이므로 분할 매수하세요. "
            "밸류에이션은 저평가 구간으로 관찰됩니다."
        )

    agent = StockAnalysisAgent(llm=rogue_llm)
    _wire(agent, data=_good_data(),
          technical=TechnicalResult(trend="strong_up", volatility_pct=15.0),
          fundamental=FundamentalResult(valuation="cheap"))
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    for banned in ("매수하세요", "매도하세요", "분할 매수", "매수 시점", "매도 시점", "사세요", "파세요"):
        assert banned not in result.explanation, f"설명에 행동 지시 '{banned}' 노출됨"
    assert result.disclaimer


def test_missing_data_recorded_not_hallucinated():
    data = StockData(symbol="005930", name="삼성전자", missing=["현재가", "OHLCV"])
    agent = StockAnalysisAgent()
    _wire(agent, data=data)  # 모든 신호 None
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert result.recommendation == Recommendation.INSUFFICIENT_DATA
    assert "추세" in result.missing_data
    assert result.metrics.current_price is None


def test_llm_cannot_change_recommendation_and_forbidden_stripped():
    # 규칙 엔진은 중립 데이터로 NEUTRAL을 내지만, LLM이 금지 표현을 쏟아내도
    # recommendation은 바뀌지 않고 설명에서 금지 표현이 제거된다.
    def rogue_llm(system, user):
        return "이 종목은 무조건 사세요. 반드시 오릅니다. 손실 가능성 없습니다."

    agent = StockAnalysisAgent(llm=rogue_llm)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="neutral", volatility_pct=20.0),
          fundamental=FundamentalResult(valuation="neutral"))
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))

    assert result.recommendation == Recommendation.NEUTRAL
    assert not guardrails.contains_forbidden(result.explanation)
    assert "무조건 사세요" not in result.explanation
    assert "본인의 책임" in result.explanation


def test_news_mention_gets_source_link():
    # 뉴스 출처 URL이 있으면 설명의 첫 '뉴스'가 마크다운 링크로 변환된다.
    news = NewsResult(sentiment="negative", summary="최근 뉴스 2건",
                      source_url="https://news.example.com/article/1")
    agent = StockAnalysisAgent(llm=None)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="expensive"), news=news)
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert result.news_url == "https://news.example.com/article/1"
    assert "[뉴스](https://news.example.com/article/1)" in result.explanation


def test_no_news_url_leaves_plain_text():
    news = NewsResult(sentiment="negative", summary="최근 뉴스 2건", source_url=None)
    agent = StockAnalysisAgent(llm=None)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="neutral"), news=news)
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert "](http" not in result.explanation


def test_missing_signals_not_mentioned_in_explanation():
    # 뉴스·AI 예측이 없으면 설명에서 아예 거론하지 않는다(템플릿 경로).
    agent = StockAnalysisAgent(llm=None)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="neutral"))  # news/forecast 없음
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert "데이터 없음" not in result.explanation
    assert "뉴스" not in result.explanation
    assert "AI 예측" not in result.explanation
    assert "확보" not in result.explanation


def test_llm_unavailable_data_sentence_stripped():
    # LLM이 '뉴스·AI 예측 데이터가 확보되지 않아 한계가 있다'고 해도 그 문장을 제거한다.
    def llm(system, user):
        return (
            "삼성전자는 상승 추세가 이어지고 있습니다. "
            "뉴스 감성과 AI 예측 데이터는 확보되지 않아 시장 분위기를 파악하는 데 한계가 있습니다. "
            "밸류에이션은 적정 수준입니다."
        )

    agent = StockAnalysisAgent(llm=llm)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="neutral"))
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert "확보되지" not in result.explanation
    assert "한계" not in result.explanation
    assert "상승 추세" in result.explanation  # 정상 문장은 유지


def test_news_topic_sentence_stripped_any_phrasing():
    # 보고된 표현: 데이터가 없을 때 뉴스/이슈를 거론하는 어떤 문장도 제거한다.
    def llm(system, user):
        return (
            "삼성전자는 상승 추세가 이어지고 있습니다. "
            "제공된 지표에는 뉴스나 이슈 정보가 포함되어 있지 않아 해당 내용은 분석하지 않습니다. "
            "밸류에이션은 고평가 구간입니다."
        )

    agent = StockAnalysisAgent(llm=llm)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="expensive"))  # news/forecast 없음
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert "뉴스" not in result.explanation
    assert "이슈" not in result.explanation
    assert "분석하지 않습니다" not in result.explanation
    assert "상승 추세" in result.explanation
    assert "고평가" in result.explanation


def test_news_sentence_kept_when_news_data_present():
    # 뉴스 데이터가 있으면 뉴스 문장은 유지된다(주제 제거는 '없을 때'만).
    def llm(system, user):
        return "삼성전자는 최근 부정적 뉴스 흐름이 있습니다. 추세는 상승입니다."

    news = NewsResult(sentiment="negative", summary="최근 뉴스 2건", source_url="https://n.example/1")
    agent = StockAnalysisAgent(llm=llm)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="neutral"), news=news)
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert "뉴스" in result.explanation


def test_template_fallback_when_no_llm():
    agent = StockAnalysisAgent(llm=None)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="cheap"), news=NewsResult(sentiment="positive", summary="최근 뉴스 2건"))
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert "삼성전자" in result.explanation
    assert result.recommendation != Recommendation.INSUFFICIENT_DATA


def test_internal_variable_names_not_exposed():
    # 내부 변수명(strong_down, neutral_positive 등)이 설명에 노출되면 안 된다.
    # LLM context에 번역된 한글 라벨만 보내므로, LLM도 한글만 볼 수 있다.
    def spy_llm(system, user):
        # user에 raw 변수명이 없는지 확인
        assert "strong_down" not in user, "LLM context에 strong_down 노출됨"
        assert "neutral_positive" not in user, "LLM context에 neutral_positive 노출됨"
        assert "cheap" not in user, "LLM context에 cheap 노출됨 (한글 라벨 사용해야 함)"
        # 대신 한글 라벨이 있어야 함
        assert "강한 하락" in user or "상승 추세" in user
        return "삼성전자는 현재 약세 상황입니다."

    agent = StockAnalysisAgent(llm=spy_llm)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="strong_down", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="cheap"))
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    # 결과에도 raw 변수명이 노출되면 안 된다
    assert "strong_down" not in result.explanation
    assert "cheap" not in result.explanation


def test_ai_gauge_populated_but_not_in_recommendation():
    # AI 게이지(하방 리스크)는 결과에 노출되지만 추천 점수는 바꾸지 않는다(보조 전용).
    forecast = ForecastResult(forecast="slightly_negative", up_prob=0.25, down_prob=0.41,
                              up_pctl=40, down_pctl=92, down_risk_level="elevated")
    agent = StockAnalysisAgent(llm=None)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="neutral"), forecast=forecast)
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert result.ai_forecast is not None
    assert result.ai_forecast.down_risk_level == "elevated"
    assert result.ai_forecast.down_pctl == 92
    # forecast가 없을 때와 추천이 동일해야 한다(게이지는 추천에 무영향).
    agent2 = StockAnalysisAgent(llm=None)
    _wire(agent2, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="neutral"))
    base = agent2.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert result.recommendation == base.recommendation
    assert result.confidence == base.confidence


def test_ai_gauge_none_when_no_forecast():
    agent = StockAnalysisAgent(llm=None)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="neutral"))  # forecast 기본 None
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))
    assert result.ai_forecast is None


def test_english_recommendation_not_exposed():
    # MILDLY_FAVORABLE 같은 영어 enum 값이 설명에 노출되면 안 된다.
    # LLM context에 "지표 다소 양호" 같은 한글 상태 등급 라벨만 보내므로, LLM도 한글만 볼 수 있다.
    context_received = {}

    def spy_llm(system, user):
        context_received["user"] = user
        # context에 영어 enum 값이 없어야 함
        assert "MILDLY_FAVORABLE" not in user, "LLM context에 MILDLY_FAVORABLE 노출됨"
        assert "FAVORABLE" not in user, "LLM context에 FAVORABLE 노출됨"
        assert "NEUTRAL" not in user, "LLM context에 NEUTRAL 노출됨"
        # 대신 한글 상태 등급 라벨이 있어야 함 (trend up + valuation cheap → MILDLY_FAVORABLE)
        assert "지표 다소 양호" in user, "LLM context에 '지표 다소 양호' 라벨이 없음"
        return "추세는 상승세이고 밸류에이션은 저평가 구간으로 관찰됩니다."

    agent = StockAnalysisAgent(llm=spy_llm)
    _wire(agent, data=_good_data(), technical=TechnicalResult(trend="up", volatility_pct=18.0),
          fundamental=FundamentalResult(valuation="cheap"))
    result = agent.analyze(StockRef(symbol="005930", name="삼성전자"))

    # LLM이 받은 context에 영어 enum이 없는지 재확인
    assert "MILDLY_FAVORABLE" not in context_received["user"]
    assert "지표 다소 양호" in context_received["user"]
    # 결과 설명에도 영어 enum이 없어야 함
    assert "MILDLY_FAVORABLE" not in result.explanation
