"""Vector memory repository adapters."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

from .models import PrimitiveMetadata, VectorMemoryDocument, VectorMemoryMatch


class VectorMemoryUnavailable(RuntimeError):
    """Raised when a vector repository cannot be initialized."""


class VectorMemoryRepository(Protocol):
    async def upsert(
        self,
        *,
        item: VectorMemoryDocument,
        embedding: Sequence[float],
    ) -> None:
        ...

    async def upsert_many(
        self,
        *,
        items: Sequence[VectorMemoryDocument],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        ...

    async def query_similar(
        self,
        *,
        query_embedding: Sequence[float],
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[VectorMemoryMatch]:
        ...


class InMemoryVectorMemoryRepository:
    def __init__(self) -> None:
        self._items: dict[str, tuple[VectorMemoryDocument, list[float]]] = {}

    async def upsert(
        self,
        *,
        item: VectorMemoryDocument,
        embedding: Sequence[float],
    ) -> None:
        self._items[item.id] = (item, list(embedding))

    async def upsert_many(
        self,
        *,
        items: Sequence[VectorMemoryDocument],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        for item, embedding in zip(items, embeddings):
            self._items[item.id] = (item, list(embedding))

    async def query_similar(
        self,
        *,
        query_embedding: Sequence[float],
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[VectorMemoryMatch]:
        matches: list[VectorMemoryMatch] = []
        for item, embedding in self._items.values():
            if not _matches_where(item.metadata, where):
                continue
            matches.append(
                VectorMemoryMatch(
                    id=item.id,
                    similarity_score=_cosine_similarity(query_embedding, embedding),
                    document=item.document,
                    metadata=dict(item.metadata),
                )
            )
        return sorted(matches, key=lambda match: match.similarity_score, reverse=True)[:top_k]

    def count(self) -> int:
        return len(self._items)


class ChromaVectorMemoryRepository:
    def __init__(
        self,
        *,
        persist_path: Path,
        collection_name: str = "backtest_results",
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
        item: VectorMemoryDocument,
        embedding: Sequence[float],
    ) -> None:
        await self.upsert_many(items=[item], embeddings=[embedding])

    async def upsert_many(
        self,
        *,
        items: Sequence[VectorMemoryDocument],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if not items:
            return
        await asyncio.to_thread(
            self._collection.upsert,
            ids=[item.id for item in items],
            documents=[item.document for item in items],
            embeddings=[list(embedding) for embedding in embeddings],
            metadatas=[item.metadata for item in items],
        )

    async def query_similar(
        self,
        *,
        query_embedding: Sequence[float],
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[VectorMemoryMatch]:
        result = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[list(query_embedding)],
            n_results=max(1, top_k),
            where=_normalize_chroma_where(where),
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        matches: list[VectorMemoryMatch] = []
        for item_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            matches.append(
                VectorMemoryMatch(
                    id=str(item_id),
                    similarity_score=max(0.0, 1.0 - float(distance)),
                    document=str(document or ""),
                    metadata=dict(metadata or {}),
                )
            )
        return matches

    def count(self) -> int:
        return int(self._collection.count())


def _matches_where(metadata: dict[str, PrimitiveMetadata], where: Optional[dict[str, Any]]) -> bool:
    if not where:
        return True
    for key, expected in where.items():
        if metadata.get(key) != expected:
            return False
    return True


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _normalize_chroma_where(where: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not where or len(where) <= 1:
        return where
    return {"$and": [{key: value} for key, value in where.items()]}
