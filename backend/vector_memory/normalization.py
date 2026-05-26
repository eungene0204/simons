"""Backtest result normalization and embedding document rendering."""

from __future__ import annotations

import json
from typing import Any

from .identity import strategy_hash_for, strategy_memory_id
from .models import NormalizedBacktestMemory, PrimitiveMetadata, VectorMemoryDocument


METRIC_KEYS = {
    "return_": ("return", "total_return", "totalReturn"),
    "CAGR": ("CAGR", "cagr"),
    "Sharpe": ("Sharpe", "sharpe"),
    "Sortino": ("Sortino", "sortino"),
    "Calmar": ("Calmar", "calmar", "calmarRatio"),
    "WinRate": ("WinRate", "win_rate", "winRate"),
    "ProfitFactor": ("ProfitFactor", "profit_factor", "profitFactor"),
    "MDD": ("MDD", "mdd", "maxDrawdown"),
    "volatility": ("volatility", "Volatility"),
    "turnover": ("turnover", "Turnover"),
    "tradeCount": ("tradeCount", "trade_count", "trades"),
    "averageHoldingDays": ("averageHoldingDays", "average_holding_days", "avgHoldingDays"),
}

RISK_KEYS = (
    "stop_loss_pct",
    "take_profit_pct",
    "trailing_stop_pct",
    "max_positions",
    "hold_period_days",
    "max_holding_days",
    "position_size_pct",
)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _first_metric(metrics: dict[str, Any], key: str) -> Any:
    for candidate in METRIC_KEYS[key]:
        if candidate in metrics:
            return metrics[candidate]
    return None


