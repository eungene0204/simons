"""
RiskScoringService — 변동성/밸류에이션/뉴스로 위험도 산출(단일 책임: 리스크 평가).

결정적 규칙. 입력이 모두 없으면 risk=None을 반환한다(환각 금지).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RiskResult:
    risk: Optional[str] = None  # low | medium | high
    factors: list[str] = field(default_factory=list)


class RiskScoringService:
    def score(
        self,
        *,
        volatility_pct: Optional[float],
        valuation: Optional[str],
        news_sentiment: Optional[str],
        news_risk_alert: Optional[str],
    ) -> RiskResult:
        if volatility_pct is None and valuation is None and news_sentiment is None and news_risk_alert is None:
            return RiskResult()

        score = 0
        factors: list[str] = []

        if volatility_pct is not None:
            if volatility_pct >= 50:
                score += 2
                factors.append(f"높은 변동성(연율 {volatility_pct:.0f}%)")
            elif volatility_pct >= 30:
                score += 1
                factors.append(f"중간 변동성(연율 {volatility_pct:.0f}%)")

        if valuation == "expensive":
            score += 1
            factors.append("밸류에이션 부담(고평가 구간)")

        if news_sentiment == "negative":
            score += 1
            factors.append("부정적 뉴스 흐름")

        if news_risk_alert == "high":
            score += 2
            factors.append("뉴스 고위험 경보")
        elif news_risk_alert == "medium":
            score += 1

        if score >= 3:
            risk = "high"
        elif score >= 1:
            risk = "medium"
        else:
            risk = "low"
        return RiskResult(risk=risk, factors=factors)
