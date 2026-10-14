"""Ephemeral identities for sequential JSON Patch operations and atomic selection."""
from copy import deepcopy

from strategy_conversation.interpreter.decisions import digest, record
from .patch_applier import PatchError, _promote_patches_on_absent_condition

FIELDS = ("entry_conditions", "exit_conditions")


class PatchApproval:
    def __init__(self, strategy, patches, linked_pairs=()):
        self.base_hash = digest(strategy)
        self.original = list(patches)
        self.initial = {field: [f"{field}:{i}:{digest(c)[:12]}" for i, c in enumerate(getattr(strategy, field))]
                        for field in FIELDS}
        cells = deepcopy(self.initial)
        self.operations, self.owners = [], {}
        normalized = _promote_patches_on_absent_condition(strategy.model_dump(), patches)
        absent = {}
        for patch in patches:
            tokens = patch.path.split("/")[1:]
            if (patch.op == "replace" and len(tokens) == 3 and tokens[0] in FIELDS
                    and tokens[1].isdigit() and int(tokens[1]) >= len(self.initial[tokens[0]])):
                absent.setdefault((tokens[0], int(tokens[1])), []).append(patch)
        promoted_members = iter(group for group in absent.values()
                                if {p.path.rsplit("/", 1)[1]: p.value for p in group}.get("factor"))
        for ordinal, patch in enumerate(normalized):
            tokens = patch.path.split("/")[1:]
            field = tokens[0]
            operation = {"patch": patch, "field": field, "target": None,
                         "group": f"patch:{ordinal}:{digest(patch)[:12]}"}
            operation["members"] = [p for p in patches if p is patch] or next(promoted_members)
            if field in FIELDS:
                if len(tokens) == 1:
                    operation["group"] = f"list:{field}:{ordinal}"
                    values = patch.value if patch.op != "remove" else []
                    if not isinstance(values, list):
                        raise PatchError("Condition list patch is not a list")
                    operation["new_cells"] = [f"new:{ordinal}:{i}" for i in range(len(values))]
                    cells[field] = operation["new_cells"].copy()
                    for cell in cells[field]:
                        self.owners[cell] = operation["group"]
                else:
                    add = len(tokens) == 2 and (patch.op == "add" or tokens[1] == "-")
                    index = len(cells[field]) if tokens[1] == "-" else int(tokens[1])
                    if index < 0 or index > len(cells[field]) or (not add and index == len(cells[field])):
                        raise PatchError("Condition pointer has no identity")
                    if add:
                        target = f"new:{ordinal}"
                        operation["following"] = cells[field][index:].copy()
                        cells[field].insert(index, target)
                    else:
                        target = cells[field][index]
                        if len(tokens) == 2 and patch.op == "remove":
                            cells[field].pop(index)
                    operation["target"] = target
                    operation["group"] = self.owners.get(target, target)
                    self.owners[target] = operation["group"]
            self.operations.append(operation)
        self.final_cells = cells
        for left, right in linked_pairs:
            members = {operation["group"] for operation in self.operations
                       if operation["patch"] is left or operation["patch"] is right}
            if len(members) == 2:
                group = "replacement:" + digest(sorted(members))[:16]
                for operation in self.operations:
                    if operation["group"] in members:
                        operation["group"] = group
                self.owners = {cell: group if owner in members else owner for cell, owner in self.owners.items()}

    def condition_origins(self, strategy):
        origins = {}
        for field in FIELDS:
            conditions = getattr(strategy, field)
            if len(conditions) != len(self.final_cells[field]):
                raise PatchError("Normalized condition identities differ")
            origins.update({id(condition): cell for condition, cell in zip(conditions, self.final_cells[field])})
        return origins

    def bind_universe(self, universe, log):
        operations = [op for op in self.operations if op["field"] == "universe"]
        if log is None or not operations:
            return
        group = "universe:" + digest(universe)[:16]
        for operation in operations:
            operation["group"] = group
        self.bind_log(log)
        log.bind(universe, group + ":candidate", group)

    def bind_log(self, log):
        if log is None:
            return
        for operation in self.operations:
            patch = operation["patch"]
            for member in operation["members"]:
                identity = log.bindings.get(id(member))
                if identity:
                    log.bind(member, identity[0], operation["group"])
                    for row in log.results:
                        if row["candidate_id"] == identity[0]:
                            row["change_group_id"] = operation["group"]

    def select(self, blocked):
        cells, selected = deepcopy(self.initial), []
        for operation in self.operations:
            if operation["group"] in blocked:
                continue
            patch, field, target = operation["patch"], operation["field"], operation["target"]
            if field in FIELDS:
                if target is None:
                    cells[field] = operation["new_cells"].copy()
                elif "following" in operation:
                    index = next((cells[field].index(cell) for cell in operation["following"]
                                  if cell in cells[field]), len(cells[field]))
                    patch = patch.model_copy(update={"path": f"/{field}/{index}"})
                    cells[field].insert(index, target)
                else:
                    if target not in cells[field]:
                        raise PatchError("Approved patch targets an excluded condition")
                    index = cells[field].index(target)
                    suffix = patch.path.split("/")[3:]
                    patch = patch.model_copy(update={"path": f"/{field}/{index}" +
                        ("/" + "/".join(suffix) if suffix else "")})
                    if len(patch.path.split("/")) == 3 and patch.op == "remove":
                        cells[field].pop(index)
            selected.append(patch)
        return selected, cells

    def restore_rejected(self, original, current, origins, rejected_cells, apply, decisions=None):
        if digest(original) != self.base_hash:
            raise PatchError("Stale strategy at group approval")
        blocked = ({row["change_group_id"] for row in decisions if row["status"] in ("REJECT", "UNRESOLVED")}
                   if decisions is not None else {self.owners[cell] for cell in rejected_cells})
        rejected_fields = {field for field in FIELDS if any(cell in self.final_cells[field] for cell in rejected_cells)}
        # Unbound removals cannot be proved independent of a rejected add. Hold
        # those deletions, while preserving other precisely identified replacements.
        blocked.update(op["group"] for op in self.operations if op["field"] in rejected_fields
                       and op["patch"].op == "remove")
        if any(op["group"] in blocked and op["target"] is None and op["field"] in FIELDS
               for op in self.operations):
            # Other destructive whole-list writes in the same rewrite have no
            # proven independence. Preserve both old lists rather than half a rewrite.
            for op in self.operations:
                if op["target"] is None and op["field"] in FIELDS and op["patch"].op in ("replace", "remove"):
                    blocked.add(op["group"])
                    record("patch_dependency", op["patch"], "UNRESOLVED",
                           "BULK_REWRITE_DEPENDENCY_UNCONFIRMED")
        selected, cells = self.select(blocked)
        restored = apply(original, selected)
        blocked_cells = {cell for cell, owner in self.owners.items() if owner in blocked}
        live = {origins[id(condition)]: (field, condition) for field in FIELDS
                for condition in getattr(current, field) if id(condition) in origins}
        result = current.model_copy(deep=True)
        for field in {op["field"] for op in self.operations
                      if op["group"] in blocked and op["field"] not in FIELDS}:
            setattr(result, field, deepcopy(getattr(restored, field)))
        for field in FIELDS:
            values, value_cells = [], []
            for cell, baseline in zip(cells[field], getattr(restored, field)):
                if cell in blocked_cells or cell not in live:
                    values.append(baseline)
                    value_cells.append(cell)
                elif live[cell][0] == field:
                    values.append(live[cell][1])
                    value_cells.append(cell)
            moved = [(cell, condition) for cell, (role, condition) in live.items()
                     if role == field and cell not in cells[field]
                     and cell not in blocked_cells and any(cell in ids for ids in cells.values())]
            values.extend(condition for _, condition in moved)
            value_cells.extend(cell for cell, _ in moved)
            setattr(result, field, deepcopy(values))
            # Further domain/theme approval works on copies of these objects.
            # Carry the same identities across each deterministic approval step.
            origins.update({id(condition): cell for condition, cell in
                            zip(getattr(result, field), value_cells)})
        return result, selected, blocked


def committed_delta(original, current):
    """Canonical observed state difference, distinct from the model's proposals."""
    from strategy_conversation.interpreter.models import PatchOp
    before, after = original.model_dump(mode="json"), current.model_dump(mode="json")
    return [PatchOp(op="replace", path="/" + key, value=value) for key, value in after.items()
            if before.get(key) != value]
