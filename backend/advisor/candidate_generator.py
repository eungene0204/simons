"""
Candidate Strategy DSL generation from advisor ProposedChange items.

This module is deliberately pure. It does not run a backtest and does not
persist anything; orchestration layers can use the returned candidate DSL as
the input to a later backtest job.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from .schemas import AdviceItem, ProposedChange


ROOT_FIELDS = {
    "max_positions",
    "hold_period_days",
    "backtest_period",
    "stop_loss_pct",
    "take_profit_pct",
    "trailing_stop_pct",
    "max_mdd_limit_pct",
    "rebalancing_period",
}

LIST_FIELDS = {"entry_signals", "exit_signals", "fundamental_filters"}


def _change_key(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("metric") or value.get("indicator") or value.get("id") or value)
    return str(value)


def _upsert_list_item(items: List[Any], value: Any) -> List[Any]:
    key = _change_key(value)
    next_items = deepcopy(items)
    for index, item in enumerate(next_items):
        if _change_key(item) == key:
            next_items[index] = value
            return next_items
    next_items.append(value)
    return next_items


def apply_proposed_change(strategy_dsl: Dict[str, Any], change: ProposedChange) -> Dict[str, Any]:
    candidate = deepcopy(strategy_dsl or {})
    field = change.field

    if field == "_meta":
        candidate.setdefault("_validation", []).append(change.value)
        return candidate

    if field in ROOT_FIELDS:
        if change.action == "remove":
            candidate.pop(field, None)
        elif change.value is not None:
            candidate[field] = change.value
        return candidate

    if field in LIST_FIELDS:
        current = candidate.get(field) or []
        if not isinstance(current, list):
            current = []
        if change.action in {"add", "set", "modify"} and change.value is not None:
            candidate[field] = _upsert_list_item(current, deepcopy(change.value))
        elif change.action == "remove" and change.value is not None:
            remove_key = _change_key(change.value)
            candidate[field] = [item for item in current if _change_key(item) != remove_key]
        return candidate

    risk = candidate.get("risk")
    if isinstance(risk, dict) and field in risk:
        risk[field] = change.value
        candidate["risk"] = risk
    return candidate


def collect_proposed_changes(advice: Iterable[AdviceItem]) -> List[ProposedChange]:
    changes: List[ProposedChange] = []
    for item in advice:
        if item.proposed_change is not None:
            changes.append(item.proposed_change)
    return changes


def generate_candidate_strategy(
    strategy_dsl: Dict[str, Any],
    advice: Iterable[AdviceItem],
) -> Dict[str, Any] | None:
    changes = collect_proposed_changes(advice)
    if not changes:
        return None

    candidate = deepcopy(strategy_dsl or {})
    applied: List[Dict[str, Any]] = []
    for change in changes:
        before = deepcopy(candidate)
        candidate = apply_proposed_change(candidate, change)
        if candidate != before:
            applied.append({
                "field": change.field,
                "action": change.action,
                "description": change.description,
            })

    if not applied:
        return None

    candidate["_advisor_candidate"] = {
        "applied_changes": applied,
        "requires_backtest": True,
        "source": "advisor_proposed_changes",
    }
    return candidate
