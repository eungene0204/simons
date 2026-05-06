"""
Compose ordered user-facing response sections for the strategy advisor.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .schemas import AdviceItem, AdvisorRequest, Issue, ResponseSection


SECTION_TITLES = [
    "전략 요약",
    "현재 전략의 문제점",
    "과거 유사 전략 사례",
    "Experience Memory에서 발견한 패턴",
    "개선 제안",
    "재백테스트 조건",
    "주의할 점",
    "최종 추천",
]


def _strategy_summary(req: AdvisorRequest) -> str:
    strategy = req.parsed_strategy or {}
    universe = strategy.get("universe") or strategy.get("universe_id") or "미정"
    entry = strategy.get("entry_signals") or strategy.get("entry") or []
    exit_rules = strategy.get("exit_signals") or strategy.get("exit") or []
    capital = strategy.get("initial_capital")
    parts = [
        f"사용자 전략은 '{req.user_prompt}'입니다.",
        f"유니버스는 {universe}이며 진입 조건 {len(entry)}개, 청산 조건 {len(exit_rules)}개로 해석했습니다.",
    ]
    if capital:
        parts.append(f"초기자금은 {capital:,}원 기준으로 현실성을 점검합니다.")
    if req.backtest_result is None:
        parts.append("현재 백테스트 결과가 없어 성과는 단정하지 않습니다.")
    return " ".join(parts)


def _problem_summary(issues: Sequence[Issue]) -> str:
    if not issues:
        return "명시적으로 탐지된 구조적 문제는 적지만, 비용/슬리피지/OOS 검증 전에는 전략 품질을 확정할 수 없습니다."
    top = sorted(issues, key=lambda issue: {"high": 0, "medium": 1, "low": 2}[issue.severity])[:3]
    return " ".join(f"[{item.severity}] {item.message}" for item in top)


def _similar_case_summary(memory_context: Dict[str, Any] | None) -> str:
    if not memory_context:
        return "저장된 유사 전략 검색 결과가 없습니다. 과거 사례가 충분한 것처럼 가정하지 않습니다."
    cases = memory_context.get("retrieved_cases") or []
    if not cases:
        return "RAG 검색 결과가 부족합니다. 현재 조언은 일반 퀀트 원칙 기반의 낮은 신뢰도 점검입니다."
    lines = []
    for case in cases[:3]:
        lines.append(
            f"{case.get('case_strategy_id')}: "
            f"성공={case.get('advice_success')} "
            f"교훈={case.get('lesson') or '기록된 교훈 없음'}"
        )
    return " ".join(lines)


def _memory_pattern_summary(memory_context: Dict[str, Any] | None) -> str:
    if not memory_context:
        return "Experience Memory가 없어 반복 패턴을 확인하지 못했습니다."
    confidence = memory_context.get("confidence", "low")
    data_sufficiency = memory_context.get("data_sufficiency", "insufficient")
    lessons = [
        case.get("lesson")
        for case in memory_context.get("retrieved_cases", [])
        if case.get("lesson")
    ]
    if not lessons:
        return (
            f"data_sufficiency={data_sufficiency}, confidence={confidence}입니다. "
            "재사용 가능한 성공/실패 패턴이 부족합니다."
        )
    return (
        f"data_sufficiency={data_sufficiency}, confidence={confidence}. "
        f"반복 교훈: {lessons[0]}"
    )


def _improvement_summary(advice: Iterable[AdviceItem]) -> str:
    items = list(advice)
    if not items:
        return "현재 자동 생성된 개선 제안이 없습니다. 먼저 백테스트 입력과 리스크 조건을 보강해야 합니다."
    lines = []
    for item in items[:3]:
        change = ""
        if item.proposed_change is not None:
            change = f" 제안 변경: {item.proposed_change.description or item.proposed_change.field}."
        lines.append(f"{item.title}: {item.body}{change}")
    return " ".join(lines)


def _retest_summary(
    req: AdvisorRequest,
    candidate_strategy: Dict[str, Any] | None,
    suggested_experiments: Sequence[str],
) -> str:
    conditions = [
        "동일 기간, 동일 유니버스, 동일 초기자금, 동일 거래비용/슬리피지 조건으로 비교해야 합니다.",
    ]
    if candidate_strategy is not None:
        conditions.append("candidate_strategy를 개선 후보로 재백테스트해야 합니다.")
    else:
        conditions.append("아직 개선 후보 DSL이 없어 후보 생성 후 재백테스트가 필요합니다.")
    if req.candidate_backtest_result is None:
        conditions.append("개선 후 백테스트 결과가 없어 조언 성공 여부는 미확정입니다.")
    if suggested_experiments:
        conditions.append(f"우선 실험: {suggested_experiments[0]}")
    return " ".join(conditions)


def _warning_summary(req: AdvisorRequest, advice_evaluation: Dict[str, Any] | None) -> str:
    warnings = [
        "CAGR만으로 성공을 판단하지 말고 MDD, Sharpe, Calmar, 거래 횟수, 비용 반영 결과를 함께 봐야 합니다.",
        "초기자금 대비 과도한 유동성 필터나 잦은 매매는 개인 투자자에게 비현실적일 수 있습니다.",
    ]
    if req.backtest_result is None:
        warnings.append("현재 백테스트 결과가 없으므로 수익성 표현은 금지합니다.")
    if advice_evaluation:
        warnings.append(
            f"평가 결과 net_effect={advice_evaluation.get('net_effect')}이며 "
            f"OOS 필요={advice_evaluation.get('oos_validation_required')}입니다."
        )
    else:
        warnings.append("OOS 또는 Walk-forward 검증 전에는 확정적 추천을 하지 않습니다.")
    return " ".join(warnings)


def _final_recommendation(advice: Sequence[AdviceItem], advice_evaluation: Dict[str, Any] | None) -> str:
    if advice_evaluation and advice_evaluation.get("net_effect") == "positive":
        return "개선 전/후 백테스트에서 위험 대비 성과 개선이 유지되는지 OOS 검증을 먼저 완료하세요."
    if advice:
        return f"가장 먼저 '{advice[0].title}' 항목을 검증 가능한 후보 전략으로 만들고 재백테스트하세요."
    return "전략 조건과 백테스트 설정을 먼저 완성한 뒤 RAG 검색과 재백테스트를 다시 실행하세요."


def compose_response_sections(
    req: AdvisorRequest,
    issues: Sequence[Issue],
    advice: Sequence[AdviceItem],
    memory_context: Dict[str, Any] | None,
    candidate_strategy: Dict[str, Any] | None,
    advice_evaluation: Dict[str, Any] | None,
    suggested_experiments: Sequence[str],
) -> List[ResponseSection]:
    bodies = [
        _strategy_summary(req),
        _problem_summary(issues),
        _similar_case_summary(memory_context),
        _memory_pattern_summary(memory_context),
        _improvement_summary(advice),
        _retest_summary(req, candidate_strategy, suggested_experiments),
        _warning_summary(req, advice_evaluation),
        _final_recommendation(advice, advice_evaluation),
    ]
    return [
        ResponseSection(title=title, body=body)
        for title, body in zip(SECTION_TITLES, bodies)
    ]
