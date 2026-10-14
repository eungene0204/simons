"""Internal verdict records; UNRESOLVED is evidence, not implicit approval."""
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
import hashlib
import json
import inspect
from threading import Lock

_CURRENT = ContextVar("interpretation_decisions", default=None)


def digest(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class DecisionLog:
    def __init__(self):
        self.results, self.evidence, self.groups = [], [], []
        self.bindings = {}
        self.superseded = set()
        self.lock = Lock()

    def bind(self, subject, candidate_id, group_id):
        self.bindings[id(subject)] = (candidate_id, group_id)

    def record(self, stage, subject, status, reason, value=None, group_id=None):
        identity = self.bindings.get(id(subject))
        candidate = identity[0] if identity else "candidate:" + digest(subject)[:20]
        group = group_id or (identity[1] if identity else candidate)
        with self.lock:
            ref = f"evidence:{len(self.evidence)}"
            self.evidence.append({"id": ref, "value": deepcopy(value)})
            row = {"candidate_id": candidate, "change_group_id": group, "status": status,
                   "reason_code": reason, "evidence_ref": ref, "stage": stage}
            self.results.append(row)
        return row

    def status(self, group_id):
        latest = {(r["candidate_id"], r["stage"]): r for r in self.results if r["change_group_id"] == group_id
                  and r["candidate_id"] not in self.superseded}
        statuses = {r["status"] for r in latest.values()}
        return "REJECT" if "REJECT" in statuses else "UNRESOLVED" if "UNRESOLVED" in statuses or not statuses else "ACCEPT"

    def review(self):
        return [{"change_group_id": group, "status": self.status(group),
                 "conflicting_statuses": sorted({r["status"] for r in self.results if r["change_group_id"] == group}),
                 "superseded_candidates": sorted({r["candidate_id"] for r in self.results
                    if r["change_group_id"] == group and r["candidate_id"] in self.superseded}),
                 "evidence_refs": [r["evidence_ref"] for r in self.results if r["change_group_id"] == group]}
                for group in sorted({r["change_group_id"] for r in self.results})]


def current_log():
    return _CURRENT.get()


def record(stage, subject, status, reason, value=None, group_id=None):
    log = current_log()
    try:
        return log.record(stage, subject, status, reason, value, group_id) if log is not None else None
    except Exception:
        return None


def bind_conditions(strategy, approval=None):
    log = current_log()
    if log is None or strategy is None:
        return
    for field in ("entry_conditions", "exit_conditions"):
        for index, condition in enumerate(getattr(strategy, field)):
            group = (approval.owners.get(approval.final_cells[field][index], approval.final_cells[field][index]) if approval else
                     f"create:{field}:{index}")
            log.bind(condition, group + ":candidate:" + digest(condition)[:16], group)


def approve_legacy_patches(patches, verdicts):
    accepted, rejected = [], []
    for patch, allowed in zip(patches, verdicts):
        row = record("patch_application_policy", patch, "ACCEPT" if allowed else "REJECT",
                     "LEGACY_ELIGIBLE" if allowed else "LEGACY_REJECTED", {"allowed": allowed})
        # This row records the existing policy, not proof from schema validity.
        (accepted if (row["status"] == "ACCEPT" if row else allowed) else rejected).append(patch)
    return accepted, rejected


def decision_session(function):
    @wraps(function)
    def call(*args, **kwargs):
        from observability import span
        from .required_checks import RequiredChecks
        log = DecisionLog()
        log.required_checks = RequiredChecks()
        token = _CURRENT.set(log)
        try:
            with span("Interpretation decisions", "chain", local_only=True) as trace:
                try:
                    result = function(*args, **kwargs)
                    trace.local_evidence(final_primary_response=result)
                    return result
                finally:
                    trace.local_evidence(decision_results=log.results, decision_evidence=log.evidence,
                                         approval_groups=log.groups, common_review=log.review())
        finally:
            _CURRENT.reset(token)
    return call


def observed_verdict(adapter):
    """Reuse each existing validator's normalized result and preserve its return object."""
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            output = function(*args, **kwargs)
            if current_log() is not None:
                try:
                    from .decision_adapters import record_verdicts
                    bound = inspect.signature(function).bind(*args, **kwargs)
                    bound.apply_defaults()
                    record_verdicts(function.__name__, adapter, tuple(bound.arguments.values()), {}, output)
                except Exception as exc:
                    record(function.__name__, function.__name__, "UNRESOLVED", "ADAPTER_FAILED",
                           type(exc).__name__)
            return output
        return call
    return decorate
