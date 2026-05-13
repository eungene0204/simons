"""
ChromaDB-backed vector memory for historical backtest retrieval.

PostgreSQL or SQLite remains the source of truth. ChromaDB stores only compact
search documents and primitive metadata for semantic retrieval.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple

from .strategy_identity import canonical_strategy_string, strategy_id_for


COLLECTION_NAME = "backtest_results"
DEFAULT_EMBEDDING_DIMENSION = 384


class VectorMemoryUnavailable(RuntimeError):
    """Raised when ChromaDB is not installed or cannot be initialized."""


class EmbeddingClient(Protocol):
    model_version: str

    async def embed_text(self, text: str) -> List[float]:
        ...

    async def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        ...


@dataclass(frozen=True)
class VectorMemoryDocument:
    strategy_id: str
    document: str
    metadata: Dict[str, str | int | float | bool]


@dataclass(frozen=True)
class VectorMemoryMatch:
    strategy_id: str
    similarity_score: float
    document: str
    metadata: Dict[str, Any]


@dataclass(frozen=True)
class VectorMigrationStats:
    scanned: int
    upserted: int
    skipped: int
    unavailable: bool = False
    error: Optional[str] = None


class HashingEmbeddingClient:
    """
    Lightweight deterministic embedding client for local MVP operation.

    This keeps vector memory functional without an external model. It can be
    replaced by bge-m3, e5-large, or OpenAI embeddings behind the same protocol.
    """

    model_version = "local-hashing-v1"

    def __init__(self, dimension: int = DEFAULT_EMBEDDING_DIMENSION) -> None:
        self._dimension = dimension

    async def embed_text(self, text: str) -> List[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> List[float]:
        vector = [0.0] * self._dimension
        tokens = _tokenize(text)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class ChromaVectorMemoryRepository:
    def __init__(
        self,
        *,
        persist_path: Path,
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        try:
            import chromadb
        except ModuleNotFoundError as exc:
            raise VectorMemoryUnavailable("chromadb is not installed") from exc

        self._client = chromadb.PersistentClient(path=str(persist_path))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert(
        self,
        *,
        strategy_id: str,
        document: str,
        embedding: Sequence[float],
        metadata: Dict[str, str | int | float | bool],
    ) -> None:
        await asyncio.to_thread(
            self._collection.upsert,
            ids=[strategy_id],
            documents=[document],
            embeddings=[list(embedding)],
            metadatas=[metadata],
        )

    async def query_similar(
        self,
        *,
        query_embedding: Sequence[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[VectorMemoryMatch]:
        result = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[list(query_embedding)],
            n_results=max(1, min(top_k, 7)),
            where=_normalize_chroma_where(where),
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        matches: List[VectorMemoryMatch] = []
        for strategy_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            matches.append(
                VectorMemoryMatch(
                    strategy_id=str(strategy_id),
                    similarity_score=max(0.0, 1.0 - float(distance)),
                    document=str(document or ""),
                    metadata=dict(metadata or {}),
                )
            )
        return matches

    async def exists(self, *, strategy_id: str) -> bool:
        result = await asyncio.to_thread(self._collection.get, ids=[strategy_id], include=[])
        return bool(result.get("ids"))


class VectorMemoryService:
    def __init__(
        self,
        *,
        repository: ChromaVectorMemoryRepository,
        embedding_client: EmbeddingClient,
    ) -> None:
        self._repository = repository
        self._embedding_client = embedding_client

    async def upsert_document(self, item: VectorMemoryDocument) -> None:
        embedding = await self._embedding_client.embed_text(item.document)
        await self._repository.upsert(
            strategy_id=item.strategy_id,
            document=item.document,
            embedding=embedding,
            metadata=item.metadata,
        )

    async def query(
        self,
        *,
        text: str,
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[VectorMemoryMatch]:
        embedding = await self._embedding_client.embed_text(text)
        return await self._repository.query_similar(
            query_embedding=embedding,
            top_k=top_k,
            where=where,
        )


def default_chroma_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    configured = os.getenv("ADVISOR_CHROMA_PATH")
    if configured:
        return Path(configured)
    return project_root / "backend" / "advisor" / ".chroma"


def create_vector_memory_service(
    *,
    persist_path: Optional[Path] = None,
    embedding_client: Optional[EmbeddingClient] = None,
) -> VectorMemoryService:
    repository = ChromaVectorMemoryRepository(
        persist_path=persist_path or default_chroma_path(),
    )
    return VectorMemoryService(
        repository=repository,
        embedding_client=embedding_client or HashingEmbeddingClient(),
    )


def build_retrieval_query(user_prompt: str, strategy_dsl: Dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Prompt: {user_prompt}",
            f"Canonical Strategy DSL: {canonical_strategy_string(strategy_dsl)}",
        ]
    )


async def migrate_backtest_results_to_chroma(
    conn: sqlite3.Connection,
    *,
    persist_path: Optional[Path] = None,
    embedding_client: Optional[EmbeddingClient] = None,
) -> VectorMigrationStats:
    try:
        service = create_vector_memory_service(
            persist_path=persist_path,
            embedding_client=embedding_client,
        )
    except VectorMemoryUnavailable as exc:
        return VectorMigrationStats(scanned=0, upserted=0, skipped=0, unavailable=True, error=str(exc))

    documents = load_backtest_documents(conn)
    upserted = 0
    skipped = 0
    for item in documents:
        try:
            await service.upsert_document(item)
            upserted += 1
        except Exception:
            skipped += 1

    return VectorMigrationStats(scanned=len(documents), upserted=upserted, skipped=skipped)


def migrate_backtest_results_to_chroma_sync(
    conn: sqlite3.Connection,
    *,
    persist_path: Optional[Path] = None,
    embedding_client: Optional[EmbeddingClient] = None,
) -> VectorMigrationStats:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            migrate_backtest_results_to_chroma(
                conn,
                persist_path=persist_path,
                embedding_client=embedding_client,
            )
        )
    return VectorMigrationStats(
        scanned=0,
        upserted=0,
        skipped=0,
        unavailable=True,
        error="migration skipped inside running event loop",
    )


async def query_chroma_memory(
    *,
    user_prompt: str,
    strategy_dsl: Dict[str, Any],
    top_k: int = 5,
    persist_path: Optional[Path] = None,
) -> List[VectorMemoryMatch]:
    service = create_vector_memory_service(persist_path=persist_path)
    where = _metadata_filter_from_strategy(strategy_dsl)
    return await service.query(
        text=build_retrieval_query(user_prompt, strategy_dsl),
        top_k=top_k,
        where=where,
    )


def query_chroma_memory_sync(
    *,
    user_prompt: str,
    strategy_dsl: Dict[str, Any],
    top_k: int = 5,
    persist_path: Optional[Path] = None,
) -> List[VectorMemoryMatch]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            query_chroma_memory(
                user_prompt=user_prompt,
                strategy_dsl=strategy_dsl,
                top_k=top_k,
                persist_path=persist_path,
            )
        )
    return []


def load_backtest_documents(conn: sqlite3.Connection) -> List[VectorMemoryDocument]:
    if not _table_exists(conn, "Strategy") or not _table_exists(conn, "BacktestResult"):
        return []

    rows = conn.execute(
        """
        SELECT Strategy.id, Strategy.name, Strategy.description, Strategy.settings,
               Strategy.strategyType, BacktestResult.summary, BacktestResult.createdAt
        FROM Strategy
        JOIN BacktestResult ON BacktestResult.strategyId = Strategy.id
        ORDER BY BacktestResult.createdAt DESC
        """
    ).fetchall()

    documents: List[VectorMemoryDocument] = []
    seen: set[str] = set()
    for row in rows:
        strategy_dsl = _json_loads(row["settings"], {})
        summary = _json_loads(row["summary"], {})
        if not isinstance(strategy_dsl, dict) or not isinstance(summary, dict):
            continue

        strategy_hash = strategy_id_for(strategy_dsl)
        strategy_id = str(row["id"] or strategy_hash)
        if strategy_id in seen:
            continue
        seen.add(strategy_id)

        document = _build_document(
            strategy_id=strategy_id,
            name=str(row["name"] or ""),
            description=str(row["description"] or ""),
            strategy_dsl=strategy_dsl,
            metrics=summary,
        )
        documents.append(
            VectorMemoryDocument(
                strategy_id=strategy_id,
                document=document,
                metadata=_build_metadata(
                    strategy_id=strategy_id,
                    strategy_hash=strategy_hash,
                    strategy_family=str(row["strategyType"] or "unknown"),
                    strategy_dsl=strategy_dsl,
                    metrics=summary,
                    created_at=str(row["createdAt"] or datetime.now(timezone.utc).isoformat()),
                ),
            )
        )
    return documents


def vector_matches_to_memory_cases(matches: Sequence[VectorMemoryMatch]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    strategy_cases: List[Dict[str, Any]] = []
    experiences: List[Dict[str, Any]] = []
    for match in matches:
        metadata = match.metadata
        strategy_dsl = _json_loads(metadata.get("strategy_dsl"), {})
        metrics = _metrics_from_metadata(metadata)
        strategy_cases.append(
            {
                "strategy_id": match.strategy_id,
                "strategy_summary": metadata.get("strategy_summary") or match.document[:240],
                "strategy_dsl": strategy_dsl,
                "agent_advice_text": match.document,
                "vector_similarity_score": match.similarity_score,
            }
        )
        experiences.append(
            {
                "strategy_id": match.strategy_id,
                "strategy_summary": metadata.get("strategy_summary") or "",
                "strategy_dsl": strategy_dsl,
                "before_backtest": metrics,
                "after_backtest": {},
                "evaluation": {
                    "advice_success": None,
                    "net_effect": "unverified",
                    "source": "chroma_backtest_results",
                },
                "lesson": _lesson_from_match(match),
                "confidence": "medium" if match.similarity_score >= 0.55 else "low",
                "similarity_reason": f"ChromaDB vector similarity score {match.similarity_score:.3f}",
            }
        )
    return strategy_cases, experiences


def _tokenize(text: str) -> List[str]:
    normalized = text.lower()
    return [token for token in normalized.replace("_", " ").split() if token]


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


def _metric(metrics: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = metrics.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def _int_metric(metrics: Dict[str, Any], *keys: str) -> int:
    value = _metric(metrics, *keys)
    return int(value) if value is not None else 0


def _strategy_universe(strategy_dsl: Dict[str, Any]) -> str:
    value = strategy_dsl.get("universe_id") or strategy_dsl.get("universe") or strategy_dsl.get("symbols")
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value or "unknown")


def _strategy_timeframe(strategy_dsl: Dict[str, Any]) -> str:
    return str(strategy_dsl.get("timeframe") or strategy_dsl.get("interval") or "1d")


def _build_document(
    *,
    strategy_id: str,
    name: str,
    description: str,
    strategy_dsl: Dict[str, Any],
    metrics: Dict[str, Any],
) -> str:
    return "\n".join(
        [
            f"Strategy ID: {strategy_id}",
            f"Strategy summary: {description or name or strategy_id}",
            f"Indicators and rules: {_json_dumps(strategy_dsl)}",
            f"Universe: {_strategy_universe(strategy_dsl)}",
            f"Timeframe: {_strategy_timeframe(strategy_dsl)}",
            (
                "Performance metrics: "
                f"CAGR={_metric(metrics, 'cagr')}, "
                f"Total Return={_metric(metrics, 'total_return', 'totalReturn')}, "
                f"MDD={_metric(metrics, 'mdd', 'maxDrawdown')}, "
                f"Sharpe={_metric(metrics, 'sharpe')}, "
                f"Sortino={_metric(metrics, 'sortino')}, "
                f"Profit Factor={_metric(metrics, 'profit_factor', 'profitFactor')}, "
                f"Win Rate={_metric(metrics, 'win_rate', 'winRate')}, "
                f"Trade Count={_int_metric(metrics, 'trade_count', 'tradeCount', 'trades')}, "
                f"Calmar={_metric(metrics, 'calmar', 'calmar_ratio', 'calmarRatio')}"
            ),
        ]
    )


def _build_metadata(
    *,
    strategy_id: str,
    strategy_hash: str,
    strategy_family: str,
    strategy_dsl: Dict[str, Any],
    metrics: Dict[str, Any],
    created_at: str,
) -> Dict[str, str | int | float | bool]:
    cagr = _metric(metrics, "cagr")
    sharpe = _metric(metrics, "sharpe")
    mdd = _metric(metrics, "mdd", "maxDrawdown")
    return _drop_none(
        {
            "strategy_id": strategy_id,
            "strategy_hash": strategy_hash,
            "strategy_family": strategy_family,
            "strategy_summary": str(strategy_dsl.get("description") or strategy_id),
            "strategy_dsl": _json_dumps(strategy_dsl),
            "universe": _strategy_universe(strategy_dsl),
            "timeframe": _strategy_timeframe(strategy_dsl),
            "cagr": cagr,
            "mdd": mdd,
            "sharpe": sharpe,
            "profit_factor": _metric(metrics, "profit_factor", "profitFactor"),
            "win_rate": _metric(metrics, "win_rate", "winRate"),
            "trade_count": _int_metric(metrics, "trade_count", "tradeCount", "trades"),
            "result_status": _result_status(cagr=cagr, sharpe=sharpe, mdd=mdd),
            "created_at": created_at,
            "model_version": "local-hashing-v1",
            "backtest_engine_version": "unknown",
        }
    )


def _drop_none(value: Dict[str, Any]) -> Dict[str, str | int | float | bool]:
    return {key: item for key, item in value.items() if item is not None}


def _result_status(*, cagr: Optional[float], sharpe: Optional[float], mdd: Optional[float]) -> str:
    if cagr is None and sharpe is None:
        return "WARNING"
    if (cagr is not None and cagr < 0) or (sharpe is not None and sharpe < 0):
        return "FAIL"
    if mdd is not None and mdd < -0.30:
        return "WARNING"
    return "PASS"


def _metadata_filter_from_strategy(strategy_dsl: Dict[str, Any]) -> Optional[Dict[str, str]]:
    where: Dict[str, str] = {}
    universe = _strategy_universe(strategy_dsl)
    timeframe = _strategy_timeframe(strategy_dsl)
    if universe != "unknown":
        where["universe"] = universe
    if timeframe:
        where["timeframe"] = timeframe
    return where or None


def _normalize_chroma_where(where: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not where or len(where) <= 1:
        return where
    return {"$and": [{key: value} for key, value in where.items()]}


def _metrics_from_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "cagr": metadata.get("cagr"),
        "mdd": metadata.get("mdd"),
        "sharpe": metadata.get("sharpe"),
        "profit_factor": metadata.get("profit_factor"),
        "win_rate": metadata.get("win_rate"),
        "trade_count": metadata.get("trade_count"),
    }


def _lesson_from_match(match: VectorMemoryMatch) -> str:
    status = match.metadata.get("result_status", "WARNING")
    return (
        f"ChromaDB에서 검색된 과거 백테스트 사례입니다. result_status={status}, "
        f"similarity={match.similarity_score:.3f}. 동일 조건 재백테스트와 OOS 검증 전에는 "
        "성과를 확정하지 않습니다."
    )
