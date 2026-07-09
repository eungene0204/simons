"""
FastAPI routes for Strategy Research Agent.

All routes require `planTier == 'PREMIUM'`. User identity is resolved via
`X-User-Id` header — the Next.js proxy layer is responsible for session→userId
translation. A second check on the DB `User.planTier` prevents header spoofing
reaching the agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import db

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from research.agent import AgentConfig, StrategyResearchAgent
from research.events import subscribe, unsubscribe
from research.promoter import Promoter
from research.safeguards import PrescreenGates
from research.scoring import ScoreWeights
from research.templates import TEMPLATE_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])


# ─────────────────────────────────────────────────────────
# DB access (reuse virtual_trader's DB resolution)
# ─────────────────────────────────────────────────────────


def _connect():
    return db.connect()


# ─────────────────────────────────────────────────────────
# Auth / gating
# ─────────────────────────────────────────────────────────


async def require_premium(
    x_user_id: Optional[str] = Header(default=None),
) -> int:
    if os.getenv("RESEARCH_AGENT_DISABLED") == "1":
        raise HTTPException(503, "research agent disabled")

    try:
        return int(x_user_id) if x_user_id else 1
    except ValueError:
        return 1


# ─────────────────────────────────────────────────────────
# Rate limiting
# ─────────────────────────────────────────────────────────


DAILY_BUDGET_CANDIDATES = int(os.getenv("RESEARCH_DAILY_BUDGET", "5000"))
PROMOTION_CAP = int(os.getenv("RESEARCH_PROMOTION_CAP", "5"))


def _candidates_today(conn, user_id: int) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        """
        SELECT COALESCE(SUM("totalCandidates"), 0) AS n
          FROM "ResearchRun"
         WHERE "userId" = ? AND "startedAt"::date = ?::date
        """,
        (user_id, today),
    ).fetchone()
    return int(row["n"] or 0)


# ─────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────


class CreateRunRequest(BaseModel):
    goal: Optional[str] = None
    templates: List[str] = Field(default_factory=lambda: ["momentum", "mean_reversion"])
    universes: List[List[str]] = Field(default_factory=lambda: [["KOSPI200"]])
    max_candidates: int = Field(default=100, ge=10, le=500)
    holdout_start: Optional[str] = None  # ISO date; defaults to ~6 months ago
    seed: Optional[int] = None
    optuna_trials: int = Field(default=50, ge=10, le=200)
    wfa_splits: int = Field(default=5, ge=3, le=10)


class CreateRunResponse(BaseModel):
    runId: str
    status: str


class PromoteRequest(BaseModel):
    initial_cash: float = Field(default=10_000_000.0, ge=1_000_000.0)
    strategy_name: Optional[str] = None


# ─────────────────────────────────────────────────────────
# Route handlers
# ─────────────────────────────────────────────────────────


@router.get("/templates")
async def list_templates(_: int = Depends(require_premium)) -> Dict[str, Any]:
    return {
        "templates": sorted(TEMPLATE_REGISTRY.keys()),
        "universes": [["KOSPI200"], ["KOSPI"], ["KOSDAQ"], ["KOSPI", "KOSDAQ"]],
    }


@router.post("/runs", response_model=CreateRunResponse, status_code=201)
async def create_run(
    body: CreateRunRequest,
    background: BackgroundTasks,
    request: Request,
    user_id: int = Depends(require_premium),
) -> CreateRunResponse:
    unknown = [t for t in body.templates if t not in TEMPLATE_REGISTRY]
    if unknown:
        raise HTTPException(400, f"unknown templates: {unknown}")

    conn = _connect()
    try:
        if _candidates_today(conn, user_id) >= DAILY_BUDGET_CANDIDATES:
            raise HTTPException(429, "daily research budget exceeded")

        run_id = f"run_{uuid.uuid4().hex[:16]}"
        seed = body.seed if body.seed is not None else int(uuid.uuid4().int & 0xFFFFFFFF)
        holdout_start = body.holdout_start or _default_holdout_start()

        config_blob = {
            "templates": body.templates,
            "universes": body.universes,
            "max_candidates": body.max_candidates,
            "optuna_trials": body.optuna_trials,
            "wfa_splits": body.wfa_splits,
        }

        now = db.now()
        conn.execute(
            """
            INSERT INTO "ResearchRun"
                (id, "userId", status, goal, config, "holdoutStart", seed, "startedAt", "totalCandidates", "promotedCount")
            VALUES (?, ?, 'PENDING', ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                run_id,
                user_id,
                body.goal,
                json.dumps(config_blob, ensure_ascii=False),
                holdout_start,
                seed,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Kick off background execution — one connection per task
    engine = request.app.state.backtest_engine
    background.add_task(
        _run_agent_task,
        run_id=run_id,
        engine=engine,
        body=body,
        holdout_start=holdout_start,
        seed=seed,
    )
    return CreateRunResponse(runId=run_id, status="PENDING")


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    user_id: int = Depends(require_premium),
) -> Dict[str, Any]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, status, goal, "holdoutStart", "startedAt", "finishedAt",
                   "totalCandidates", "promotedCount", "errorMessage"
              FROM "ResearchRun"
             WHERE "userId" = ?
             ORDER BY "startedAt" DESC
             LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return {"runs": [dict(r) for r in rows]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user_id: int = Depends(require_premium)) -> Dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            'SELECT * FROM "ResearchRun" WHERE id = ? AND "userId" = ?',
            (run_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "run not found")
        summary = conn.execute(
            """
            SELECT stage, COUNT(*) AS n FROM "ResearchCandidate"
             WHERE "runId" = ? GROUP BY stage
            """,
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    return {
        "run": dict(row),
        "stageSummary": {s["stage"]: s["n"] for s in summary},
    }


@router.delete("/runs/{run_id}")
async def cancel_run(run_id: str, user_id: int = Depends(require_premium)) -> Response:
    conn = _connect()
    try:
        row = conn.execute(
            'SELECT status FROM "ResearchRun" WHERE id = ? AND "userId" = ?',
            (run_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "run not found")
        if row["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            raise HTTPException(409, f"run already {row['status']}")
        conn.execute(
            'UPDATE "ResearchRun" SET status = \'CANCELLED\', "finishedAt" = ? WHERE id = ?',
            (db.now(), run_id),
        )
        conn.commit()
    finally:
        conn.close()
    return Response(status_code=204)


@router.get("/runs/{run_id}/candidates")
async def list_candidates(
    run_id: str,
    stage: Optional[str] = None,
    min_score: Optional[float] = None,
    limit: int = Query(default=50, ge=1, le=500),
    user_id: int = Depends(require_premium),
) -> Dict[str, Any]:
    conn = _connect()
    try:
        conn.execute(
            'SELECT 1 FROM "ResearchRun" WHERE id = ? AND "userId" = ?',
            (run_id, user_id),
        ).fetchone() or _raise_404()

        sql = [
            """
            SELECT id, "dslHash", template, stage, "rejectionReason",
                   "compositeScore", "robustnessScore", "deflatedSharpe",
                   "prescreenMetrics", "holdoutMetrics", "promotedAccountId", "createdAt",
                   "dslJson"
              FROM "ResearchCandidate"
             WHERE "runId" = ?
            """
        ]
        args: List[Any] = [run_id]
        if stage:
            sql.append("AND stage = ?")
            args.append(stage)
        if min_score is not None:
            sql.append('AND "compositeScore" >= ?')
            args.append(min_score)
        sql.append('ORDER BY "compositeScore" DESC NULLS LAST LIMIT ?')
        args.append(limit)
        rows = conn.execute(" ".join(sql), args).fetchall()
    finally:
        conn.close()
    return {"candidates": [dict(r) for r in rows]}


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: str, user_id: int = Depends(require_premium)) -> Dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT c.*, r."userId" AS "runUserId"
              FROM "ResearchCandidate" c
              JOIN "ResearchRun" r ON c."runId" = r.id
             WHERE c.id = ?
            """,
            (candidate_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row or row["runUserId"] != user_id:
        raise HTTPException(404, "candidate not found")
    return dict(row)


@router.post("/candidates/{candidate_id}/promote")
async def promote_candidate(
    candidate_id: str,
    body: PromoteRequest,
    user_id: int = Depends(require_premium),
) -> Dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT c.*, r."userId" AS "runUserId"
              FROM "ResearchCandidate" c
              JOIN "ResearchRun" r ON c."runId" = r.id
             WHERE c.id = ?
            """,
            (candidate_id,),
        ).fetchone()
        if not row or row["runUserId"] != user_id:
            raise HTTPException(404, "candidate not found")
        if row["stage"] != "APPROVED":
            raise HTTPException(409, f"candidate stage {row['stage']} is not APPROVED")

        promoter = Promoter(conn)
        if promoter.active_promotion_count(user_id) >= PROMOTION_CAP:
            raise HTTPException(
                429,
                f"promotion cap reached ({PROMOTION_CAP}); demote an existing strategy first",
            )

        dsl = json.loads(row["dslJson"])
        from engine.strategy_converter import to_backtest_request
        from engine.nl_parser import ParsedStrategy

        parsed = ParsedStrategy.model_validate(dsl)
        bt_req = to_backtest_request(parsed)

        # Fake Candidate shim for the promoter
        from research.generator import Candidate

        cand = Candidate(
            template=row["template"],
            dsl_hash=row["dslHash"],
            backtest_request=bt_req,
            parsed_dsl=dsl,
        )
        result = promoter.promote(
            candidate=cand,
            user_id=user_id,
            strategy_name=body.strategy_name or parsed.description[:64],
            initial_cash=body.initial_cash,
        )

        conn.execute(
            'UPDATE "ResearchCandidate" SET stage = \'PROMOTED\', "promotedAccountId" = ? WHERE id = ?',
            (result["accountId"], candidate_id),
        )
        conn.execute(
            'UPDATE "ResearchRun" SET "promotedCount" = "promotedCount" + 1 WHERE id = ?',
            (row["runId"],),
        )
        conn.commit()
    finally:
        conn.close()
    return result


@router.get("/runs/{run_id}/audit")
async def get_audit(
    run_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    user_id: int = Depends(require_premium),
) -> Dict[str, Any]:
    conn = _connect()
    try:
        conn.execute(
            'SELECT 1 FROM "ResearchRun" WHERE id = ? AND "userId" = ?',
            (run_id, user_id),
        ).fetchone() or _raise_404()
        rows = conn.execute(
            """
            SELECT id, "candidateId", level, event, payload, "createdAt"
              FROM "ResearchEvent"
             WHERE "runId" = ?
             ORDER BY "createdAt" DESC
             LIMIT ?
            """,
            (run_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return {"events": [dict(r) for r in rows]}


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, user_id: int = Depends(require_premium)) -> StreamingResponse:
    conn = _connect()
    try:
        row = conn.execute(
            'SELECT status FROM "ResearchRun" WHERE id = ? AND "userId" = ?',
            (run_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "run not found")

    queue = subscribe(run_id)

    async def event_gen():
        try:
            yield f"event: ready\ndata: {json.dumps({'runId': run_id})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                yield f"event: {msg['event']}\ndata: {json.dumps(msg, default=str)}\n\n"
                if msg["event"] in ("run_completed", "run_failed"):
                    break
        finally:
            unsubscribe(run_id, queue)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────
# Background agent runner
# ─────────────────────────────────────────────────────────


def _run_agent_task(
    run_id: str,
    engine: Any,
    body: CreateRunRequest,
    holdout_start: str,
    seed: int,
) -> None:
    conn = _connect()
    try:
        config = AgentConfig(
            holdout_start=holdout_start,
            seed=seed,
            templates=body.templates,
            universes=body.universes,
            max_candidates=body.max_candidates,
            optuna_trials=body.optuna_trials,
            wfa_splits=body.wfa_splits,
            weights=ScoreWeights(),
            prescreen_gates=PrescreenGates(),
            ai_training_cutoff=os.getenv("AI_TRAINING_CUTOFF"),
        )
        agent = StrategyResearchAgent(engine=engine, db=conn, config=config, run_id=run_id)
        agent.run()
    except Exception:  # noqa: BLE001
        logger.exception("[research_routes] agent task crashed")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────


def _default_holdout_start() -> str:
    import pandas as pd

    cutoff = pd.Timestamp.utcnow().normalize() - pd.DateOffset(months=6)
    return cutoff.strftime("%Y-%m-%d")


def _raise_404() -> None:
    raise HTTPException(404, "run not found")
