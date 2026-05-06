"""
SQLite repository for advisor RAG + Experience Memory.

The Python backend shares the same SQLite database as Prisma, but does not use
the Prisma client. This module keeps DB access optional: missing tables or an
empty database return no memory context and skip persistence.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from .strategy_identity import canonical_strategy_string, strategy_id_for


def _db_path() -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("file:"):
        rel = db_url.replace("file:", "", 1)
        prisma_dir = os.path.join(project_root, "prisma")
        candidate = os.path.join(prisma_dir, rel)
        if os.path.exists(candidate):
            return candidate
        alt = os.path.join(project_root, rel.lstrip("./"))
        if os.path.exists(alt):
            return alt
    return os.path.join(project_root, "prisma", "prisma", "dev.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _model_dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _strategy_summary(user_prompt: str, strategy_dsl: Dict[str, Any]) -> str:
    for key in ("summary", "strategy_summary", "description", "name"):
        value = strategy_dsl.get(key)
        if value:
            return str(value)
    return user_prompt[:200]


def _stringify_field(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return _json_dumps(value)


def _confidence(response: Any) -> str:
    memory_context = response.strategy_memory_context or {}
    confidence = memory_context.get("confidence")
    if confidence in {"low", "medium", "high"}:
        return confidence
    if response.advice_evaluation:
        return "medium"
    return "low"


def _evaluation_payload(response: Any) -> Dict[str, Any]:
    if response.advice_evaluation:
        return response.advice_evaluation
    return {
        "advice_success": None,
        "improved_metrics": [],
        "worsened_metrics": [],
        "net_effect": "unverified",
        "reason": "개선 후보 백테스트 결과가 없어 조언 성공 여부를 아직 평가할 수 없습니다.",
        "overfitting_risk": response.overfit_risk,
        "oos_validation_required": True,
    }


def _lesson(strategy_summary: str, evaluation: Dict[str, Any]) -> str:
    if evaluation.get("net_effect") == "positive":
        improved = ", ".join(evaluation.get("improved_metrics") or [])
        return (
            f"{strategy_summary} 유형에서는 {improved or '핵심 지표'} 개선이 확인된 조언이라도 "
            "거래비용, 유동성, OOS 검증을 함께 재확인해야 한다."
        )
    if evaluation.get("net_effect") == "unverified":
        return (
            f"{strategy_summary} 유형의 조언은 개선 후보 백테스트 전까지 성공 사례로 재사용하지 말고, "
            "후보 전략의 비용 반영 성과와 OOS 안정성을 먼저 검증해야 한다."
        )
    return (
        f"{strategy_summary} 유형에서는 {evaluation.get('reason', '개선 효과가 제한적이었다')} "
        "비슷한 전략에서는 같은 조언을 반복하기 전에 지표별 악화 원인을 먼저 확인해야 한다."
    )


def _agent_advice_payload(response: Any, confidence: str) -> Dict[str, Any]:
    advice = response.advice or []
    recommended_changes = [
        _model_dump(item.proposed_change)
        for item in advice
        if item.proposed_change is not None
    ]
    risk_warnings = [
        item.body
        for item in advice
        if item.severity == "high" or "리스크" in item.title or "주의" in item.title
    ]
    return {
        "advice_summary": advice[0].body if advice else "",
        "recommended_changes": recommended_changes,
        "risk_warnings": risk_warnings,
        "assumptions": [
            "조언 성공 여부는 개선 후보 백테스트와 비용/슬리피지/OOS 검증 후 확정한다.",
        ],
        "confidence": confidence,
    }


def _load_strategy_cases(conn: sqlite3.Connection, limit: int) -> List[Dict[str, Any]]:
    if not _table_exists(conn, "Strategy"):
        return []

    rows = conn.execute(
        """
        SELECT id, name, description, settings
        FROM Strategy
        ORDER BY updatedAt DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    cases: List[Dict[str, Any]] = []
    for row in rows:
        cases.append({
            "strategy_id": row["id"],
            "strategy_summary": row["description"] or row["name"] or "",
            "strategy_dsl": _json_loads(row["settings"], {}),
        })
    return cases


