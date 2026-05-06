"""
Before/after advice evaluation for backtest-based strategy improvements.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


METRIC_ALIASES = {
    "mdd": ("mdd", "max_drawdown", "maxDrawdown"),
    "cagr": ("cagr",),
    "sharpe": ("sharpe", "sharpe_ratio", "sharpeRatio"),
    "sortino": ("sortino", "sortino_ratio", "sortinoRatio"),
    "calmar": ("calmar", "calmar_ratio", "calmarRatio"),
    "profit_factor": ("profit_factor", "profitFactor"),
    "win_rate": ("win_rate", "winRate"),
    "trade_count": ("trade_count", "trades", "tradeCount"),
    "turnover": ("turnover",),
    "avg_trade_return": ("avg_trade_return", "avgTradeReturn"),
    "max_losing_streak": ("max_losing_streak", "maxConsecutiveLosses"),
}

HIGHER_IS_BETTER = {
    "cagr",
    "sharpe",
    "sortino",
    "calmar",
    "profit_factor",
    "win_rate",
    "avg_trade_return",
}

LOWER_ABS_IS_BETTER = {"mdd"}
LOWER_IS_BETTER = {"turnover", "max_losing_streak"}


def _to_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _numeric(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_metrics(value: Any) -> Dict[str, Optional[float]]:
    raw = _to_dict(value)
    normalized: Dict[str, Optional[float]] = {}
    for canonical, aliases in METRIC_ALIASES.items():
        metric_value = None
        for alias in aliases:
            if alias in raw:
                metric_value = _numeric(raw.get(alias))
                break
        normalized[canonical] = metric_value
    return normalized


def _metric_improved(metric: str, before: float, after: float) -> bool:
    if metric in HIGHER_IS_BETTER:
        return after > before
    if metric in LOWER_ABS_IS_BETTER:
        return abs(after) < abs(before)
    if metric in LOWER_IS_BETTER:
        return after < before
    return False


def compare_metrics(before: Any, after: Any) -> Dict[str, List[str]]:
    before_metrics = normalize_metrics(before)
    after_metrics = normalize_metrics(after)
    improved: List[str] = []
    worsened: List[str] = []

    for metric in METRIC_ALIASES:
        before_value = before_metrics.get(metric)
        after_value = after_metrics.get(metric)
        if before_value is None or after_value is None or before_value == after_value:
            continue
        if _metric_improved(metric, before_value, after_value):
            improved.append(metric)
        else:
            worsened.append(metric)

    return {"improved_metrics": improved, "worsened_metrics": worsened}


def _trade_count_excessive(before_metrics: Dict[str, Optional[float]], after_metrics: Dict[str, Optional[float]]) -> bool:
    before_count = before_metrics.get("trade_count")
    after_count = after_metrics.get("trade_count")
    if before_count is None or after_count is None:
        return False
    return before_count >= 10 and after_count > before_count * 2


def _overfitting_risk(context: Dict[str, Any], improved: Iterable[str], worsened: Iterable[str]) -> str:
    if context.get("oos_available") and context.get("oos_delta", 0) < -0.05:
        return "high"
    if "cagr" in improved and ("sharpe" in worsened or "mdd" in worsened):
        return "medium"
    if not context.get("oos_available", False):
        return "medium"
    return "low"


def evaluate_advice(before: Any, after: Any, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    context = context or {}
    before_metrics = normalize_metrics(before)
    after_metrics = normalize_metrics(after)
    compared = compare_metrics(before_metrics, after_metrics)
    improved = compared["improved_metrics"]
    worsened = compared["worsened_metrics"]

    excessive_trades = _trade_count_excessive(before_metrics, after_metrics)
    oos_bad = bool(context.get("oos_available") and context.get("oos_delta", 0) < -0.05)
    liquidity_bad = context.get("liquidity_check") == "fail"
    cost_bad = context.get("cost_adjusted_profitability") == "lost"
    complexity_bad = context.get("complexity_increase") == "high" and len(improved) <= 1

    success = (
        ("cagr" in improved or "mdd" in improved)
        and ("sharpe" in improved or "calmar" in improved or "sortino" in improved)
        and not excessive_trades
        and not oos_bad
        and not liquidity_bad
        and not cost_bad
        and not complexity_bad
    )

    blockers = []
    if excessive_trades:
        blockers.append("거래 횟수가 과도하게 증가했습니다.")
    if oos_bad:
        blockers.append("OOS 성능이 악화되었습니다.")
    if liquidity_bad:
        blockers.append("초기자금 대비 유동성 조건이 비현실적입니다.")
    if cost_bad:
        blockers.append("거래비용과 슬리피지 반영 후 수익성이 사라졌습니다.")
    if complexity_bad:
        blockers.append("전략 복잡도 증가 대비 성능 개선이 미미합니다.")

    if success:
        reason = "수익 또는 위험 지표와 위험 대비 수익 지표가 함께 개선되었습니다."
        net_effect = "positive"
    elif blockers:
        reason = " ".join(blockers)
        net_effect = "negative"
    elif improved and worsened:
        reason = "일부 지표는 개선되었지만 악화 지표가 함께 존재해 추가 검증이 필요합니다."
        net_effect = "neutral"
    else:
        reason = "개선 전보다 유의미한 성능 개선이 확인되지 않았습니다."
        net_effect = "negative"

    return {
        "advice_success": success,
        "improved_metrics": improved,
        "worsened_metrics": worsened,
        "net_effect": net_effect,
        "reason": reason,
        "overfitting_risk": _overfitting_risk(context, improved, worsened),
        "oos_validation_required": not context.get("oos_available", False),
    }


def build_reusable_lesson(strategy_summary: str, evaluation: Dict[str, Any]) -> str:
    if evaluation.get("advice_success"):
        improved = ", ".join(evaluation.get("improved_metrics") or [])
        return (
            f"{strategy_summary} 유형에서는 조언 적용 후 {improved or '핵심 지표'}가 개선된 사례가 있으므로, "
            "동일한 개선안을 적용할 때도 거래비용, 유동성, OOS 검증을 함께 확인해야 한다."
        )
    return (
        f"{strategy_summary} 유형에서는 {evaluation.get('reason', '개선 효과가 제한적이었다')} "
        "비슷한 전략에서는 같은 조언을 반복하기 전에 파라미터 민감도와 비용 반영 결과를 먼저 확인해야 한다."
    )
