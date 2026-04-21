"""
Research event emitter — persists to DB + streams to in-memory SSE subscribers.

Writes ResearchEvent rows via raw SQLite (bypassing Prisma client to match
the rest of the Python backend) and pushes to per-run asyncio queues for
/research/runs/{id}/stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# runId → set of asyncio.Queue
_subscribers: Dict[str, set[asyncio.Queue]] = defaultdict(set)


class EventEmitter:
    def __init__(self, db: sqlite3.Connection, run_id: str):
        self.db = db
        self.run_id = run_id

    def emit(
        self,
        event: str,
        payload: Optional[Dict[str, Any]] = None,
        level: str = "INFO",
        candidate_id: Optional[str] = None,
    ) -> None:
        payload_json = json.dumps(payload or {}, ensure_ascii=False, default=str)
        ev_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        try:
            self.db.execute(
                """
                INSERT INTO ResearchEvent (id, runId, candidateId, level, event, payload, createdAt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ev_id, self.run_id, candidate_id, level, event, payload_json, now),
            )
            self.db.commit()
        except sqlite3.Error as e:
            logger.warning(f"[EventEmitter] DB write failed: {e}")

        # Fan-out to SSE subscribers (non-blocking)
        msg = {
            "id": ev_id,
            "event": event,
            "level": level,
            "candidateId": candidate_id,
            "payload": payload or {},
            "createdAt": now,
        }
        for q in list(_subscribers.get(self.run_id, ())):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def transition(self, new_status: str) -> None:
        self.db.execute(
            "UPDATE ResearchRun SET status = ? WHERE id = ?",
            (new_status, self.run_id),
        )
        self.db.commit()
        self.emit("state_transition", {"status": new_status})


def subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1024)
    _subscribers[run_id].add(q)
    return q


def unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    _subscribers.get(run_id, set()).discard(q)
    if not _subscribers.get(run_id):
        _subscribers.pop(run_id, None)
