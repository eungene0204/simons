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

from .advice_evaluator import evaluate_advice
from .similarity import search_similar_strategies
from .strategy_identity import canonical_strategy_string, strategy_id_for
from vector_memory import (
    ChromaVectorMemoryRepository,
    HashingEmbeddingClient,
    VectorMemoryService,
    migrate_backtest_results_to_chroma,
    normalize_backtest_result,
)
from vector_memory.models import VectorMemoryMatch


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


def _uses_default_database() -> bool:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_path = os.path.join(project_root, "prisma", "prisma", "dev.db")
    return os.path.abspath(_db_path()) == os.path.abspath(default_path)


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


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _chroma_path() -> str:
    configured = os.getenv("ADVISOR_CHROMA_PATH")
    if configured:
        return configured
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "backend", "advisor", ".chroma")


def _nested_dict(value: Any, key: str) -> Dict[str, Any]:
    nested = value.get(key) if isinstance(value, dict) else None
    return nested if isinstance(nested, dict) else {}


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


def _bootstrap_timeframe(strategy_dsl: Dict[str, Any]) -> str:
    period = _nested_dict(strategy_dsl, "period")
    options = _nested_dict(strategy_dsl, "options")
    return _coerce_text(
        strategy_dsl.get("timeframe")
        or strategy_dsl.get("interval")
        or period.get("timeframe")
        or period.get("interval")
        or options.get("timeframe"),
        "1d",
    )


def _bootstrap_initial_capital(strategy_dsl: Dict[str, Any], summary: Dict[str, Any]) -> float:
    options = _nested_dict(strategy_dsl, "options")
    risk = _nested_dict(strategy_dsl, "risk")
    return _coerce_float(
        strategy_dsl.get("initial_capital")
        or strategy_dsl.get("initialCapital")
        or options.get("initialCapital")
        or options.get("initial_capital")
        or risk.get("initialCapital")
        or summary.get("initialCapital"),
        0.0,
    )


def _bootstrap_evaluation() -> Dict[str, Any]:
    return {
        "advice_success": None,
        "improved_metrics": [],
        "worsened_metrics": [],
        "net_effect": "unverified",
        "reason": "기존 단일 백테스트 결과만 bootstrap되어 조언 전/후 비교는 아직 없습니다.",
        "source": "historical_backtest_bootstrap",
        "oos_validation_required": True,
    }


def _comparison_context() -> Dict[str, Any]:
    return {
        "oos_available": False,
        "comparison_source": "historical_similar_strategy",
    }


def _bootstrap_agent_advice(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "advice_summary": "Historical backtest bootstrap only. No generated advice is attached yet.",
        "recommended_changes": [],
        "risk_warnings": summary.get("warnings") if isinstance(summary.get("warnings"), list) else [],
        "assumptions": [
            "This memory row was bootstrapped from a stored backtest result without advisor intervention.",
        ],
        "confidence": "low",
    }


def _extract_strategy_dsl_from_document(document: str) -> Dict[str, Any]:
    prefix = "Strategy DSL: "
    for line in document.splitlines():
        if line.startswith(prefix):
            value = _json_loads(line[len(prefix):], {})
            return value if isinstance(value, dict) else {}
    return {}


def _metrics_from_vector_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "return": metadata.get("return"),
        "cagr": metadata.get("cagr"),
        "mdd": metadata.get("mdd"),
        "sharpe": metadata.get("sharpe"),
        "sortino": metadata.get("sortino"),
        "profit_factor": metadata.get("profit_factor"),
        "win_rate": metadata.get("win_rate"),
        "volatility": metadata.get("volatility"),
        "turnover": metadata.get("turnover"),
        "trade_count": metadata.get("trade_count"),
    }


