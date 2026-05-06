"""
Strategy identity helpers for advisor memory retrieval.

These helpers mirror the content-addressed strategy_id rule without depending
on the backtest converter. They accept generic dict payloads from DB rows,
coach requests, or parsed strategies.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from typing import Any, Dict


VOLATILE_KEYS = {
    "id",
    "name",
    "description",
    "created_at",
    "createdAt",
    "updated_at",
    "updatedAt",
    "trace_id",
    "traceId",
    "ui_state",
    "uiState",
    "strategy_id",
    "strategyId",
    "canonical_strategy_dsl",
    "canonicalStrategyDsl",
}


def _normalize_number(value: float) -> int | float:
    try:
        normalized = Decimal(str(value)).normalize()
    except InvalidOperation:
        return value
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(normalized)


def normalize_strategy_dsl(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_strategy_dsl(inner)
            for key, inner in sorted(value.items())
            if key not in VOLATILE_KEYS and inner is not None
        }
    if isinstance(value, list):
        return [normalize_strategy_dsl(item) for item in value]
    if isinstance(value, float):
        return _normalize_number(value)
    return value


def canonical_strategy_string(strategy_dsl: Dict[str, Any]) -> str:
    normalized = normalize_strategy_dsl(strategy_dsl or {})
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def strategy_id_for(strategy_dsl: Dict[str, Any]) -> str:
    canonical = canonical_strategy_string(strategy_dsl)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def backtest_cache_key_for(strategy_id: str, backtest_config: Dict[str, Any]) -> str:
    payload = {
        "strategy_id": strategy_id,
        "backtest_config": normalize_strategy_dsl(backtest_config or {}),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
