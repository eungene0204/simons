import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from advisor.vector_memory import (
    HashingEmbeddingClient,
    load_backtest_documents,
    migrate_backtest_results_to_chroma,
    query_chroma_memory,
)


def _create_backtest_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE Strategy (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            settings TEXT NOT NULL,
            strategyType TEXT NOT NULL,
            createdAt TEXT NOT NULL,
            updatedAt TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE BacktestResult (
            id TEXT PRIMARY KEY,
            strategyId TEXT NOT NULL,
            stockId INTEGER,
            summary TEXT NOT NULL,
            trades TEXT,
            createdAt TEXT NOT NULL
        )
        """
    )
    rows = [
        (
            "rsi_case",
            "RSI mean reversion",
            "RSI oversold entry and overbought exit",
            {
                "universe": ["KOSPI200"],
                "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
                "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
                "timeframe": "1d",
            },
            {"cagr": 0.08, "mdd": -0.18, "sharpe": 0.9, "trade_count": 34},
        ),
        (
            "pbr_case",
            "PBR value",
            "Low PBR diversified strategy",
            {
                "universe": ["KOSPI"],
                "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
                "timeframe": "1d",
            },
            {"cagr": -0.02, "mdd": -0.24, "sharpe": -0.1, "trade_count": 12},
        ),
    ]
    for strategy_id, name, description, settings, summary in rows:
        conn.execute(
            """
            INSERT INTO Strategy (id, name, description, settings, strategyType, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_id,
                name,
                description,
                json.dumps(settings),
                "test",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO BacktestResult (id, strategyId, summary, createdAt)
            VALUES (?, ?, ?, ?)
            """,
            (
                f"bt_{strategy_id}",
                strategy_id,
                json.dumps(summary),
                "2026-02-01T00:00:00Z",
            ),
        )
    conn.commit()
    return conn


@pytest.mark.asyncio
async def test_hashing_embedding_is_stable() -> None:
    client = HashingEmbeddingClient(dimension=32)

    left = await client.embed_text("RSI mean reversion")
    right = await client.embed_text("RSI mean reversion")

    assert left == right
    assert len(left) == 32


def test_load_backtest_documents_builds_chroma_schema(tmp_path) -> None:
    conn = _create_backtest_db(tmp_path / "memory.db")

    documents = load_backtest_documents(conn)

    assert len(documents) == 2
    rsi = next(item for item in documents if item.strategy_id == "rsi_case")
    assert "RSI oversold" in rsi.document
    assert rsi.metadata["strategy_id"] == "rsi_case"
    assert rsi.metadata["universe"] == "KOSPI200"
    assert rsi.metadata["timeframe"] == "1d"
    assert rsi.metadata["sharpe"] == 0.9
    conn.close()


@pytest.mark.asyncio
async def test_chroma_migration_and_similarity_search(tmp_path) -> None:
    pytest.importorskip("chromadb")
    conn = _create_backtest_db(tmp_path / "memory.db")
    chroma_path = tmp_path / "chroma"

    stats = await migrate_backtest_results_to_chroma(conn, persist_path=chroma_path)
    matches = await query_chroma_memory(
        user_prompt="RSI 30 이하에서 매수하고 70 이상에서 매도",
        strategy_dsl={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 31}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 69}],
            "timeframe": "1d",
        },
        persist_path=chroma_path,
    )

    assert stats.scanned == 2
    assert stats.upserted == 2
    assert matches
    assert matches[0].strategy_id == "rsi_case"
    assert matches[0].metadata["universe"] == "KOSPI200"
    conn.close()
