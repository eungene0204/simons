"""Embedding client protocols and deterministic local embedding."""

from __future__ import annotations

import asyncio
import hashlib
import math
from typing import Any, Optional, Protocol, Sequence


DEFAULT_EMBEDDING_DIMENSION = 384
BGE_M3_DIMENSION = 1024
BGE_M3_MODEL_NAME = "BAAI/bge-m3"


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


# ── bge-m3 의미 임베딩 ────────────────────────────────────────────────────────
# 코퍼스 적재와 라이브 쿼리가 같은 모델/차원을 써야 검색이 성립한다(둘 다 BgeM3EmbeddingClient).
# 모델(~2.3GB)은 프로세스당 1회만 로드하도록 전역 싱글턴으로 캐시한다.

_BGE_M3_MODEL: Any = None


def _resolve_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _load_bge_m3(device: Optional[str] = None) -> Any:
    """SentenceTransformer bge-m3 싱글턴 로더(지연 로딩)."""
    global _BGE_M3_MODEL
    if _BGE_M3_MODEL is None:
        from sentence_transformers import SentenceTransformer

        _BGE_M3_MODEL = SentenceTransformer(BGE_M3_MODEL_NAME, device=device or _resolve_device())
    return _BGE_M3_MODEL


class BgeM3EmbeddingClient:
    """BAAI/bge-m3 dense 임베딩(1024차원, L2 정규화 → 코사인 검색용).

    동기 인코딩을 asyncio.to_thread로 감싸 비동기 인터페이스를 유지한다.
    """

    model_version = "bge-m3"

    def __init__(self, *, device: Optional[str] = None, batch_size: int = 32) -> None:
        self._device = device
        self._batch_size = batch_size

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        model = _load_bge_m3(self._device)
        vectors = model.encode(
            list(texts),
            normalize_embeddings=True,
            batch_size=self._batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, texts)
