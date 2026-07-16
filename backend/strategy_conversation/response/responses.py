"""사용자 응답 생성 — 내부 JSON을 그대로 노출하지 않는 자연어 응답(결정론).

규제 안전 원칙: 추천·전망·조언 표현 금지. 추천값은 '일반적인 시작값' 표현으로만
제시하고 사용자 확인을 받는다.
"""

from __future__ import annotations

from typing import List, Optional

from strategy_conversation.interpreter.models import (
    StrategyIntent,
    ValidationReport,
)
from strategy_conversation.registry.indicator_registry import REGISTRY


def _describe_conditions(intent: StrategyIntent) -> List[str]:
    lines: List[str] = []
    strategy = intent.strategy
    if strategy is None:
        return lines
    for role, conditions in (("진입", strategy.entry_conditions), ("청산", strategy.exit_conditions)):
        for cond in conditions:
            spec = REGISTRY.get(cond.factor)
            name = spec.display_name if spec else cond.factor
            if cond.operator and cond.value is not None:
                lines.append(f"- {role}: {name} {cond.operator} {cond.value:g}")
            elif cond.value is None:
                lines.append(f"- {role}: {name} (기준값 미정)")
            else:
                lines.append(f"- {role}: {name}")
    for rank in strategy.ranking:
        lookback = f" (최근 {rank.lookback_days}거래일)" if rank.lookback_days else ""
        lines.append(f"- 선정: 기간 수익률 상위 랭킹{lookback}")
    return lines


def build_clarification_response(intent: StrategyIntent, report: ValidationReport) -> str:
    """누락/모호 항목에 대한 되묻기 응답."""
    parts: List[str] = []
    summary = _describe_conditions(intent)
    if summary:
        parts.append("요청을 다음 조건으로 이해했습니다.")
        parts.extend(summary)
        parts.append("")
    if report.errors:
        parts.append("확인이 필요한 문제가 있습니다.")
        parts.extend(f"- {e}" for e in report.errors)
        parts.append("")
    if report.clarification_questions:
        parts.append("아직 정해지지 않은 값이 있습니다.")
        for q in report.clarification_questions:
            line = f"- {q.question}"
            if q.recommended_value is not None:
                reason = f" ({q.recommendation_reason})" if q.recommendation_reason else ""
                line += f" 일반적인 시작값: {q.recommended_value}{reason}"
            parts.append(line)
    return "\n".join(parts).strip()


def build_unsupported_response(report: ValidationReport) -> str:
    """미지원 기능 안내 — 조용한 대체 없이 명시적으로 알리고 확인을 받는다."""
    features = ", ".join(report.unsupported_features)
    parts = [
        f"요청하신 조건({features})의 의미는 이해했지만, "
        "현재 데이터 파이프라인/백테스트 엔진에서는 지원되지 않아 실행할 수 없습니다."
    ]
    if report.suggested_fixes:
        parts.append("")
        parts.extend(report.suggested_fixes)
    return "\n".join(parts)


def build_strategy_summary(intent: StrategyIntent, warnings: Optional[List[str]] = None) -> str:
    """READY 상태 전략의 확인용 요약."""
    parts = ["다음 조건의 전략으로 구성했습니다."]
    parts.extend(_describe_conditions(intent))
    strategy = intent.strategy
    if strategy is not None:
        markets = "+".join(strategy.universe.markets)
        sector = f", 섹터: {', '.join(strategy.universe.sectors)}" if strategy.universe.sectors else ""
        parts.append(f"- 유니버스: {markets}{sector}")
        if strategy.portfolio.selection_count:
            parts.append(f"- 종목 수: {strategy.portfolio.selection_count}개")
        if strategy.portfolio.rebalance_frequency:
            parts.append(f"- 리밸런싱: {strategy.portfolio.rebalance_frequency}")
        risk = strategy.risk_management
        for label, value in (("손절", risk.stop_loss), ("익절", risk.take_profit),
                             ("트레일링 스탑", risk.trailing_stop)):
            if value is not None:
                parts.append(f"- {label}: {value:g}%")
    if warnings:
        parts.append("")
        parts.extend(f"⚠ {w}" for w in warnings)
    parts.append("")
    parts.append("결과는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다.")
    return "\n".join(parts)
