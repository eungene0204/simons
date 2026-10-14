"""Structured producer evidence for every KR notice, including legacy text producers."""
from copy import deepcopy
from functools import wraps
from hashlib import sha256
import json

_SCOPES = {
    "single_asset_adjustments": ("target_symbols", "exit_signals", "hold_period_days", "rebalancing_period"),
    "single_asset_review": ("target_symbols", "entry_signals", "exit_signals", "fundamental_filters", "backtest_period"),
    "minimums": ("initial_capital", "hold_period_days", "max_positions", "backtest_period", "stop_loss_pct", "take_profit_pct"),
    "renamed_symbols": ("target_symbols",),
    "sector_grounding": ("sector", "target_symbols"),
}


class NoticeText(str):
    def __new__(cls, text, evidence=None):
        obj = super().__new__(cls, text)
        obj.evidence = evidence
        return obj


def snapshot(parsed, fields=None):
    value = parsed.model_dump(mode="json") if hasattr(parsed, "model_dump") else dict(parsed or {})
    return {field: deepcopy(item) for field, item in value.items()
            if field not in ("description", "name") and (fields is None or field in fields)}


def producer(messages, name, parsed=None, *, kind="OBSERVATION", fields=None):
    fields = fields or _SCOPES.get(name)
    bound = snapshot(parsed, fields) if parsed is not None else None
    return [NoticeText(str(message), deepcopy(getattr(message, "evidence", None)) or
                       {"producer": name, "kind": kind, "fields": bound, "scope": list(fields) if fields else None}) for message in messages]


class NoticeList(list):
    """Capture the fields each producer actually changed before its append."""
    def __init__(self, parsed, name):
        super().__init__()
        self.parsed, self.name, self.before = parsed, name, snapshot(parsed)

    def append(self, message):
        after = snapshot(self.parsed)
        changed = {field: value for field, value in after.items() if self.before.get(field) != value}
        super().append(NoticeText(message, {"producer": self.name, "kind": "OBSERVATION",
                                          "fields": changed or after}))
        self.before = after


def wrap_producer(function, name, *, kind="OBSERVATION", fields=None):
    @wraps(function)
    def wrapped(*args, **kwargs):
        messages = function(*args, **kwargs)
        parsed = next((arg for arg in args if hasattr(arg, "target_symbols")), None)
        if name == "renamed_symbols" and len(args) > 1:
            parsed = {"target_symbols": args[1]}
        return producer(messages, name, parsed, kind=kind, fields=fields)
    return wrapped


def collect(result):
    existing = list(result.get("_notice_evidence") or [])
    known = {item["text"] for item in existing}
    parsed = result.get("parsed")
    for message in result.get("notices") or []:
        text = str(message)
        if text in known:
            continue
        evidence = deepcopy(getattr(message, "evidence", None))
        if evidence is None:
            # A source without a dedicated slot receipt is bound to the observed
            # result, rather than being treated as unconditional free text.
            mode = (result.get("interpreter") or (result.get("runtime") or {}).get("interpreter") or {}).get("mode")
            transition = mode in {"primary_modify_explain", "primary_modify_unsupported",
                "primary_modify_rejected_patches", "primary_modify_required_hold",
                "primary_modify_rejected_condition_pair", "primary_modify_ambiguous_patches",
                "primary_modify_self_doubt", "primary_modify_needs_value", "primary_modify_capability_conflict"}
            evidence = {"producer": "response_projection", "kind": "TRANSITION" if transition else "RESULT_OBSERVATION",
                        "fields": None if transition else snapshot(parsed)}
        if evidence["fields"] is None and evidence["kind"] != "TRANSITION":
            evidence["fields"] = snapshot(parsed, evidence.get("scope"))
        identity = sha256(json.dumps({"text": text, **evidence}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        existing.append({"id": identity, "text": text, **evidence})
        known.add(text)
    result["_notice_evidence"] = existing
    return existing


def project(result):
    evidence = collect(result)
    final = snapshot(result.get("parsed"))
    decisions, notices = [], []
    for item in evidence:
        def matches_field(field, value):
            actual = final.get(field)
            if item["producer"] in ("renamed_symbols", "sector_grounding") and isinstance(value, list) and isinstance(actual, list):
                return all(part in actual for part in value)
            return actual == value
        matches = item["kind"] == "TRANSITION" or all(
            matches_field(field, value) for field, value in (item["fields"] or {}).items())
        decisions.append({**item, "status": "CURRENT" if matches else "STALE",
                          "reason": "FINAL_FIELDS_MATCH" if matches else "FINAL_FIELDS_CHANGED"})
        if matches:
            notices.append(item["text"])
    result["notices"] = list(dict.fromkeys(notices))
    return decisions
