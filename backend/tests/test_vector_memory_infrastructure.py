import os
import json
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from vector_memory import (
    HashingEmbeddingClient,
    InMemoryVectorMemoryRepository,
    VectorMemoryService,
    load_batch_candidate_memories,
    load_backtest_memories,
    migrate_backtest_results,
    migrate_backtest_results_to_chroma,
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


def _seed_backtest_db(conn):
    """simons_test에 Strategy/BacktestResult 시딩(스키마는 마이그레이션으로 존재)."""
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
            'INSERT INTO "Strategy" (id, name, description, settings, "strategyType", "createdAt", "updatedAt")'
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                strategy_id,
                name,
                description,
                json.dumps(settings),
                "test",
                datetime(2026, 1, 1),
                datetime(2026, 1, 1),
            ),
        )
        conn.execute(
            'INSERT INTO "BacktestResult" (id, "strategyId", summary, "createdAt") VALUES (?, ?, ?, ?)',
            (
                f"bt_{strategy_id}",
                strategy_id,
                json.dumps(summary),
                datetime(2026, 2, 1),
            ),
        )
    conn.commit()
    return conn


def _add_batch_candidate(conn):
    # BatchRunCandidate.runId → BatchRun FK: 부모 BatchRun 먼저 시딩
    conn.execute(
        'INSERT INTO "BatchRun" (id, "totalPrompts", "rankingSnapshot") VALUES (?, ?, ?)'
        ' ON CONFLICT (id) DO NOTHING',
        ("batch_run_001", 1, "[]"),
    )
    conn.execute(
        """
        INSERT INTO "BatchRunCandidate" (
            id, "runId", "strategyId", prompt, "strategyName", status, "errorMessage",
            metrics, rank, "backtestRequest", "createdAt"
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "candidate_001",
            "batch_run_001",
            None,
            "RSI batch candidate with ATR stop",
            "mean_reversion / rsi_reversal",
            "computed",
            None,
            json.dumps({
                **_rsi_metrics(),
                "equity": [10_000_000, 10_100_000, 10_250_000],
                "benchmark_equity": [10_000_000, 10_050_000, 10_000_000],
            }),
            1,
            json.dumps({
                "strategy_id": "candidate_strategy_hash",
                "canonical_strategy_dsl": {
                    **_rsi_dsl(25),
                    "stop_loss_pct": 6,
                },
                "symbols": ["005930", "000660"],
                "period": "1y",
                "options": {
                    "fee_rate": 0.00015,
                    "slippage_rate": 0.0002,
                },
            }),
            datetime(2026, 2, 2),
        ),
    )
    conn.commit()


def _insert_failed_batch_candidate(conn):
    conn.execute(
        """
        INSERT INTO "BatchRunCandidate" (
            id, "runId", "strategyId", prompt, "strategyName", status, "errorMessage",
            metrics, rank, "backtestRequest", "createdAt"
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "candidate_failed_001",
            "batch_run_001",
            None,
            "Failed RSI batch candidate",
            "mean_reversion / rsi_reversal",
            "failed",
            "Backtest execution failed",
            json.dumps("failed"),
            None,
            json.dumps({
                "canonical_strategy_dsl": _rsi_dsl(20),
            }),
            datetime(2026, 2, 3),
        ),
    )
    conn.commit()


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


def test_load_backtest_memories_normalizes_stored_prisma_rows(app_db) -> None:
    _seed_backtest_db(app_db)

    records = load_backtest_memories(app_db)

    assert len(records) == 2
    rsi = next(record for record in records if "rsi" in record.indicators)
    assert rsi.strategySummary == "RSI oversold entry and overbought exit"
    assert rsi.marketRegime == "sideways"
    assert rsi.Sharpe == 0.9
    assert rsi.tradeCount == 34


def test_load_batch_candidate_memories_normalizes_batch_rows_without_raw_series(app_db) -> None:
    _seed_backtest_db(app_db)
    _add_batch_candidate(app_db)

    records = load_batch_candidate_memories(app_db)

    assert len(records) == 1
    record = records[0]
    document = build_vector_document(record)

    assert record.strategySummary == "RSI batch candidate with ATR stop"
    assert record.strategyVersion == "batch_candidate:candidate_001"
    assert record.indicators == ["rsi"]
    assert record.Sharpe == 0.9
    assert record.successReason.startswith("Batch candidate completed, rank=1")
    assert "equity" not in document.document
    assert document.id.endswith(":batch_candidate:candidate_001")


def test_load_batch_candidate_memories_keeps_failed_rows_with_non_object_metrics(app_db) -> None:
    _seed_backtest_db(app_db)
    _add_batch_candidate(app_db)
    _insert_failed_batch_candidate(app_db)

    records = load_batch_candidate_memories(app_db)

    failed = next(record for record in records if record.strategyVersion == "batch_candidate:candidate_failed_001")
    assert failed.failureReason == "Backtest execution failed"
    assert failed.Sharpe == 0
    assert failed.successReason == ""


def test_load_backtest_memories_includes_backtest_results_and_batch_candidates(app_db) -> None:
    _seed_backtest_db(app_db)
    _add_batch_candidate(app_db)

    records = load_backtest_memories(app_db)

    assert len(records) == 3
    assert any(record.strategyVersion == "batch_candidate:candidate_001" for record in records)


@pytest.mark.asyncio
async def test_migrate_backtest_results_upserts_loaded_rows(app_db) -> None:
    _seed_backtest_db(app_db)
    repository = InMemoryVectorMemoryRepository()
    service = VectorMemoryService(
        repository=repository,
        embedding_client=HashingEmbeddingClient(dimension=64),
    )

    stats = await migrate_backtest_results(app_db, service=service)

    assert stats.scanned == 2
    assert stats.upserted == 2
    assert stats.skipped == 0
    assert repository.count() == 2

    matches = await service.query_text(text="RSI oversold entry", where={"marketRegime": "sideways"})
    assert matches
    assert matches[0].metadata["sharpe"] == 0.9


@pytest.mark.asyncio
async def test_chroma_migration_skips_batch_candidates_when_already_loaded(tmp_path, app_db) -> None:
    pytest.importorskip("chromadb")
    _seed_backtest_db(app_db)
    _add_batch_candidate(app_db)

    first = await migrate_backtest_results_to_chroma(app_db, persist_path=tmp_path / "chroma", batch_size=2)
    second = await migrate_backtest_results_to_chroma(app_db, persist_path=tmp_path / "chroma", batch_size=2)

    assert first.scanned == 3
    assert first.upserted == 3
    assert second.scanned == 2
    assert second.upserted == 2
