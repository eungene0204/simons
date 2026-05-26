"""
Compose ordered user-facing response sections for the strategy advisor.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .schemas import AdviceItem, AdvisorRequest, Issue, ResponseSection


SECTION_TITLES = [
    "전략 요약",
    "유사 전략 검색 결과",
    "유사 성공 전략 공통점",
    "유사 실패 전략 공통점",
    "시장 레짐 적합성",
    "리스크 분석",
    "과최적화 가능성",
    "전략 개선 제안",
    "추천 추가 필터",
    "다음 액션",
]


CATEGORY_LABELS = {
    "similar": "현재 전략과 유사",
    "successful_low_risk": "유사 성공/저위험",
    "failed_high_risk": "유사 실패/고위험",
    "same_market_regime": "동일 시장 레짐",
    "same_capital": "동일 자본 규모",
    "same_holding_period": "동일 보유기간",
    "same_trade_frequency": "동일 거래 빈도",
}


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


def _metric_value(metrics: Dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = metrics.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _case_metrics(case: Dict[str, Any]) -> Dict[str, Any]:
    after = case.get("after_metrics")
    if isinstance(after, dict) and after:
        return after
    before = case.get("before_metrics")
    return before if isinstance(before, dict) else {}


def _ranked_cases(cases: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def rank_key(case: Dict[str, Any]) -> tuple[float, float, float, float, float, float, float]:
        metrics = _case_metrics(case)
        sharpe = _metric_value(metrics, "sharpe", "Sharpe") or -999.0
        sortino = _metric_value(metrics, "sortino", "Sortino") or -999.0
        cagr = _metric_value(metrics, "cagr", "CAGR", "return") or -999.0
        mdd = _metric_value(metrics, "mdd", "MDD", "maxDrawdown") or -999.0
        win_rate = _metric_value(metrics, "win_rate", "winRate", "WinRate") or -999.0
        profit_factor = _metric_value(metrics, "profit_factor", "profitFactor", "ProfitFactor") or -999.0
        turnover = _metric_value(metrics, "turnover", "Turnover")
        turnover_rank = -turnover if turnover is not None else -999.0
        return (sharpe, sortino, cagr, mdd, win_rate, profit_factor, turnover_rank)

    return sorted(cases, key=rank_key, reverse=True)


def _improved_metrics(case: Dict[str, Any]) -> List[str]:
    before = case.get("before_metrics") if isinstance(case.get("before_metrics"), dict) else {}
    after = case.get("after_metrics") if isinstance(case.get("after_metrics"), dict) else {}
    improved: List[str] = []
    for key, label in (("sharpe", "Sharpe"), ("sortino", "Sortino"), ("cagr", "CAGR"), ("win_rate", "Win Rate"), ("profit_factor", "Profit Factor")):
        before_value = _metric_value(before, key)
        after_value = _metric_value(after, key)
        if before_value is not None and after_value is not None and after_value > before_value:
            improved.append(label)
    before_mdd = _metric_value(before, "mdd", "maxDrawdown")
    after_mdd = _metric_value(after, "mdd", "maxDrawdown")
    if before_mdd is not None and after_mdd is not None and after_mdd > before_mdd:
        improved.append("MDD")
    before_turnover = _metric_value(before, "turnover")
    after_turnover = _metric_value(after, "turnover")
    if before_turnover is not None and after_turnover is not None and after_turnover < before_turnover:
        improved.append("Turnover")
    return improved


def _successful_cases(cases: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        case
        for case in cases
        if case.get("advice_success") is True or _improved_metrics(case)
    ]


def _failed_cases(cases: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [case for case in cases if case.get("advice_success") is False]


def _lesson_summary(cases: Sequence[Dict[str, Any]], fallback: str) -> str:
    lessons = [
        str(case.get("lesson")).strip()
        for case in cases
        if str(case.get("lesson") or "").strip()
    ]
    if lessons:
        return " ".join(lessons[:2])
    return fallback


def _case_categories(case: Dict[str, Any]) -> List[str]:
    categories = case.get("retrieval_categories")
    return [str(item) for item in categories] if isinstance(categories, list) else []


def _cases_with_category(cases: Sequence[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    return [case for case in cases if category in _case_categories(case)]


def _category_summary(cases: Sequence[Dict[str, Any]]) -> str:
    counts: Dict[str, int] = {}
    for case in cases:
        for category in _case_categories(case):
            counts[category] = counts.get(category, 0) + 1
    if not counts:
        return "검색 범주 메타데이터 없음."
    parts = [
        f"{CATEGORY_LABELS.get(category, category)} {counts[category]}건"
        for category in CATEGORY_LABELS
        if counts.get(category)
    ]
    return "검색 범주: " + ", ".join(parts) + "."


def _similar_case_summary(memory_context: Dict[str, Any] | None) -> str:
    if not memory_context:
        return "검색된 유사 전략 수: 0개. 저장된 유사 전략 검색 결과가 없어 과거 사례가 충분한 것처럼 가정하지 않습니다."
    cases = memory_context.get("retrieved_cases") or []
    search_quality = memory_context.get("search_quality") or {}
    matched_count = int(search_quality.get("matched_count") or len(memory_context.get("similar_strategy_ids") or []))
    retrieved_count = int(search_quality.get("retrieved_count") or len(cases))
    if not cases:
        return (
            f"검색된 유사 전략 수: {matched_count}개, Experience Memory 사례: 0개. "
            "RAG 검색 결과가 부족해 현재 조언은 낮은 신뢰도의 구조 점검으로 제한합니다."
        )
    lines = []
    for case in _ranked_cases(cases)[:3]:
        metrics = _case_metrics(case)
        metric_text = (
            f"Sharpe={_metric_value(metrics, 'sharpe', 'Sharpe')}, "
            f"Sortino={_metric_value(metrics, 'sortino', 'Sortino')}, "
            f"CAGR={_metric_value(metrics, 'cagr', 'CAGR', 'return')}, "
            f"MDD={_metric_value(metrics, 'mdd', 'MDD', 'maxDrawdown')}, "
            f"Win Rate={_metric_value(metrics, 'win_rate', 'winRate', 'WinRate')}, "
            f"Profit Factor={_metric_value(metrics, 'profit_factor', 'profitFactor', 'ProfitFactor')}, "
            f"Volatility={_metric_value(metrics, 'volatility', 'Volatility')}, "
            f"Turnover={_metric_value(metrics, 'turnover', 'Turnover')}, "
            f"Trade Count={_metric_value(metrics, 'trade_count', 'tradeCount', 'trades')}"
        )
        lines.append(
            f"{case.get('case_strategy_id')}: "
            f"성공={case.get('advice_success')} "
            f"{metric_text} "
            f"교훈={case.get('lesson') or '기록된 교훈 없음'}"
        )
    return (
        f"검색된 유사 전략 수: {matched_count}개, Experience Memory 사례: {retrieved_count}개. "
        f"{_category_summary(cases)} "
        f"Sharpe, Sortino, CAGR, MDD, Win Rate, Profit Factor, Turnover 우선순위로 재정렬했습니다. "
        + " ".join(lines)
    )


def _failure_summary(memory_context: Dict[str, Any] | None) -> str:
    if not memory_context:
        return "유사 실패 전략의 공통점: 검색 근거 없음. 실패 패턴은 Experience Memory 확보 후 판단합니다."
    cases = memory_context.get("retrieved_cases") or []
    failed = _failed_cases(cases)
    high_risk = _cases_with_category(cases, "failed_high_risk")
    if high_risk:
        failed = list({id(case): case for case in failed + high_risk}.values())
    if not failed:
        return "유사 실패 전략의 공통점: 명시적으로 실패로 평가된 사례가 부족합니다. 실패 공통점은 단정하지 않습니다."
    category_note = f" 유사 실패/고위험 검색 {len(high_risk)}건을 포함했습니다." if high_risk else ""
    return (
        f"유사 실패 전략의 공통점: {_lesson_summary(failed, '기록된 실패 교훈 없음')}. "
        f"{category_note} "
        "Overfitting, Data leakage, Regime collapse, Excessive turnover, Low liquidity, Tail risk, "
        "Volatility explosion, Trend dependency, Sideways market weakness를 재백테스트에서 분리 확인해야 합니다."
    )


def _success_summary(memory_context: Dict[str, Any] | None) -> str:
    if not memory_context:
        return "유사 성공 전략의 공통점: 검색 근거 없음. 성공 가능성은 백테스트와 유사 사례 확보 전까지 판단하지 않습니다."
    cases = memory_context.get("retrieved_cases") or []
    successful = _successful_cases(cases)
    low_risk_success = _cases_with_category(cases, "successful_low_risk")
    if low_risk_success:
        successful = list({id(case): case for case in successful + low_risk_success}.values())
    if not successful:
        return "유사 성공 전략의 공통점: 검증된 성공 사례가 부족합니다. 개선 후보 백테스트 전까지 성공 가능성을 단정하지 않습니다."
    improved = sorted({metric for case in successful for metric in _improved_metrics(case)})
    metric_text = ", ".join(improved) if improved else "위험 대비 성과"
    category_note = f" 유사 성공/저위험 검색 {len(low_risk_success)}건을 포함했습니다." if low_risk_success else ""
    return (
        f"유사 성공 전략의 공통점: {_lesson_summary(successful, '기록된 성공 교훈 없음')}. "
        f"이 사례들은 조정 후 {metric_text} 개선 신호가 있었습니다.{category_note}"
    )


def _regime_summary(req: AdvisorRequest, memory_context: Dict[str, Any] | None) -> str:
    strategy = req.parsed_strategy or {}
    explicit_regime = (
        strategy.get("marketRegime")
        or strategy.get("market_regime")
        or strategy.get("regime")
        or strategy.get("market_environment")
    )
    cases = (memory_context or {}).get("retrieved_cases") or []
    same_regime_cases = _cases_with_category(cases, "same_market_regime")
    regime_values = [
        str(case.get("marketRegime") or case.get("market_regime") or "").strip()
        for case in cases
        if str(case.get("marketRegime") or case.get("market_regime") or "").strip()
    ]
    if same_regime_cases:
        return (
            f"시장 레짐별 적합성: 동일 시장 레짐으로 검색된 유사 백테스트 {len(same_regime_cases)}건이 있습니다. "
            "bull, bear, sideways, high volatility, low volatility, crisis 조건별 성과를 같은 비용 조건으로 분리 확인해야 합니다."
        )
    if regime_values:
        counts = {regime: regime_values.count(regime) for regime in sorted(set(regime_values))}
        summary = ", ".join(f"{regime} {count}건" for regime, count in counts.items())
        return (
            f"시장 레짐별 적합성: 검색 사례의 레짐 분포는 {summary}입니다. "
            "bull, bear, sideways, high volatility, low volatility, crisis 조건별 성과를 같은 비용 조건으로 분리 확인해야 합니다."
        )
    if explicit_regime:
        return (
            f"시장 레짐별 적합성: 현재 전략은 {explicit_regime} 조건으로 해석됐지만, "
            "유사 백테스트의 레짐 태그가 부족해 강한 환경과 약한 환경을 확정하지 않습니다."
        )
    return (
        "시장 레짐별 적합성: bull, bear, sideways, high volatility, low volatility, crisis 태그가 검색 근거에 부족합니다. "
        "레짐별 성과를 분리 백테스트하기 전에는 특정 시장에서 강하다고 말하지 않습니다."
    )


def _risk_summary(
    req: AdvisorRequest,
    issues: Sequence[Issue],
    advice_evaluation: Dict[str, Any] | None,
    memory_context: Dict[str, Any] | None,
) -> str:
    parts = [f"현재 전략의 위험 요소: {_problem_summary(issues)}"]
    if req.backtest_result is not None:
        bt = req.backtest_result
        parts.append(
            "현재 백테스트 지표: "
            f"Sharpe={bt.sharpe}, Sortino={bt.sortino}, CAGR={bt.cagr}, MDD={bt.mdd}, "
            f"Win Rate={bt.win_rate}, Profit Factor={bt.profit_factor}, Turnover={bt.turnover}, trades={bt.trade_count}."
        )
    else:
        parts.append("현재 백테스트 결과가 없어 Sharpe, Sortino, CAGR, MDD, Win Rate, Profit Factor, Turnover 위험을 수치로 확정하지 않습니다.")
    if advice_evaluation:
        parts.append(
            f"개선안 평가 net_effect={advice_evaluation.get('net_effect')}, "
            f"OOS 필요={advice_evaluation.get('oos_validation_required')}입니다."
        )
    else:
        parts.append("OOS 또는 Walk-forward 검증 전에는 과최적화와 레짐 의존 위험을 낮게 보지 않습니다.")
    fit_context = _fit_context_summary(memory_context)
    if fit_context:
        parts.append(fit_context)
    return " ".join(parts)


def _fit_context_summary(memory_context: Dict[str, Any] | None) -> str:
    cases = (memory_context or {}).get("retrieved_cases") or []
    if not cases:
        return ""
    parts = []
    for category in ("same_capital", "same_holding_period", "same_trade_frequency"):
        count = len(_cases_with_category(cases, category))
        if count:
            parts.append(f"{CATEGORY_LABELS[category]} {count}건")
    if not parts:
        return ""
    return " 사용자 조건 적합 검색: " + ", ".join(parts) + "."


def _overfit_summary(
    req: AdvisorRequest,
    advice: Sequence[AdviceItem],
    advice_evaluation: Dict[str, Any] | None,
) -> str:
    overfit_items = [item for item in advice if "과최적화" in item.title or "과최적화" in item.body]
    if overfit_items:
        return "과최적화 가능성: " + " ".join(f"{item.title}: {item.body}" for item in overfit_items[:2])
    if req.backtest_result is None:
        return (
            "과최적화 가능성: 현재 백테스트 결과가 없어 거래 횟수, CAGR, MDD, 필터 수 기반의 과최적화 판단을 보류합니다. "
            "Walk-forward와 OOS 구간 검증 전에는 낮은 위험으로 보지 않습니다."
        )
    if advice_evaluation:
        return (
            f"과최적화 가능성: 개선안 평가 net_effect={advice_evaluation.get('net_effect')}입니다. "
            "OOS 성과가 유지될 때만 개선안을 채택하세요."
        )
    return "과최적화 가능성: 명시적 고위험 신호는 제한적이지만, OOS 또는 Walk-forward 검증 전에는 확정하지 않습니다."


def _improvement_summary(advice: Iterable[AdviceItem]) -> str:
    items = list(advice)
    if not items:
        return "개선해야 할 조건: 현재 자동 생성된 개선 제안이 없습니다. 먼저 백테스트 입력과 리스크 조건을 보강해야 합니다."
    lines = []
    for item in items[:3]:
        change = ""
        if item.proposed_change is not None:
            change = f" 제안 변경: {item.proposed_change.description or item.proposed_change.field}."
        lines.append(f"{item.title}: {item.body}{change}")
    return "개선해야 할 조건: " + " ".join(lines)


def _recommended_filter_summary(
    req: AdvisorRequest,
    advice: Sequence[AdviceItem],
    memory_context: Dict[str, Any] | None,
) -> str:
    filter_candidates = [
        "ATR stop loss",
        "Volume filter",
        "Volatility filter",
        "Market trend filter",
        "Position sizing 개선",
        "Holding period 조정",
        "Sector filter",
        "Risk management 개선",
        "Trade frequency 감소",
        "Regime filter",
    ]
    proposed = [
        item.proposed_change.description or item.proposed_change.field
        for item in advice
        if item.proposed_change is not None
    ]
    evidence = "검색 근거가 부족하므로 각 필터는 한 번에 하나씩만 추가해 비교해야 합니다."
    cases = (memory_context or {}).get("retrieved_cases") or []
    if cases:
        evidence = f"Experience Memory {len(cases)}건과 {_category_summary(cases)} 근거로 후보 필터를 분리 검증합니다."
    if req.backtest_result is None:
        evidence += " 현재 백테스트 결과가 없어 개선 효과 수치는 아직 확정하지 않습니다."
    proposed_text = ", ".join(proposed[:3]) if proposed else "자동 proposed_change 없음"
    return (
        f"추천 추가 필터: {', '.join(filter_candidates)}. "
        f"현재 agent 제안: {proposed_text}. {evidence}"
    )


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
        return "다음 백테스트 액션: 개선 전/후 백테스트에서 위험 대비 성과 개선이 유지되는지 OOS 검증을 먼저 완료하세요."
    if advice:
        return f"다음 백테스트 액션: 가장 먼저 '{advice[0].title}' 항목을 검증 가능한 후보 전략으로 만들고 재백테스트하세요."
    return "다음 백테스트 액션: 전략 조건과 백테스트 설정을 먼저 완성한 뒤 RAG 검색과 재백테스트를 다시 실행하세요."


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
        _similar_case_summary(memory_context),
        _success_summary(memory_context),
        _failure_summary(memory_context),
        _regime_summary(req, memory_context),
        _risk_summary(req, issues, advice_evaluation, memory_context),
        _overfit_summary(req, advice, advice_evaluation),
        _improvement_summary(advice),
        _recommended_filter_summary(req, advice, memory_context),
        " ".join([
            _retest_summary(req, candidate_strategy, suggested_experiments),
            _warning_summary(req, advice_evaluation),
            _final_recommendation(advice, advice_evaluation),
        ]),
    ]
    return [
        ResponseSection(title=title, body=body)
        for title, body in zip(SECTION_TITLES, bodies)
    ]
