"""
FundamentalAnalysisService — PER/PBR/ROE로 밸류에이션 판정(단일 책임: 재무 분석).

단순·결정적 임계 기준. 값이 없으면 None을 반환한다(환각 금지).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FundamentalResult:
    valuation: Optional[str] = None  # cheap | neutral | expensive
    notes: Optional[str] = None


class FundamentalAnalysisService:
    def analyze(
        self,
        per: Optional[float],
        pbr: Optional[float],
        roe: Optional[float],
    ) -> FundamentalResult:
        # 핵심 밸류 지표(PER/PBR)가 모두 없으면 판정 불가.
        if per is None and pbr is None:
            return FundamentalResult()

        score = 0  # 음수=저평가, 양수=고평가
        if per is not None:
            if per <= 0:
                score += 1  # 적자 — 고평가/주의 쪽
            elif per < 10:
                score -= 1
            elif per > 25:
                score += 1
        if pbr is not None:
            if pbr < 1.0:
                score -= 1
            elif pbr > 3.0:
                score += 1
        # 높은 ROE는 고평가를 일부 정당화 → 점수 완화.
        if roe is not None and roe >= 15 and score > 0:
            score -= 1

        if score <= -1:
            valuation = "cheap"
        elif score >= 1:
            valuation = "expensive"
        else:
            valuation = "neutral"
        return FundamentalResult(valuation=valuation)
