"""Attribute deterministic validation failures by reverting candidate groups."""
from collections import Counter

from .decisions import record
from .models import StrategyIntent


def _path(field):
    return field.removeprefix("strategy.").replace("[", "/").replace("]", "").replace(".", "/")


def _issues(report, patches):
    deferred = {finding["message"] for finding in report._universe_findings}
    issues = Counter(("error", message) for message in report.errors if message not in deferred)
    for question in report.clarification_questions:
        field = _path(question.field or "")
        for patch in patches:
            path = patch.path.lstrip("/")
            # A condition's factor/operator/value belong to the same candidate.
            if path.split("/")[0] in ("entry_conditions", "exit_conditions"):
                path = "/".join(path.split("/")[:2])
            if field and (field == path or field.startswith(path + "/")
                          or path.startswith(field + "/") or path.endswith("/-")
                          and field.startswith(path.rsplit("/", 1)[0] + "/")):
                issues[("missing", question.field)] += 1
                break
    return issues


def approve_domains(approval, original, current, origins, blocked, validate, apply):
    """Hold implicated groups; never parse a diagnostic sentence for ownership.

    The same real validator checks each counterfactual. Unattributed failures
    retain the caller's global safe refusal; they are never silently accepted.
    """
    blocked = set(blocked)
    diagnostics, questions = [], []

    def candidate(excluded):
        rows = [{"change_group_id": group, "status": "UNRESOLVED"} for group in excluded]
        spec, patches, expanded = approval.restore_rejected(
            original, current, origins, set(), apply, decisions=rows)
        result = validate(StrategyIntent(intent="MODIFY_STRATEGY", strategy=spec))
        return spec, patches, expanded, result

    spec, patches, blocked, result = candidate(blocked)
    # Every iteration removes at least one group. No model/search call is made.
    for _ in range(len(approval.operations)):
        failures = _issues(result.report, patches)
        if not failures:
            break
        active = {op["group"] for op in approval.operations} - blocked
        implicated = set()
        for group in sorted(active):
            try:
                _, trial_patches, _, trial = candidate(blocked | {group})
            except Exception:
                # A sequential dependency is not proof of independent approval.
                continue
            removed = failures - _issues(trial.report, trial_patches)
            if removed:
                implicated.add(group)
                for kind, value in removed:
                    if kind == "error" and value not in diagnostics:
                        from strategy_conversation.response.notice_evidence import producer
                        diagnostics.append(producer([value], "domain_approval", kind="TRANSITION")[0])
                for question in result.report.clarification_questions:
                    if ("missing", question.field) in removed and question not in questions:
                        questions.append(question)
                record("domain_validation", group, "UNRESOLVED", "DOMAIN_GROUP_HELD",
                       group_id=group, value={"removed_issues": list(removed)})
        if not implicated:
            break
        blocked.update(implicated)
        spec, patches, blocked, result = candidate(blocked)
    return spec, patches, blocked, result, diagnostics, questions


def create_domain_candidates(strategy):
    """Reuse patch groups for a new strategy; there is no previous user state."""
    from .models import PatchOp, StrategySpec
    from strategy_conversation.conversation.patch_approval import PatchApproval

    baseline = StrategySpec()
    before, after = baseline.model_dump(), strategy.model_dump()
    patches = []
    for field, value in after.items():
        if field in ("entry_conditions", "exit_conditions"):
            patches.extend(PatchOp(op="add", path=f"/{field}/-", value=c) for c in value)
        elif value != before[field]:
            if field in ("portfolio", "risk_management", "backtest"):
                patches.extend(PatchOp(op="replace", path=f"/{field}/{name}", value=item)
                               for name, item in value.items() if item != before[field].get(name))
            else:
                patches.append(PatchOp(op="replace", path=f"/{field}", value=value))
    return baseline, PatchApproval(baseline, patches)
