import os
import json
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from vector_memory import (
    HashingEmbeddingClient,
    InMemoryVectorMemoryRepository,
    VectorMemoryService,
    load_backtest_memories,
    migrate_backtest_results,
    normalize_backtest_result,
    strategy_hash_for,
    strategy_memory_id,
)
from vector_memory.normalization import build_embedding_text, build_vector_document
from vector_memory.repository import ChromaVectorMemoryRepository


def _rsi_dsl(threshold=30):
    return {
        "description": "RSI mean reversion",
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": threshold}],
        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
        "stop_loss_pct": 8,
        "hold_period_days": 20,
        "max_positions": 10,
        "initial_capital": 10_000_000,
        "timeframe": "1d",
        "sectorBias": ["semiconductor"],
    }


def _rsi_metrics():
    return {
        "return": 0.18,
        "cagr": 0.08,
        "sharpe": 0.9,
        "sortino": 1.2,
        "calmar": 0.44,
        "win_rate": 0.56,
        "profit_factor": 1.35,
        "mdd": -0.18,
        "volatility": 0.16,
        "turnover": 1.8,
        "trade_count": 34,
        "average_holding_days": 11.5,
        "successReason": "ATR stop and trend filter reduced drawdown.",
    }


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
            _rsi_dsl(),
            {**_rsi_metrics(), "marketRegime": "sideways"},
        ),
        (
            "pbr_case",
            "PBR value",
            "Low PBR diversified strategy",
            {
                "universe": ["KOSPI"],
                "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
                "timeframe": "1d",
                "initial_capital": 5_000_000,
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


def test_strategy_hash_ignores_volatile_fields_and_tracks_version() -> None:
    left = {**_rsi_dsl(), "id": "draft", "updatedAt": "2026-01-01T00:00:00Z"}
    right = _rsi_dsl()

    assert strategy_hash_for(left) == strategy_hash_for(right)
    assert strategy_memory_id(left, strategy_version="v1").endswith(":v1")
    assert strategy_memory_id(left, strategy_version="v2").endswith(":v2")


def test_normalize_backtest_result_uses_required_schema() -> None:
    record = normalize_backtest_result(
        strategy_dsl=_rsi_dsl(),
        metrics=_rsi_metrics(),
        strategy_summary="RSI oversold entry with stop loss",
        market_regime="sideways",
        failure_reason="Fails when volatility explodes.",
    )
    payload = record.to_payload()

    assert set(payload) >= {
        "strategyDsl",
        "strategySummary",
        "indicators",
        "entryConditions",
        "exitConditions",
        "riskManagement",
        "marketRegime",
        "sectorBias",
        "holdingPeriod",
        "rebalanceFrequency",
        "capital",
        "return",
        "CAGR",
        "Sharpe",
        "Sortino",
        "Calmar",
        "WinRate",
        "ProfitFactor",
        "MDD",
        "volatility",
        "turnover",
        "tradeCount",
        "averageHoldingDays",
        "failureReason",
        "successReason",
    }
    assert payload["indicators"] == ["rsi"]
    assert payload["holdingPeriod"] == 20
    assert payload["capital"] == 10_000_000
    assert payload["Sharpe"] == 0.9
    assert payload["failureReason"] == "Fails when volatility explodes."


def test_embedding_text_and_metadata_include_retrieval_fields() -> None:
    record = normalize_backtest_result(
        strategy_dsl=_rsi_dsl(),
        metrics=_rsi_metrics(),
        strategy_summary="RSI oversold entry with stop loss",
        market_regime="sideways",
    )

    text = build_embedding_text(record)
    document = build_vector_document(record)

    assert "Strategy DSL" in text
    assert "Entry conditions" in text
    assert "Failure reason" in text
    assert "Success reason" in text
    assert document.metadata["strategy_hash"] == strategy_hash_for(_rsi_dsl())
    assert document.metadata["marketRegime"] == "sideways"
    assert document.metadata["sectorBias"] == "semiconductor"
    assert document.metadata["indicators"] == "rsi"
    assert document.metadata["holdingPeriod"] == 20
    assert document.metadata["riskLevel"] == "medium"
    assert document.metadata["successReason"] == "ATR stop and trend filter reduced drawdown."


@pytest.mark.asyncio
async def test_vector_memory_service_upserts_without_duplicates_and_filters_metadata() -> None:
    repository = InMemoryVectorMemoryRepository()
    service = VectorMemoryService(
        repository=repository,
        embedding_client=HashingEmbeddingClient(dimension=64),
    )
    first = normalize_backtest_result(
        strategy_dsl=_rsi_dsl(),
        metrics=_rsi_metrics(),
        strategy_summary="RSI sideways case",
        market_regime="sideways",
    )
    second = normalize_backtest_result(
        strategy_dsl={**_rsi_dsl(25), "marketRegime": "bull"},
        metrics={**_rsi_metrics(), "sharpe": 0.3, "mdd": -0.32},
        strategy_summary="RSI bull case",
        market_regime="bull",
    )

    await service.upsert_backtest_memory(first)
    await service.upsert_backtest_memory(first)
    await service.upsert_backtest_memory(second)

    assert repository.count() == 2
    matches = await service.query_similar(
        record=first,
        top_k=5,
        where={"marketRegime": "sideways"},
    )

    assert len(matches) == 1
    assert matches[0].metadata["marketRegime"] == "sideways"
    assert matches[0].metadata["capital"] == 10_000_000
    assert matches[0].metadata["holdingPeriod"] == 20


@pytest.mark.asyncio
async def test_chroma_repository_upserts_and_queries_with_metadata(tmp_path) -> None:
    pytest.importorskip("chromadb")
    repository = ChromaVectorMemoryRepository(persist_path=tmp_path)
    service = VectorMemoryService(
        repository=repository,
        embedding_client=HashingEmbeddingClient(dimension=64),
    )
    record = normalize_backtest_result(
        strategy_dsl=_rsi_dsl(),
        metrics=_rsi_metrics(),
        strategy_summary="RSI sideways case",
        market_regime="sideways",
    )

    await service.upsert_backtest_memory(record)
    matches = await service.query_similar(record=record, where={"marketRegime": "sideways"})

    assert matches
    assert matches[0].metadata["marketRegime"] == "sideways"


def test_load_backtest_memories_normalizes_stored_prisma_rows(tmp_path) -> None:
    conn = _create_backtest_db(tmp_path / "memory.db")

    records = load_backtest_memories(conn)

    assert len(records) == 2
    rsi = next(record for record in records if "rsi" in record.indicators)
    assert rsi.strategySummary == "RSI oversold entry and overbought exit"
    assert rsi.marketRegime == "sideways"
    assert rsi.Sharpe == 0.9
    assert rsi.tradeCount == 34
    conn.close()


@pytest.mark.asyncio
async def test_migrate_backtest_results_upserts_loaded_rows(tmp_path) -> None:
    conn = _create_backtest_db(tmp_path / "memory.db")
    repository = InMemoryVectorMemoryRepository()
    service = VectorMemoryService(
        repository=repository,
        embedding_client=HashingEmbeddingClient(dimension=64),
    )

    stats = await migrate_backtest_results(conn, service=service)

    assert stats.scanned == 2
    assert stats.upserted == 2
    assert stats.skipped == 0
    assert repository.count() == 2

    matches = await service.query_text(text="RSI oversold entry", where={"marketRegime": "sideways"})
    assert matches
    assert matches[0].metadata["sharpe"] == 0.9
    conn.close()
