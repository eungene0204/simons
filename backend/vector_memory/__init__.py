"""Vector memory infrastructure for backtest Experience Memory."""

from .embedding import HashingEmbeddingClient
from .identity import canonical_strategy_string, strategy_hash_for, strategy_memory_id
from .models import (
    NormalizedBacktestMemory,
    VectorMemoryDocument,
    VectorMemoryMatch,
)
from .migration import (
    VectorMigrationStats,
    load_backtest_memories,
    migrate_backtest_results,
    migrate_backtest_results_to_chroma,
)
from .normalization import build_embedding_text, normalize_backtest_result
from .repository import ChromaVectorMemoryRepository, InMemoryVectorMemoryRepository
from .service import VectorMemoryService

__all__ = [
    "ChromaVectorMemoryRepository",
    "HashingEmbeddingClient",
    "InMemoryVectorMemoryRepository",
    "NormalizedBacktestMemory",
    "VectorMemoryDocument",
    "VectorMemoryMatch",
    "VectorMigrationStats",
    "VectorMemoryService",
    "build_embedding_text",
    "canonical_strategy_string",
    "load_backtest_memories",
    "migrate_backtest_results",
    "migrate_backtest_results_to_chroma",
    "normalize_backtest_result",
    "strategy_hash_for",
    "strategy_memory_id",
]
