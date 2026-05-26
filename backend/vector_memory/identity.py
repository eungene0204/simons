"""Stable identity helpers for strategy vector memory records."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from typing import Any


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
}


def _normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_for_hash(inner)
            for key, inner in sorted(value.items())
            if key not in VOLATILE_KEYS and inner is not None
        }
    if isinstance(value, list):
        return [_normalize_for_hash(item) for item in value]
    if isinstance(value, float):
        return float(Decimal(str(value)).normalize())
    return value


def canonical_strategy_string(strategy_dsl: dict[str, Any]) -> str:
    normalized = _normalize_for_hash(strategy_dsl or {})
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def strategy_hash_for(strategy_dsl: dict[str, Any]) -> str:
    canonical = canonical_strategy_string(strategy_dsl)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def strategy_memory_id(strategy_dsl: dict[str, Any], *, strategy_version: str = "v1") -> str:
    return f"{strategy_hash_for(strategy_dsl)}:{strategy_version}"
