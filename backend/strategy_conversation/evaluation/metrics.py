"""평가 지표 계산 — 케이스별 실행 결과에서 집계 지표를 산출한다(순수 함수, LLM 불필요).

핵심 지표: 사용자가 말하지 않은 값을 임의 확정하는 비율(false assumption rate),
누락을 질문 없이 넘기는 비율, 미지원 지표를 지원으로 판단하는 비율,
동일 의미 다양한 표현 성공률.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _factors_of(intent_dump: Dict[str, Any]) -> List[str]:
    strategy = intent_dump.get("strategy") or {}
    factors = [
        c.get("factor")
        for c in (strategy.get("entry_conditions") or []) + (strategy.get("exit_conditions") or [])
    ]
    return [f for f in factors if f]


def evaluate_case(case: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
    """단일 케이스 채점. outcome은 evaluator가 만든 실행 기록:
    {intent_dump, report_dump, schema_failed, repair_attempts, compiled, latency_ms, error}
    """
    expect = case.get("expect", {})
    result: Dict[str, Any] = {"id": case["id"], "category": case.get("category")}

    if outcome.get("schema_failed") or outcome.get("error"):
        result["schema_failed"] = True
        result["passed"] = False
        return result

    intent_dump = outcome["intent_dump"]
    report = outcome.get("report_dump") or {}
    checks: Dict[str, bool] = {}

    if "intent" in expect:
        allowed = expect["intent"]
        if isinstance(allowed, str):
            allowed = [allowed]
        checks["intent"] = intent_dump.get("intent") in allowed

    if "factors" in expect:
        found = set(_factors_of(intent_dump))
        checks["factors"] = set(expect["factors"]).issubset(found)

    if "thresholds" in expect:
        strategy = intent_dump.get("strategy") or {}
        conds = (strategy.get("entry_conditions") or []) + (strategy.get("exit_conditions") or [])
        by_factor = {c.get("factor"): c.get("value") for c in conds}
        checks["thresholds"] = all(
            by_factor.get(f) == v for f, v in expect["thresholds"].items()
        )

    if "missing_value_factors" in expect:
        strategy = intent_dump.get("strategy") or {}
        conds = (strategy.get("entry_conditions") or []) + (strategy.get("exit_conditions") or [])
        by_factor = {c.get("factor"): c for c in conds}
        # 누락값을 임의 확정하지 않았는지(false assumption) + 질문이 생성됐는지
        no_assumption = all(
            (by_factor.get(f) or {}).get("value") is None for f in expect["missing_value_factors"]
        )
        checks["no_false_assumption"] = no_assumption
        checks["missing_detected"] = bool(report.get("missing_fields")) \
            and bool(report.get("clarification_questions"))

    if expect.get("needs_clarification"):
        checks["needs_clarification"] = report.get("status") == "NEEDS_CLARIFICATION"

    if "status" in expect:
        checks["status"] = report.get("status") == expect["status"]

    if expect.get("unsupported_any"):
        checks["unsupported_detected"] = bool(report.get("unsupported_features")) \
            or intent_dump.get("intent") == "UNSUPPORTED_REQUEST"

    if expect.get("no_silent_substitute"):
        # 미지원 요청이 지원 지표 조건으로 둔갑하지 않았는지
        checks["no_silent_substitute"] = not outcome.get("compiled")

    if expect.get("conflict"):
        errors = report.get("errors") or []
        checks["conflict_detected"] = any("모순" in e for e in errors)

    if expect.get("ranking"):
        strategy = intent_dump.get("strategy") or {}
        checks["ranking"] = bool(strategy.get("ranking"))

    if expect.get("sectors_any"):
        strategy = intent_dump.get("strategy") or {}
        universe = strategy.get("universe") or {}
        checks["sectors"] = bool(universe.get("sectors"))

    result["checks"] = checks
    result["passed"] = all(checks.values()) if checks else True
    return result


def aggregate(case_results: List[Dict[str, Any]], outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(case_results)
    if total == 0:
        return {"total": 0}

    def _rate(count: int) -> float:
        return round(count / total, 4)

    schema_failures = sum(1 for r in case_results if r.get("schema_failed"))
    passed = sum(1 for r in case_results if r.get("passed"))

    def _check_rate(name: str) -> float | None:
        relevant = [r for r in case_results if name in (r.get("checks") or {})]
        if not relevant:
            return None
        return round(sum(1 for r in relevant if r["checks"][name]) / len(relevant), 4)

    latencies = sorted(o.get("latency_ms", 0) for o in outcomes if o.get("latency_ms"))
    repairs = [o.get("repair_attempts", 0) for o in outcomes if not o.get("schema_failed")]

    by_category: Dict[str, Dict[str, int]] = {}
    for r in case_results:
        cat = r.get("category") or "unknown"
        stats = by_category.setdefault(cat, {"total": 0, "passed": 0})
        stats["total"] += 1
        stats["passed"] += 1 if r.get("passed") else 0

    return {
        "total": total,
        "pass_rate": _rate(passed),
        "json_schema_failure_rate": _rate(schema_failures),
        "intent_classification_accuracy": _check_rate("intent"),
        "indicator_extraction_accuracy": _check_rate("factors"),
        "threshold_extraction_accuracy": _check_rate("thresholds"),
        "missing_field_detection_recall": _check_rate("missing_detected"),
        "false_assumption_rate": (
            None if _check_rate("no_false_assumption") is None
            else round(1 - _check_rate("no_false_assumption"), 4)
        ),
        "unsupported_feature_detection_accuracy": _check_rate("unsupported_detected"),
        "conflict_detection_accuracy": _check_rate("conflict_detected"),
        "llm_repair_used_rate": (
            round(sum(1 for r in repairs if r > 0) / len(repairs), 4) if repairs else None
        ),
        "latency_ms_p50": latencies[len(latencies) // 2] if latencies else None,
        "latency_ms_p95": latencies[int(len(latencies) * 0.95)] if latencies else None,
        "by_category": by_category,
    }
