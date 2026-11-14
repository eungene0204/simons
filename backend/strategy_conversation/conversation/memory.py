"""서버 쪽 대화 기억 — 초안(draft_id)별 턴 기록을 앱 DB에 남기고 다시 읽는다.

프론트 에코(previous_parsed·pending_ask …)는 '지금 상태'만 나른다. 이 기록은 그 초안에서
어떤 발화가 오갔고 실행 가능성 점검이 무엇을 봤는지를 서버가 직접 기억해, 총괄 에이전트
(planner/orchestrator.py)가 조회 도구로 읽게 한다. 판정의 근거가 아니라 참고 기록이다 —
전략 상태의 정본은 여전히 에코된 ParsedStrategy와 RevisionLedger다.

- 발화 원문이 들어가므로 Trace·triage 리포트와 같이 3일만 보관한다(쓸 때 지난 행을 지운다).
- DB 장애·테이블 부재는 기억 없음으로 강등한다 — 기억이 해석 턴을 깨면 안 된다.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("strategy_interpreter.memory")

TABLE = "StrategyConversationTurn"
RETENTION = timedelta(days=3)
RECALL_LIMIT = 6


def recall(draft_id: Optional[str], limit: int = RECALL_LIMIT) -> List[Dict[str, Any]]:
    """초안의 최근 턴 기록(오래된 것부터). 기억이 없거나 읽지 못하면 빈 목록."""
    if not draft_id:
        return []
    import db

    try:
        conn = db.connect()
        try:
            with conn:  # 읽는 턴도 기한 지난 원문을 지운다 — 쓰기가 없어도 남지 않게
                conn.execute(f'DELETE FROM "{TABLE}" WHERE "createdAt" < ?', (db.now() - RETENTION,))
            rows = conn.execute(
                f'SELECT "turn", "utterance", "question", "stateHash", "feasibility" FROM "{TABLE}" '
                'WHERE "draftId" = ? AND "createdAt" >= ? ORDER BY "turn" DESC LIMIT ?',
                (draft_id, db.now() - RETENTION, limit),
            ).fetchall()
        finally:
            conn.close()
    except (db.Error, OSError):
        logger.warning("대화 기억 조회 실패 — 기억 없음으로 진행", exc_info=True)
        return []
    return [
        {"turn": row["turn"], "utterance": row["utterance"], "question": row["question"],
         "state_hash": row["stateHash"],
         "feasibility": json.loads(row["feasibility"]) if row["feasibility"] else None}
        for row in reversed(rows)
    ]


def remember(
    draft_id: Optional[str], utterance: str, question: Optional[str], state_hash: str,
    feasibility: Optional[Dict[str, Any]] = None,
) -> None:
    """이번 턴을 기록하고 보관 기한이 지난 행을 지운다. 실패는 삼킨다."""
    if not draft_id:
        return
    import db

    try:
        conn = db.connect()
        try:
            with conn:
                conn.execute(f'DELETE FROM "{TABLE}" WHERE "createdAt" < ?', (db.now() - RETENTION,))
                turn = conn.execute(
                    f'SELECT COALESCE(MAX("turn"), 0) + 1 FROM "{TABLE}" WHERE "draftId" = ?',
                    (draft_id,),
                ).fetchone()[0]
                conn.execute(
                    f'INSERT INTO "{TABLE}" ("id", "draftId", "turn", "utterance", "question", '
                    '"stateHash", "feasibility", "createdAt") VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (uuid4().hex, draft_id, turn, utterance, question, state_hash,
                     json.dumps(feasibility, ensure_ascii=False) if feasibility else None, db.now()),
                )
        finally:
            conn.close()
    except (db.Error, OSError):
        logger.warning("대화 기억 기록 실패 — 이번 턴은 기억하지 않음", exc_info=True)


def remembered_feasibility(turns: List[Dict[str, Any]], state_hash: str) -> Optional[Dict[str, Any]]:
    """같은 전략 상태에서 이미 본 점검 결과(없으면 None) — 같은 백테스트를 다시 돌리지 않는다."""
    for turn in reversed(turns):
        if turn.get("state_hash") == state_hash and turn.get("feasibility"):
            return turn["feasibility"]
    return None