def _vector_memory_lesson(match: VectorMemoryMatch) -> str:
    metadata = match.metadata
    success_reason = _coerce_text(metadata.get("successReason"))
    failure_reason = _coerce_text(metadata.get("failureReason"))
    risk_level = _coerce_text(metadata.get("riskLevel"), "unknown")
    if success_reason:
        return (
            f"Vector Memory에서 검색된 유사 백테스트 사례입니다. "
            f"riskLevel={risk_level}, similarity={match.similarity_score:.3f}. "
            f"성공 원인: {success_reason}"
        )
    if failure_reason:
        return (
            f"Vector Memory에서 검색된 유사 백테스트 사례입니다. "
            f"riskLevel={risk_level}, similarity={match.similarity_score:.3f}. "
            f"실패 원인: {failure_reason}"
        )
    return (
        f"Vector Memory에서 검색된 유사 백테스트 사례입니다. "
        f"riskLevel={risk_level}, similarity={match.similarity_score:.3f}. "
        "동일 조건 재백테스트와 OOS 검증 전에는 성과를 확정하지 않습니다."
    )


def _vector_matches_to_memory_cases(
    matches: List[VectorMemoryMatch],
    retrieval_categories: Optional[Dict[str, List[str]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    strategy_cases: List[Dict[str, Any]] = []
    experiences: List[Dict[str, Any]] = []
    for match in matches:
        metadata = match.metadata
        strategy_dsl = _extract_strategy_dsl_from_document(match.document)
        metrics = _metrics_from_vector_metadata(metadata)
        strategy_id = _coerce_text(metadata.get("strategy_hash"), match.id.split(":", 1)[0])
        summary = _coerce_text(metadata.get("strategy_summary"), match.document[:240])
        categories = (retrieval_categories or {}).get(match.id, ["similar"])
        category_text = ", ".join(categories)
        strategy_cases.append({
            "strategy_id": strategy_id,
            "strategy_summary": summary,
            "strategy_dsl": strategy_dsl,
            "agent_advice_text": match.document,
            "vector_similarity_score": match.similarity_score,
            "retrieval_categories": categories,
        })
        experiences.append({
            "strategy_id": strategy_id,
            "strategy_summary": summary,
            "strategy_dsl": strategy_dsl,
            "before_backtest": metrics,
            "after_backtest": {},
            "evaluation": {
                "advice_success": None,
                "net_effect": "unverified",
                "source": "vector_memory_backtest_results",
            },
            "lesson": _vector_memory_lesson(match),
            "confidence": "medium" if match.similarity_score >= 0.55 else "low",
            "similarity_reason": (
                f"Vector memory retrieval categories={category_text}; "
                f"similarity score {match.similarity_score:.3f}"
            ),
            "retrieval_categories": categories,
        })
    return strategy_cases, experiences


def _record_filter_value(record: Any, field: str) -> Any:
    value = getattr(record, field)
    if value in ("", None, 0, 0.0):
        return None
    return value


async def _query_vector_memory_by_categories(
    service: VectorMemoryService,
    query_record: Any,
    *,
    top_k: int,
) -> Tuple[List[VectorMemoryMatch], Dict[str, List[str]]]:
    filters: List[Tuple[str, Optional[Dict[str, Any]]]] = [
        ("similar", None),
        ("successful_low_risk", {"riskLevel": "low"}),
        ("failed_high_risk", {"riskLevel": "high"}),
    ]
    market_regime = _record_filter_value(query_record, "marketRegime")
    capital = _record_filter_value(query_record, "capital")
    holding_period = _record_filter_value(query_record, "holdingPeriod")
    rebalance_frequency = _record_filter_value(query_record, "rebalanceFrequency")
    if market_regime:
        filters.append(("same_market_regime", {"marketRegime": market_regime}))
    if capital:
        filters.append(("same_capital", {"capital": capital}))
    if holding_period:
        filters.append(("same_holding_period", {"holdingPeriod": holding_period}))
    if rebalance_frequency:
        filters.append(("same_trade_frequency", {"rebalanceFrequency": rebalance_frequency}))

    by_id: Dict[str, VectorMemoryMatch] = {}
    categories: Dict[str, List[str]] = {}
    for category, where in filters:
        matches = await service.query_similar(
            record=query_record,
            top_k=top_k,
            where=where,
        )
        for match in matches:
            existing = by_id.get(match.id)
            if existing is None or match.similarity_score > existing.similarity_score:
                by_id[match.id] = match
            categories.setdefault(match.id, [])
            if category not in categories[match.id]:
                categories[match.id].append(category)

    ordered = sorted(by_id.values(), key=lambda item: item.similarity_score, reverse=True)
    return ordered[: max(top_k, len(filters))], categories


def _bootstrap_lesson(strategy_summary: str, summary: Dict[str, Any]) -> str:
    cagr = summary.get("cagr")
    sharpe = summary.get("sharpe")
    mdd = summary.get("mdd")
    if mdd is None:
        mdd = summary.get("maxDrawdown")
    if cagr is not None and cagr >= 0:
        return (
            f"{strategy_summary} 전략은 과거 백테스트에서 CAGR {cagr:g}, "
            f"MDD {mdd if mdd is not None else 'N/A'} 수준을 기록했다. "
            "단일 historical result이므로 동일 개선안을 재사용하기 전에 OOS와 비용 반영 검증이 필요하다."
        )
    return (
        f"{strategy_summary} 전략은 과거 백테스트에서 CAGR {cagr if cagr is not None else 'N/A'}, "
        f"Sharpe {sharpe if sharpe is not None else 'N/A'}로 부진했다. "
        "이 메모리는 실패 패턴 참고용이며, 원인 분해 없이 같은 구조를 반복하지 않아야 한다."
    )


def _historical_comparison_lesson(
    strategy_summary: str,
    candidate_summary: str,
    evaluation: Dict[str, Any],
) -> str:
    if evaluation.get("advice_success"):
        improved = ", ".join(evaluation.get("improved_metrics") or [])
        return (
            f"{strategy_summary}와 유사한 과거 전략 중 {candidate_summary} 사례에서 "
            f"{improved or '핵심 성과'} 개선이 확인되었다. "
            "이 패턴은 historical comparison이므로 실제 적용 전 동일 조건 재백테스트와 OOS 검증이 필요하다."
        )
    return (
        f"{strategy_summary}와 유사한 과거 전략 비교에서 {evaluation.get('reason', '개선 효과가 제한적이었다')} "
        "같은 구조의 조언을 적용하기 전에 파라미터 민감도와 비용 반영 결과를 먼저 확인해야 한다."
    )


def _comparison_agent_advice(candidate_summary: str, evaluation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "advice_summary": (
            f"Historical comparison found a similar strategy: {candidate_summary}. "
            "Use it as evidence for candidate validation, not as a final recommendation."
        ),
        "recommended_changes": [],
        "risk_warnings": [
            "Historical comparison is not a direct advisor-generated candidate backtest.",
            "OOS and cost-adjusted validation are still required.",
        ],
        "assumptions": [
            "The afterBacktest field stores the better similar historical strategy result.",
        ],
        "confidence": "medium" if evaluation.get("advice_success") else "low",
    }


def _bootstrap_experience_rows(conn: sqlite3.Connection) -> None:
    if (
        not _table_exists(conn, "Strategy")
        or not _table_exists(conn, "BacktestResult")
        or not _table_exists(conn, "AdviceExperience")
    ):
        return

    existing_count = conn.execute("SELECT COUNT(*) FROM AdviceExperience").fetchone()[0]
    if existing_count:
        return

    rows = conn.execute(
        """
        SELECT Strategy.id, Strategy.name, Strategy.description, Strategy.settings,
               BacktestResult.id AS backtestResultId,
               BacktestResult.summary, BacktestResult.createdAt
        FROM Strategy
        JOIN BacktestResult ON BacktestResult.strategyId = Strategy.id
        ORDER BY Strategy.id ASC, BacktestResult.createdAt DESC
        """
    ).fetchall()

    seen_strategy_ids: set[str] = set()
    inserted = 0
    for row in rows:
        strategy_row_id = row["id"]
        if strategy_row_id in seen_strategy_ids:
            continue
        seen_strategy_ids.add(strategy_row_id)

        strategy_dsl = _json_loads(row["settings"], {})
        summary = _json_loads(row["summary"], {})
        if not isinstance(strategy_dsl, dict) or not strategy_dsl:
            continue
        if not isinstance(summary, dict) or not summary:
            continue

        strategy_summary = row["description"] or row["name"] or strategy_row_id
        lesson = _bootstrap_lesson(strategy_summary, summary)
        evaluation = _bootstrap_evaluation()
        experience_id = f"bootstrap_{row['backtestResultId']}"

        conn.execute(
            """
            INSERT OR IGNORE INTO AdviceExperience (
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
                strategy_row_id,
                _coerce_text(row["createdAt"], datetime.now(timezone.utc).isoformat()),
                strategy_dsl.get("market"),
                _stringify_field(strategy_dsl.get("universe") or strategy_dsl.get("symbols")),
                _bootstrap_initial_capital(strategy_dsl, summary),
                _bootstrap_timeframe(strategy_dsl),
                strategy_summary,
                strategy_summary,
                _json_dumps(strategy_dsl),
                canonical_strategy_string(strategy_dsl),
                strategy_id_for(strategy_dsl),
                _json_dumps([]),
                _json_dumps([]),
                _json_dumps(_bootstrap_agent_advice(summary)),
                _json_dumps(summary),
                None,
                _json_dumps(evaluation),
                lesson,
                "low",
                "bootstrap_backtest_only",
            ),
        )
        inserted += 1

    if inserted:
        conn.commit()


def _load_bootstrap_experiences(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, strategyId, userPrompt, strategySummary, strategyDsl,
               beforeBacktest, afterBacktest
        FROM AdviceExperience
        WHERE dataCoverage IN ('bootstrap_backtest_only', 'bootstrap_historical_comparison')
        """
    ).fetchall()

    experiences: List[Dict[str, Any]] = []
    for row in rows:
        strategy_dsl = _json_loads(row["strategyDsl"], {})
        before = _json_loads(row["beforeBacktest"], {})
        if not isinstance(strategy_dsl, dict) or not isinstance(before, dict) or not before:
            continue
        experiences.append({
            "id": row["id"],
            "strategy_id": row["strategyId"],
            "user_prompt": row["userPrompt"] or "",
            "strategy_summary": row["strategySummary"] or row["strategyId"],
            "strategy_dsl": strategy_dsl,
            "before_backtest": before,
            "after_backtest": _json_loads(row["afterBacktest"], {}),
        })
    return experiences


def _evaluation_rank(evaluation: Dict[str, Any]) -> Tuple[int, int, int]:
    net_effect = evaluation.get("net_effect")
    net_rank = {"positive": 3, "neutral": 2, "negative": 1}.get(net_effect, 0)
    improved = len(evaluation.get("improved_metrics") or [])
    worsened = len(evaluation.get("worsened_metrics") or [])
    return net_rank, improved, -worsened


def _best_historical_comparator(
    current: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    cases = [
        {
            "strategy_id": item["strategy_id"],
            "user_prompt": item["user_prompt"],
            "strategy_summary": item["strategy_summary"],
            "strategy_dsl": item["strategy_dsl"],
            "agent_advice_text": item["strategy_summary"],
        }
        for item in candidates
        if item["strategy_id"] != current["strategy_id"]
    ]
    similar = search_similar_strategies(
        current["user_prompt"],
        current["strategy_dsl"],
        cases,
        top_k=8,
        min_score=0.35,
        min_structure_score=0.35,
    )
    by_id = {item["strategy_id"]: item for item in candidates}

    best: Optional[Tuple[Dict[str, Any], Dict[str, Any]]] = None
    best_rank = (0, 0, 0)
    for item in similar:
        candidate = by_id.get(item.strategy_id)
        if not candidate:
            continue
        evaluation = evaluate_advice(
            current["before_backtest"],
            candidate["before_backtest"],
            _comparison_context(),
        )
        evaluation["source"] = "historical_similar_strategy"
        evaluation["comparison_strategy_id"] = candidate["strategy_id"]
        evaluation["similarity"] = {
            "text_score": item.text_score,
            "structure_score": item.structure_score,
            "combined_score": item.combined_score,
            "reason": item.similarity_reason,
        }
        rank = _evaluation_rank(evaluation)
        if rank > best_rank:
            best = candidate, evaluation
            best_rank = rank

    if best and best[1].get("net_effect") == "positive":
        return best
    return None


def _enrich_bootstrap_comparisons(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "AdviceExperience"):
        return

    experiences = _load_bootstrap_experiences(conn)
    if len(experiences) < 2:
        return

    updated = 0
    for current in experiences:
        if current.get("after_backtest"):
            continue
        best = _best_historical_comparator(current, experiences)
        if not best:
            continue

        candidate, evaluation = best
        retrieved_cases = [{
            "case_strategy_id": candidate["strategy_id"],
            "similarity_reason": evaluation["similarity"]["reason"],
            "before_metrics": current["before_backtest"],
            "after_metrics": candidate["before_backtest"],
            "lesson": _historical_comparison_lesson(
                current["strategy_summary"],
                candidate["strategy_summary"],
                evaluation,
            ),
            "advice_success": evaluation.get("advice_success"),
        }]
        lesson = retrieved_cases[0]["lesson"]
        conn.execute(
            """
            UPDATE AdviceExperience
            SET afterBacktest = ?,
                evaluation = ?,
                lesson = ?,
                retrievedCases = ?,
                agentAdvice = ?,
                confidence = ?,
                dataCoverage = ?
            WHERE id = ?
            """,
            (
                _json_dumps(candidate["before_backtest"]),
                _json_dumps(evaluation),
                lesson,
                _json_dumps(retrieved_cases),
                _json_dumps(_comparison_agent_advice(candidate["strategy_summary"], evaluation)),
                "medium",
                "bootstrap_historical_comparison",
                current["id"],
            ),
        )
        updated += 1

    if updated:
        conn.commit()


def _insert_strategy_if_absent(
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
        ON CONFLICT(id) DO NOTHING
        """,
        (
            strategy_id,
            strategy_summary[:80] or strategy_id[:12],
            strategy_summary,
            _json_dumps(strategy_dsl),
            "advisor_memory",
        ),
    )


def load_advisor_memory(limit: int = 500) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        conn = _connect()
    except sqlite3.Error:
        return [], []

    try:
        _bootstrap_experience_rows(conn)
        _enrich_bootstrap_comparisons(conn)
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


async def load_vector_advisor_memory(
    user_prompt: str,
    strategy_dsl: Dict[str, Any],
    top_k: int = 5,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Bootstrap historical backtest rows into ChromaDB and retrieve similar cases.

    This is best-effort. Missing ChromaDB, old dev databases, or locked SQLite
    files must not break advisor responses.
    """
    if not os.getenv("ADVISOR_CHROMA_PATH") and not _uses_default_database():
        return [], []

    try:
        conn = _connect()
    except sqlite3.Error:
        return [], []

    try:
        _bootstrap_experience_rows(conn)
        _enrich_bootstrap_comparisons(conn)
        migration = await migrate_backtest_results_to_chroma(
            conn,
            persist_path=_chroma_path(),
        )
        if migration.unavailable or migration.scanned == 0:
            return [], []
    except sqlite3.Error:
        conn.close()
        return [], []
    finally:
        conn.close()

    try:
        service = VectorMemoryService(
            repository=ChromaVectorMemoryRepository(persist_path=_chroma_path()),
            embedding_client=HashingEmbeddingClient(),
        )
        query_record = normalize_backtest_result(
            strategy_dsl=strategy_dsl,
            metrics={},
            strategy_summary=user_prompt,
        )
        matches, retrieval_categories = await _query_vector_memory_by_categories(
            service,
            query_record,
            top_k=top_k,
        )
    except Exception:
        return [], []
    return _vector_matches_to_memory_cases(matches, retrieval_categories)


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

        _insert_strategy_if_absent(conn, strategy_hash, summary, strategy_dsl)
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
