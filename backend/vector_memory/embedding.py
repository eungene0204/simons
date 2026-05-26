"""Embedding client protocols and deterministic local embedding."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, Sequence


DEFAULT_EMBEDDING_DIMENSION = 384


class EmbeddingClient(Protocol):
    model_version: str

    async def embed_text(self, text: str) -> list[float]:
        ...

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        ...


class HashingEmbeddingClient:
    """Deterministic embedding client for local tests and offline MVP flows."""

    model_version = "local-hashing-v1"

    def __init__(self, dimension: int = DEFAULT_EMBEDDING_DIMENSION) -> None:
        self._dimension = dimension

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for token in _tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def _tokenize(text: str) -> list[str]:
    return [token for token in text.lower().replace("_", " ").split() if token]
