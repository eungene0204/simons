"""
LLMExplanationGenerator — 분석 결과를 자연어로 '설명만' 한다(단일 책임: 자연어 생성).

LLM은 이미 RecommendationEngine이 확정한 recommendation/signals를 바꾸지 못하며,
매수/매도 지시·확정 수익 표현도 금지된다(프롬프트 + guardrails 이중 차단).
LLM이 없거나 실패하면 결정적 템플릿 설명으로 폴백한다(기능 항상 동작 보장).

설명 구조(스펙 §5): 종목명 → 요약 → 핵심 지표 → 뉴스/이슈 → 리스크 → 최종 의견 → 면책.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from . import guardrails
from .schemas import Recommendation, StockAnalysisResult

logger = logging.getLogger(__name__)

LLMFn = Callable[[str, str], str]

_RECOMMENDATION_KO = {
    Recommendation.STRONG_BUY: "여러 지표가 긍정적이고 리스크가 제한적인 구간으로 보입니다",
    Recommendation.ACCUMULATE: "긍정적이나 단기 리스크가 있어 분할 접근이 적절해 보입니다",
    Recommendation.HOLD: "신규 매수보다는 보유 또는 관망이 적절해 보입니다",
    Recommendation.CAUTION: "리스크가 커서 신중한 접근이 필요해 보입니다",
    Recommendation.AVOID: "현재 조건에서는 진입을 피하는 편이 적절해 보입니다",
    Recommendation.INSUFFICIENT_DATA: "판단에 필요한 데이터가 부족합니다",
}

# Recommendation enum 값을 한글 라벨로 매핑 (LLM context용)
_RECOMMENDATION_LABEL = {
    Recommendation.STRONG_BUY: "강한 긍정",
    Recommendation.ACCUMULATE: "분할 매수",
    Recommendation.HOLD: "보유/관망",
    Recommendation.CAUTION: "주의",
    Recommendation.AVOID: "회피",
    Recommendation.INSUFFICIENT_DATA: "데이터 부족",
}

_SIGNAL_KO = {
    "trend": {
        "strong_up": "강한 상승 추세", "up": "상승 추세", "neutral_positive": "중립~약한 상승",
        "neutral": "뚜렷한 추세 없음", "neutral_negative": "중립~약한 하락",
        "down": "하락 추세", "strong_down": "강한 하락 추세",
    },
    "valuation": {"cheap": "저평가 구간", "neutral": "적정 밸류에이션", "expensive": "고평가 구간"},
    "news_sentiment": {"positive": "긍정적", "neutral": "중립", "negative": "부정적"},
    "forecast": {
        "positive": "상승 우위", "slightly_positive": "약한 상승 우위", "neutral": "중립",
        "slightly_negative": "약한 하락 우위", "negative": "하락 우위",
    },
    "risk": {"low": "낮음", "medium": "보통", "high": "높음"},
}

_SYSTEM_PROMPT = (
    "당신은 종목 분석 결과를 사용자에게 쉽게 설명하는 도우미입니다. "
    "최종 추천(recommendation)과 신호(signals)는 이미 규칙 엔진이 확정했습니다. "
    "당신의 역할은 그 결과를 설명·요약하고 리스크와 확인이 필요한 정보를 안내하는 것뿐입니다. "
    "절대 추천 등급을 바꾸지 마십시오. "
    "'매수하세요/매도하세요' 같은 직접 지시, '반드시 오릅니다/수익 보장/손실 없음' 같은 확정적 표현, "
    "투자 책임을 사용자에게 떠넘기는 표현을 쓰지 마십시오. "
    "아래에 제공된 지표만으로 설명하십시오. 제공되지 않은 항목(예: 뉴스, AI 예측)은 추측으로 채우지도, "
    "언급하지도 마십시오. '데이터 없음', '확보되지 않았다', '정보가 부족하다', '파악에 한계가 있다' 같은 "
    "표현으로 없는 데이터를 거론하는 것도 금지합니다. 없는 항목은 그냥 빼고, 있는 지표만으로 자연스럽게 쓰십시오. "
    "제공된 지표 안에서 종목명, 현재 분석 요약, 핵심 지표, (뉴스가 있으면) 뉴스/이슈, 리스크 요인, 최종 의견 순으로 작성하십시오. "
    "한국어 평문으로 자연스럽게 쓰고, JSON이나 머리말 기호 없이 문단으로만 답하십시오."
)


class LLMExplanationGenerator:
    def __init__(self, llm: Optional[LLMFn] = None) -> None:
        self._llm = llm

    def generate(self, result: StockAnalysisResult) -> str:
        # INSUFFICIENT_DATA 설명은 데이터 부족을 알리는 것이 목적이므로 strip 대상에서 제외한다.
        if result.recommendation == Recommendation.INSUFFICIENT_DATA:
            return guardrails.apply(self._template(result))

        text = self._try_llm(result) if self._llm is not None else None
        text = text or self._template(result)
        text = guardrails.sanitize(text)
        # 없는 데이터(뉴스·AI 예측 등)를 거론하는 문장은 제거한다 — 아예 언급하지 않는다.
        text = guardrails.strip_unavailable_data_mentions(text, self._missing_topics(result))
        explanation = guardrails.ensure_disclaimer(text)
        # 설명이 '뉴스'를 언급하면 실제 출처 기사 URL을 링크로 단다.
        return guardrails.attach_news_link(explanation, result.news_url)

    @staticmethod
    def _missing_topics(result: StockAnalysisResult) -> list[str]:
        """데이터가 없는 주제의 정규식 목록 — 이 주제를 언급한 문장은 통째로 제거된다."""
        topics: list[str] = []
        if not result.news_summary and result.signals.news_sentiment is None:
            topics.append(r"뉴스|이슈|감성|시장\s*분위기")
        if result.signals.forecast is None:
            topics.append(r"AI\s*예측|예측\s*모델|예측")
        return topics

    def _try_llm(self, result: StockAnalysisResult) -> Optional[str]:
        try:
            raw = self._llm(_SYSTEM_PROMPT, self._build_context(result))
        except Exception:
            logger.debug("종목 설명 LLM 실패 — 템플릿 폴백", exc_info=True)
            return None
        cleaned = (raw or "").strip()
        return cleaned or None

    @staticmethod
    def _build_context(result: StockAnalysisResult) -> str:
        """확보된 지표만 컨텍스트에 넣는다. 없는 항목은 아예 빼서 LLM이 거론하지 않게 한다.
        절대 내부 변수명(strong_down 등)과 영어(ACCUMULATE 등)을 노출하지 않고 번역된 한글 라벨만 사용한다."""
        s = result.signals
        m = result.metrics
        rec_label = _RECOMMENDATION_LABEL.get(result.recommendation, result.recommendation.value)
        lines = [
            f"종목명: {result.name} ({result.symbol})",
            f"확정 추천(변경 금지): {rec_label}",
            f"신뢰도: {result.confidence}",
        ]

        def add(label_text: str, value: str | None) -> None:
            if value is not None and value != "":
                lines.append(f"{label_text}: {value}")

        # 내부 변수명 대신 번역된 한글 라벨만 사용
        def translated(group: str, raw_value: str | None) -> str | None:
            if raw_value is None:
                return None
            return _SIGNAL_KO.get(group, {}).get(raw_value, raw_value)

        add("추세", translated("trend", s.trend))
        add("밸류에이션", translated("valuation", s.valuation))
        add("뉴스 감성", translated("news_sentiment", s.news_sentiment))
        add("AI 예측(보조)", translated("forecast", s.forecast))
        add("위험도", translated("risk", s.risk))
        add("현재가", str(m.current_price) if m.current_price is not None else None)
        add("등락률", f"{m.change_pct:+.2f}%" if m.change_pct is not None else None)
        add("PER", f"{m.per:.1f}배" if m.per is not None else None)
        add("PBR", f"{m.pbr:.1f}배" if m.pbr is not None else None)
        add("ROE", f"{m.roe:.1f}%" if m.roe is not None else None)
        add("섹터", m.sector)
        add("뉴스 요약", result.news_summary)
        if result.risk_factors:
            lines.append(f"리스크 요인: {', '.join(result.risk_factors)}")
        return "\n".join(lines)

    @classmethod
    def _template(cls, result: StockAnalysisResult) -> str:
        s = result.signals
        m = result.metrics

        if result.recommendation == Recommendation.INSUFFICIENT_DATA:
            return (
                f"{result.name}에 대해 분석에 필요한 데이터가 부족합니다. "
                f"부족한 항목: {', '.join(result.missing_data) if result.missing_data else '대부분의 지표'}. "
                "데이터가 확보되면 다시 분석해 드리겠습니다."
            )

        def label(group: str, value: str | None) -> Optional[str]:
            if value is None:
                return None
            return _SIGNAL_KO.get(group, {}).get(value, value)

        # 확보된 신호만 평가 문장에 넣는다(없는 항목은 거론하지 않음).
        signal_bits = []
        if (trend := label("trend", s.trend)):
            signal_bits.append(f"추세는 {trend}")
        if (valuation := label("valuation", s.valuation)):
            signal_bits.append(f"밸류에이션은 {valuation}")
        if (sentiment := label("news_sentiment", s.news_sentiment)):
            signal_bits.append(f"뉴스 흐름은 {sentiment}")
        if (risk := label("risk", s.risk)):
            signal_bits.append(f"위험도는 {risk} 수준")
        signal_text = (
            f"현재 {', '.join(signal_bits)}으로 평가됩니다. " if signal_bits else ""
        )

        metric_bits = []
        if m.current_price is not None:
            change = f" ({m.change_pct:+.2f}%)" if m.change_pct is not None else ""
            metric_bits.append(f"현재가 {m.current_price:,.0f}원{change}")
        for name, val, suffix in (("PER", m.per, "배"), ("PBR", m.pbr, "배"), ("ROE", m.roe, "%")):
            if val is not None:
                metric_bits.append(f"{name} {val:.1f}{suffix}")
        if m.volatility_pct is not None:
            metric_bits.append(f"연율 변동성 {m.volatility_pct:.0f}%")
        metrics_text = f"핵심 지표: {', '.join(metric_bits)}. " if metric_bits else ""

        # 뉴스/리스크 요인은 있을 때만 언급한다.
        news_text = f"뉴스/이슈: {result.news_summary}. " if result.news_summary else ""
        risk_text = f"리스크 요인: {', '.join(result.risk_factors)}. " if result.risk_factors else ""

        return (
            f"[{result.name}({result.symbol})] "
            f"{signal_text}{metrics_text}{news_text}{risk_text}"
            f"종합하면 {_RECOMMENDATION_KO[result.recommendation]}."
        )