def _stringify_condition(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_indicator(value: Any) -> str:
    return str(value or "").strip().lower()


def _extract_signals(strategy_dsl: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = strategy_dsl.get(key)
    if isinstance(value, dict):
        value = value.get("conditions")
    return [item for item in value or [] if isinstance(item, dict)]


def _extract_indicators(strategy_dsl: dict[str, Any]) -> list[str]:
    indicators: set[str] = set()
    for key in ("entry_signals", "entry", "exit_signals", "exit"):
        for signal in _extract_signals(strategy_dsl, key):
            indicator = _normalize_indicator(signal.get("indicator") or signal.get("type") or signal.get("metric"))
            if indicator:
                indicators.add(indicator)
    for item in strategy_dsl.get("fundamental_filters") or []:
        if isinstance(item, dict):
            metric = _normalize_indicator(item.get("metric"))
            if metric:
                indicators.add(metric)
    return sorted(indicators)


def _extract_risk_management(strategy_dsl: dict[str, Any]) -> dict[str, Any]:
    risk = strategy_dsl.get("risk") if isinstance(strategy_dsl.get("risk"), dict) else {}
    result: dict[str, Any] = {}
    for key in RISK_KEYS:
        if key in strategy_dsl:
            result[key] = strategy_dsl[key]
        elif key in risk:
            result[key] = risk[key]
    return result


def _list_text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def normalize_backtest_result(
    *,
    strategy_dsl: dict[str, Any],
    metrics: dict[str, Any],
    strategy_summary: str = "",
    market_regime: str = "",
    sector_bias: list[str] | None = None,
    failure_reason: str = "",
    success_reason: str = "",
    strategy_version: str = "v1",
) -> NormalizedBacktestMemory:
    strategy_dsl = strategy_dsl or {}
    metrics = metrics or {}
    risk_management = _extract_risk_management(strategy_dsl)
    holding_period = (
        strategy_dsl.get("holdingPeriod")
        or strategy_dsl.get("holding_period")
        or strategy_dsl.get("hold_period_days")
        or risk_management.get("hold_period_days")
        or risk_management.get("max_holding_days")
    )
    rebalance_frequency = (
        strategy_dsl.get("rebalanceFrequency")
        or strategy_dsl.get("rebalance_frequency")
        or strategy_dsl.get("timeframe")
        or strategy_dsl.get("interval")
        or ""
    )
    capital = (
        strategy_dsl.get("capital")
        or strategy_dsl.get("initial_capital")
        or strategy_dsl.get("initialCapital")
        or metrics.get("capital")
        or metrics.get("initialCapital")
    )

    return NormalizedBacktestMemory(
        strategyDsl=strategy_dsl,
        strategySummary=strategy_summary or str(strategy_dsl.get("description") or ""),
        indicators=_extract_indicators(strategy_dsl),
        entryConditions=[_stringify_condition(item) for item in _extract_signals(strategy_dsl, "entry_signals") + _extract_signals(strategy_dsl, "entry")],
        exitConditions=[_stringify_condition(item) for item in _extract_signals(strategy_dsl, "exit_signals") + _extract_signals(strategy_dsl, "exit")],
        riskManagement=risk_management,
        marketRegime=market_regime or str(strategy_dsl.get("marketRegime") or strategy_dsl.get("market_regime") or ""),
        sectorBias=sector_bias if sector_bias is not None else _list_text(strategy_dsl.get("sectorBias") or strategy_dsl.get("sector_bias")),
        holdingPeriod=_as_int(holding_period),
        rebalanceFrequency=str(rebalance_frequency),
        capital=_as_float(capital),
        return_=_as_float(_first_metric(metrics, "return_")),
        CAGR=_as_float(_first_metric(metrics, "CAGR")),
        Sharpe=_as_float(_first_metric(metrics, "Sharpe")),
        Sortino=_as_float(_first_metric(metrics, "Sortino")),
        Calmar=_as_float(_first_metric(metrics, "Calmar")),
        WinRate=_as_float(_first_metric(metrics, "WinRate")),
        ProfitFactor=_as_float(_first_metric(metrics, "ProfitFactor")),
        MDD=_as_float(_first_metric(metrics, "MDD")),
        volatility=_as_float(_first_metric(metrics, "volatility")),
        turnover=_as_float(_first_metric(metrics, "turnover")),
        tradeCount=_as_int(_first_metric(metrics, "tradeCount")),
        averageHoldingDays=_as_float(_first_metric(metrics, "averageHoldingDays")),
        failureReason=failure_reason or str(metrics.get("failureReason") or metrics.get("failure_reason") or ""),
        successReason=success_reason or str(metrics.get("successReason") or metrics.get("success_reason") or ""),
        strategyVersion=strategy_version,
    )


def build_embedding_text(record: NormalizedBacktestMemory) -> str:
    payload = record.to_payload()
    return "\n".join(
        [
            f"Strategy DSL: {json.dumps(record.strategyDsl, ensure_ascii=False, sort_keys=True)}",
            f"Strategy summary: {record.strategySummary}",
            f"Indicators: {', '.join(record.indicators)}",
            f"Entry conditions: {' | '.join(record.entryConditions)}",
            f"Exit conditions: {' | '.join(record.exitConditions)}",
            f"Risk management: {json.dumps(record.riskManagement, ensure_ascii=False, sort_keys=True)}",
            f"Market regime: {record.marketRegime}",
            f"Sector bias: {', '.join(record.sectorBias)}",
            f"Performance summary: return={payload['return']}, CAGR={record.CAGR}, Sharpe={record.Sharpe}, Sortino={record.Sortino}, Calmar={record.Calmar}, WinRate={record.WinRate}, ProfitFactor={record.ProfitFactor}, MDD={record.MDD}, volatility={record.volatility}, turnover={record.turnover}, tradeCount={record.tradeCount}, averageHoldingDays={record.averageHoldingDays}",
            f"Failure reason: {record.failureReason}",
            f"Success reason: {record.successReason}",
        ]
    )


def _risk_level(record: NormalizedBacktestMemory) -> str:
    if record.MDD <= -0.30 or record.volatility >= 0.35:
        return "high"
    if record.MDD <= -0.15 or record.volatility >= 0.20:
        return "medium"
    return "low"


def _metadata(record: NormalizedBacktestMemory) -> dict[str, PrimitiveMetadata]:
    strategy_hash = strategy_hash_for(record.strategyDsl)
    return {
        "strategy_hash": strategy_hash,
        "strategy_version": record.strategyVersion,
        "return": record.return_,
        "sharpe": record.Sharpe,
        "sortino": record.Sortino,
        "cagr": record.CAGR,
        "mdd": record.MDD,
        "win_rate": record.WinRate,
        "profit_factor": record.ProfitFactor,
        "volatility": record.volatility,
        "turnover": record.turnover,
        "trade_count": record.tradeCount,
        "marketRegime": record.marketRegime,
        "sectorBias": ",".join(record.sectorBias),
        "indicators": ",".join(record.indicators),
        "holdingPeriod": record.holdingPeriod,
        "rebalanceFrequency": record.rebalanceFrequency,
        "capital": record.capital,
        "riskLevel": _risk_level(record),
        "failureReason": record.failureReason,
        "successReason": record.successReason,
    }


def build_vector_document(record: NormalizedBacktestMemory) -> VectorMemoryDocument:
    strategy_hash = strategy_hash_for(record.strategyDsl)
    return VectorMemoryDocument(
        id=strategy_memory_id(record.strategyDsl, strategy_version=record.strategyVersion),
        strategy_hash=strategy_hash,
        document=build_embedding_text(record),
        metadata=_metadata(record),
    )
