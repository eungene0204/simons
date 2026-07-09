"""Migration helpers from stored backtest rows to vector memory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

import db
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


def load_backtest_memories(
    conn: Any,
    *,
    limit: Optional[int] = None,
    include_batch_candidates: bool = True,
) -> list[NormalizedBacktestMemory]:
    return list(iter_backtest_memories(conn, limit=limit, include_batch_candidates=include_batch_candidates))


def iter_backtest_memories(
    conn: Any,
    *,
    limit: Optional[int] = None,
    include_batch_candidates: bool = True,
) -> Iterator[NormalizedBacktestMemory]:
    yielded = 0
    for record in _iter_backtest_result_memories(conn, limit=limit):
        yield record
        yielded += 1
        if limit is not None and yielded >= limit:
            return

    if not include_batch_candidates:
        return

    remaining = None if limit is None else limit - yielded
    for record in _iter_batch_candidate_memories(conn, limit=remaining):
        yield record
        yielded += 1
        if limit is not None and yielded >= limit:
            return


def load_backtest_result_memories(conn: Any, *, limit: Optional[int] = None) -> list[NormalizedBacktestMemory]:
    return list(_iter_backtest_result_memories(conn, limit=limit))


def _iter_backtest_result_memories(conn: Any, *, limit: Optional[int] = None) -> Iterator[NormalizedBacktestMemory]:
    if not _table_exists(conn, "Strategy") or not _table_exists(conn, "BacktestResult"):
        return

    query = """
        SELECT "Strategy".id, "Strategy".name, "Strategy".description, "Strategy".settings,
               "Strategy"."strategyType", "BacktestResult".summary, "BacktestResult"."createdAt"
        FROM "Strategy"
        JOIN "BacktestResult" ON "BacktestResult"."strategyId" = "Strategy".id
        ORDER BY "BacktestResult"."createdAt" DESC
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (int(limit),)

    seen: set[str] = set()
    for row in conn.execute(query, params):
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
        yield record


def load_batch_candidate_memories(conn: Any, *, limit: Optional[int] = None) -> list[NormalizedBacktestMemory]:
    return list(_iter_batch_candidate_memories(conn, limit=limit))


