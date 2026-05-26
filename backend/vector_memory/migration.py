"""Migration helpers from stored backtest rows to vector memory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Optional

from .embedding import EmbeddingClient, HashingEmbeddingClient
from .models import NormalizedBacktestMemory
from .normalization import normalize_backtest_result
from .repository import ChromaVectorMemoryRepository, VectorMemoryUnavailable
from .service import VectorMemoryService


@dataclass(frozen=True)
class VectorMigrationStats:
    scanned: int
    upserted: int
    skipped: int
    unavailable: bool = False
    error: Optional[str] = None


def load_backtest_memories(conn: sqlite3.Connection, *, limit: Optional[int] = None) -> list[NormalizedBacktestMemory]:
    if not _table_exists(conn, "Strategy") or not _table_exists(conn, "BacktestResult"):
        return []

    query = """
        SELECT Strategy.id, Strategy.name, Strategy.description, Strategy.settings,
               Strategy.strategyType, BacktestResult.summary, BacktestResult.createdAt
        FROM Strategy
        JOIN BacktestResult ON BacktestResult.strategyId = Strategy.id
        ORDER BY BacktestResult.createdAt DESC
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (int(limit),)

    rows = conn.execute(query, params).fetchall()
    records: list[NormalizedBacktestMemory] = []
    seen: set[str] = set()
    for row in rows:
        strategy_dsl = _json_loads(row["settings"], {})
        metrics = _json_loads(row["summary"], {})
        if not isinstance(strategy_dsl, dict) or not isinstance(metrics, dict):
            continue
        record = normalize_backtest_result(
            strategy_dsl=strategy_dsl,
            metrics=metrics,
            strategy_summary=str(row["description"] or row["name"] or ""),
            market_regime=str(metrics.get("marketRegime") or metrics.get("market_regime") or ""),
            failure_reason=str(metrics.get("failureReason") or metrics.get("failure_reason") or ""),
            success_reason=str(metrics.get("successReason") or metrics.get("success_reason") or ""),
            strategy_version=str(metrics.get("strategyVersion") or metrics.get("strategy_version") or "v1"),
        )
        memory_key = json.dumps(
            {
                "strategy": record.strategyDsl,
                "version": record.strategyVersion,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if memory_key in seen:
            continue
        seen.add(memory_key)
        records.append(record)
    return records


async def migrate_backtest_results(
    conn: sqlite3.Connection,
    *,
    service: VectorMemoryService,
    limit: Optional[int] = None,
) -> VectorMigrationStats:
    records = load_backtest_memories(conn, limit=limit)
    upserted = 0
    skipped = 0
    for record in records:
        try:
            await service.upsert_backtest_memory(record)
            upserted += 1
        except Exception:
            skipped += 1
    return VectorMigrationStats(scanned=len(records), upserted=upserted, skipped=skipped)


async def migrate_backtest_results_to_chroma(
    conn: sqlite3.Connection,
    *,
    persist_path: Path,
    embedding_client: Optional[EmbeddingClient] = None,
    limit: Optional[int] = None,
) -> VectorMigrationStats:
    try:
        service = VectorMemoryService(
            repository=ChromaVectorMemoryRepository(persist_path=persist_path),
            embedding_client=embedding_client or HashingEmbeddingClient(),
        )
    except VectorMemoryUnavailable as exc:
        return VectorMigrationStats(scanned=0, upserted=0, skipped=0, unavailable=True, error=str(exc))
    return await migrate_backtest_results(conn, service=service, limit=limit)


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
