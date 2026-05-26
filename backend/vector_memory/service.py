"""Application service for backtest vector memory."""

from __future__ import annotations

from typing import Any, Optional

from .embedding import EmbeddingClient
from .models import NormalizedBacktestMemory, VectorMemoryDocument, VectorMemoryMatch
from .normalization import build_embedding_text, build_vector_document
from .repository import VectorMemoryRepository


class VectorMemoryService:
    def __init__(
        self,
        *,
        repository: VectorMemoryRepository,
        embedding_client: EmbeddingClient,
    ) -> None:
        self._repository = repository
        self._embedding_client = embedding_client

    async def upsert_backtest_memory(self, record: NormalizedBacktestMemory) -> VectorMemoryDocument:
        document = build_vector_document(record)
        embedding = await self._embedding_client.embed_text(document.document)
        await self._repository.upsert(item=document, embedding=embedding)
        return document

    async def query_similar(
        self,
        *,
        record: NormalizedBacktestMemory,
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[VectorMemoryMatch]:
        embedding = await self._embedding_client.embed_text(build_embedding_text(record))
        return await self._repository.query_similar(
            query_embedding=embedding,
            top_k=top_k,
            where=where,
        )

    async def query_text(
        self,
        *,
        text: str,
        top_k: int = 5,
        where: Optional[dict[str, Any]] = None,
    ) -> list[VectorMemoryMatch]:
        embedding = await self._embedding_client.embed_text(text)
        return await self._repository.query_similar(
            query_embedding=embedding,
            top_k=top_k,
            where=where,
        )