def _iter_batch_candidate_memories(conn: Any, *, limit: Optional[int] = None) -> Iterator[NormalizedBacktestMemory]:
    if not _table_exists(conn, "BatchRunCandidate"):
        return

    query = """
        SELECT id, "runId", "strategyId", prompt, "strategyName", status, "errorMessage",
               metrics, rank, "backtestRequest", "createdAt"
        FROM "BatchRunCandidate"
        WHERE "backtestRequest" IS NOT NULL
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (int(limit),)

    seen: set[str] = set()
    for row in conn.execute(query, params):
        request = _json_loads(row["backtestRequest"], {})
        metrics = _json_loads(row["metrics"], {})
        if not isinstance(request, dict):
            continue
        if not isinstance(metrics, dict):
            metrics = {}
        strategy_dsl = _strategy_dsl_from_batch_request(request)
        if not strategy_dsl:
            continue

        strategy_version = f"batch_candidate:{row['id']}"
        memory_key = json.dumps(
            {
                "strategy": strategy_dsl,
                "version": strategy_version,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if memory_key in seen:
            continue
        seen.add(memory_key)

        status = str(row["status"] or "")
        error_message = str(row["errorMessage"] or "")
        record = normalize_backtest_result(
            strategy_dsl=strategy_dsl,
            metrics=metrics,
            strategy_summary=str(row["prompt"] or row["strategyName"] or ""),
            market_regime=str(metrics.get("marketRegime") or metrics.get("market_regime") or ""),
            failure_reason=_batch_failure_reason(status=status, error_message=error_message),
            success_reason=_batch_success_reason(status=status, rank=row["rank"], metrics=metrics),
            strategy_version=strategy_version,
        )
        yield record


async def migrate_backtest_results(
    conn: Any,
    *,
    service: VectorMemoryService,
    limit: Optional[int] = None,
    batch_size: int = 128,
    include_batch_candidates: bool = True,
) -> VectorMigrationStats:
    records = iter_backtest_memories(conn, limit=limit, include_batch_candidates=include_batch_candidates)
    scanned = 0
    upserted = 0
    skipped = 0
    for batch in _batched(records, batch_size):
        scanned += len(batch)
        try:
            await service.upsert_backtest_memories(batch)
            upserted += len(batch)
        except Exception:
            for record in batch:
                try:
                    await service.upsert_backtest_memory(record)
                    upserted += 1
                except Exception:
                    skipped += 1
    return VectorMigrationStats(scanned=scanned, upserted=upserted, skipped=skipped)


async def migrate_backtest_results_to_chroma(
    conn: Any,
    *,
    persist_path: Path,
    embedding_client: Optional[EmbeddingClient] = None,
    limit: Optional[int] = None,
    batch_size: int = 128,
) -> VectorMigrationStats:
    try:
        repository = ChromaVectorMemoryRepository(persist_path=persist_path)
        service = VectorMemoryService(
            repository=repository,
            embedding_client=embedding_client or HashingEmbeddingClient(),
        )
    except VectorMemoryUnavailable as exc:
        return VectorMigrationStats(scanned=0, upserted=0, skipped=0, unavailable=True, error=str(exc))
    include_batch_candidates = True
    if limit is None and _count_batch_candidate_rows(conn) > 0:
        include_batch_candidates = repository.count() < _count_batch_candidate_rows(conn)
    return await migrate_backtest_results(
        conn,
        service=service,
        limit=limit,
        batch_size=batch_size,
        include_batch_candidates=include_batch_candidates,
    )


def _batched(records: Iterable[NormalizedBacktestMemory], batch_size: int) -> Iterator[list[NormalizedBacktestMemory]]:
    size = max(1, int(batch_size))
    batch: list[NormalizedBacktestMemory] = []
    for record in records:
        batch.append(record)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _table_exists(conn, table: str) -> bool:
    return db.table_exists(conn, table)


def _count_batch_candidate_rows(conn) -> int:
    if not _table_exists(conn, "BatchRunCandidate"):
        return 0
    row = conn.execute(
        'SELECT count(*) FROM "BatchRunCandidate" WHERE "backtestRequest" IS NOT NULL',
    ).fetchone()
    return int(row[0] if row else 0)


def _json_loads(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def _strategy_dsl_from_batch_request(request: dict[str, Any]) -> dict[str, Any]:
    for key in ("canonical_strategy_dsl", "canonicalStrategyDsl", "strategyDsl", "strategy_dsl", "dsl"):
        value = request.get(key)
        if isinstance(value, dict):
            return value

    dsl: dict[str, Any] = {}
    if request.get("universe_id") or request.get("universeId"):
        dsl["universe"] = [request.get("universe_id") or request.get("universeId")]
    if isinstance(request.get("entry"), dict):
        dsl["entry"] = request["entry"]
    if isinstance(request.get("exit"), dict):
        dsl["exit"] = request["exit"]
    if isinstance(request.get("risk"), dict):
        dsl["risk"] = request["risk"]
    if request.get("period"):
        dsl["backtest_period"] = request["period"]

    options = request.get("options") if isinstance(request.get("options"), dict) else {}
    for source, target in (
        ("initial_capital", "initial_capital"),
        ("initialCapital", "initial_capital"),
        ("fee_rate", "fee_rate"),
        ("slippage_rate", "slippage_rate"),
        ("execution_type", "execution_timing"),
    ):
        if source in options:
            dsl[target] = options[source]
        elif source in request:
            dsl[target] = request[source]
    return dsl


def _batch_failure_reason(*, status: str, error_message: str) -> str:
    normalized = status.lower()
    if error_message:
        return error_message
    if normalized and normalized not in {"computed", "completed", "success", "succeeded"}:
        return f"Batch candidate status={status}"
    return ""


def _batch_success_reason(*, status: str, rank: Any, metrics: dict[str, Any]) -> str:
    normalized = status.lower()
    if normalized not in {"computed", "completed", "success", "succeeded"}:
        return ""
    rank_text = f", rank={rank}" if rank is not None else ""
    return (
        "Batch candidate completed"
        f"{rank_text}, sharpe={metrics.get('sharpe', 0)}, "
        f"cagr={metrics.get('cagr', 0)}, mdd={metrics.get('maxDrawdown', metrics.get('mdd', 0))}"
    )