def _load_experience_rows(
    conn: sqlite3.Connection,
    limit: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not _table_exists(conn, "AdviceExperience"):
        return [], []

    rows = conn.execute(
        """
        SELECT strategyId, userPrompt, strategySummary, strategyDsl,
               retrievedCases, beforeBacktest, afterBacktest, evaluation,
               lesson, confidence
        FROM AdviceExperience
        ORDER BY createdAt DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    strategy_cases: List[Dict[str, Any]] = []
    experiences: List[Dict[str, Any]] = []
    for row in rows:
        strategy_id = row["strategyId"]
        strategy_dsl = _json_loads(row["strategyDsl"], {})
        strategy_cases.append({
            "strategy_id": strategy_id,
            "user_prompt": row["userPrompt"] or "",
            "strategy_summary": row["strategySummary"] or "",
            "strategy_dsl": strategy_dsl,
            "agent_advice_text": row["lesson"] or "",
        })
        experiences.append({
            "strategy_id": strategy_id,
            "user_prompt": row["userPrompt"] or "",
            "strategy_summary": row["strategySummary"] or "",
            "strategy_dsl": strategy_dsl,
            "retrieved_cases": _json_loads(row["retrievedCases"], []),
            "before_backtest": _json_loads(row["beforeBacktest"], {}),
            "after_backtest": _json_loads(row["afterBacktest"], {}),
            "evaluation": _json_loads(row["evaluation"], {}),
            "lesson": row["lesson"] or "",
            "confidence": row["confidence"] or "low",
        })
    return strategy_cases, experiences


def _upsert_strategy(
    conn: sqlite3.Connection,
    strategy_id: str,
    strategy_summary: str,
    strategy_dsl: Dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO Strategy (
            id, name, description, settings, strategyType, createdAt, updatedAt
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            settings=excluded.settings,
            updatedAt=CURRENT_TIMESTAMP
        """,
        (
            strategy_id,
            strategy_summary[:80] or strategy_id[:12],
            strategy_summary,
            _json_dumps(strategy_dsl),
            "advisor_memory",
        ),
    )


def load_advisor_memory(limit: int = 100) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        conn = _connect()
    except sqlite3.Error:
        return [], []

    try:
        strategy_cases = _load_strategy_cases(conn, limit)
        experience_cases, experiences = _load_experience_rows(conn, limit)
        by_id = {
            case["strategy_id"]: case
            for case in strategy_cases
            if case.get("strategy_id")
        }
        for case in experience_cases:
            if case.get("strategy_id"):
                by_id[case["strategy_id"]] = {**by_id.get(case["strategy_id"], {}), **case}
        return list(by_id.values()), experiences
    except sqlite3.Error:
        return [], []
    finally:
        conn.close()


def save_advisor_experience(request: Any, response: Any) -> Optional[str]:
    """
    Persist one advisor interaction as reusable Experience Memory.

    This is intentionally best-effort. Advisor responses must not fail because
    a local dev DB is absent, old, locked, or missing the memory tables.
    """
    try:
        conn = _connect()
    except sqlite3.Error:
        return None

    try:
        if not _table_exists(conn, "Strategy") or not _table_exists(conn, "AdviceExperience"):
            return None

        strategy_dsl = request.parsed_strategy or {}
        strategy_hash = strategy_id_for(strategy_dsl)
        canonical_dsl = canonical_strategy_string(strategy_dsl)
        summary = _strategy_summary(request.user_prompt, strategy_dsl)
        memory_context = response.strategy_memory_context or {}
        confidence = _confidence(response)
        evaluation = _evaluation_payload(response)
        lesson = _lesson(summary, evaluation)
        now = datetime.now(timezone.utc)
        experience_id = f"exp_{strategy_hash[:16]}_{int(now.timestamp() * 1_000_000)}"

        _upsert_strategy(conn, strategy_hash, summary, strategy_dsl)
        conn.execute(
            """
            INSERT INTO AdviceExperience (
                id, strategyId, createdAt, market, universe, initialCapital,
                timeframe, userPrompt, strategySummary, strategyDsl, canonicalDsl,
                strategyHash, similarStrategyIds, retrievedCases, agentAdvice,
                beforeBacktest, afterBacktest, evaluation, lesson, confidence,
                dataCoverage
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experience_id,
                strategy_hash,
                now.isoformat(),
                strategy_dsl.get("market"),
                _stringify_field(strategy_dsl.get("universe")),
                float(strategy_dsl.get("initial_capital") or 0),
                str(strategy_dsl.get("timeframe") or "1d"),
                request.user_prompt,
                summary,
                _json_dumps(strategy_dsl),
                canonical_dsl,
                strategy_hash,
                _json_dumps(memory_context.get("similar_strategy_ids") or []),
                _json_dumps(memory_context.get("retrieved_cases") or []),
                _json_dumps(_agent_advice_payload(response, confidence)),
                _json_dumps(_model_dump(request.backtest_result) or {}),
                _json_dumps(_model_dump(request.candidate_backtest_result))
                if request.candidate_backtest_result is not None
                else None,
                _json_dumps(evaluation),
                lesson,
                confidence,
                memory_context.get("data_sufficiency"),
            ),
        )
        conn.commit()
        return experience_id
    except (sqlite3.Error, TypeError, ValueError):
        return None
    finally:
        conn.close()
