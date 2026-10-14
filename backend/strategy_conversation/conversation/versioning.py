"""Durable compare-and-swap of KR draft revisions; no strategy schema or DB changes."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
import fcntl
from uuid import uuid4


def state_hash(parsed):
    from engine.nl_parser import ParsedStrategy

    value = ParsedStrategy.model_validate(parsed).model_dump(mode="json") if parsed else None
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


class RevisionConflict(Exception):
    def __init__(self, current):
        self.current = current
        super().__init__("전략이 다른 요청에서 변경됐어요. 최신 상태에서 다시 입력해 주세요.")


class RevisionLedger:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[2] / "logs" / "strategy_versions"

    @contextmanager
    def locked(self, draft_id):
        self.root.mkdir(parents=True, exist_ok=True)
        key = sha256(draft_id.encode()).hexdigest()
        path = self.root / (key + ".json")
        # Advisory locks are shared by workers/processes and released on crashes.
        with (self.root / (key + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                current = json.loads(path.read_text()) if path.exists() else None
                yield path, current
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def write(self, path, value):
        fd, temporary = tempfile.mkstemp(dir=self.root, prefix="revision-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as output:
                json.dump(value, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def begin(self, draft_id, expected_revision, expected_hash, previous):
        baseline = state_hash(previous)
        with self.locked(draft_id) as (path, current):
            if current is None:
                if expected_revision != 0 or expected_hash not in (None, baseline):
                    raise RevisionConflict(None)
                current = {"revision": 0, "state_hash": baseline, "updated_at": time.time()}
                self.write(path, current)
            elif (expected_revision != current["revision"] or expected_hash not in ((None, current["state_hash"]) if current["revision"] == 0 else (current["state_hash"],))
                  or baseline != current["state_hash"]):
                raise RevisionConflict(current)
            current["lease"] = uuid4().hex
            self.write(path, current)
            return dict(current)

    def commit(self, draft_id, ticket, parsed):
        with self.locked(draft_id) as (path, current):
            if current is None or (current["revision"], current["state_hash"], current.get("lease")) != (
                    ticket["revision"], ticket["state_hash"], ticket.get("lease")):
                raise RevisionConflict(current)
            committed = {"revision": current["revision"] + 1,
                         "state_hash": state_hash(parsed), "updated_at": time.time()}
            self.write(path, committed)
            return {"draft_id": draft_id, "revision": committed["revision"], "state_hash": committed["state_hash"]}
