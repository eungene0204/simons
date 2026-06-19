import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import advisor.memory_repository as memory_repository
from advisor.memory_repository import (
    _normalize_vector_categories,
    _rerank_vector_matches,
    load_advisor_memory,
    load_vector_advisor_memory,
)
from api import advisor_routes
from advisor.schemas import AdvisorRequest
from vector_memory import HashingEmbeddingClient, normalize_backtest_result
from vector_memory.models import VectorMemoryMatch


def _use_light_embeddings(monkeypatch):
    """인프라 배선 검증 테스트는 무거운 bge-m3 대신 결정적 해싱 임베딩을 주입한다.

    적재(부트스트랩 마이그레이션)와 쿼리가 같은 클라이언트를 쓰므로 차원이 내부 정합한다.
    """
    monkeypatch.setattr(memory_repository, "_query_embedding_client", lambda: HashingEmbeddingClient())


def _create_bootstrap_db(path):
    conn = sqlite3.connect(path)
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
    conn.execute(
        """
        CREATE TABLE AdviceExperience (
            id TEXT PRIMARY KEY,
            strategyId TEXT NOT NULL,
            createdAt TEXT NOT NULL,
            market TEXT,
            universe TEXT,
            initialCapital REAL NOT NULL,
            timeframe TEXT NOT NULL,
            userPrompt TEXT NOT NULL,
            strategySummary TEXT,
            strategyDsl TEXT NOT NULL,
            canonicalDsl TEXT NOT NULL,
            strategyHash TEXT NOT NULL,
            similarStrategyIds TEXT NOT NULL,
            retrievedCases TEXT NOT NULL,
            agentAdvice TEXT NOT NULL,
            beforeBacktest TEXT NOT NULL,
            afterBacktest TEXT,
            evaluation TEXT NOT NULL,
            lesson TEXT NOT NULL,
            confidence TEXT NOT NULL,
            dataCoverage TEXT
        )
        """
    )

    strategy_rows = [
        (
            "legacy_rsi_case",
            "RSI 평균회귀",
            "과매도 RSI 매수 후 평균회귀를 노린다",
            {
                "universe": ["KOSPI200"],
                "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30, "period": 14}],
                "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70, "period": 14}],
                "max_positions": 10,
                "initial_capital": 10000000,
                "timeframe": "1d",
            },
        ),
        (
            "legacy_pbr_case",
            "PBR 가치전략",
            "PBR 1배 이하 대형주를 분산 매수한다",
            {
                "universe": ["KOSPI"],
                "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
                "max_positions": 8,
                "initial_capital": 15000000,
                "timeframe": "1d",
            },
        ),
    ]
    for strategy_id, name, description, settings in strategy_rows:
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
                "legacy",
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
            "bt_old",
            "legacy_rsi_case",
            json.dumps({"cagr": 0.01, "maxDrawdown": -0.30, "sharpe": 0.2}),
            "2026-01-01T00:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO BacktestResult (id, strategyId, summary, createdAt)
        VALUES (?, ?, ?, ?)
        """,
        (
            "bt_new",
            "legacy_rsi_case",
            json.dumps({"cagr": 0.06, "maxDrawdown": -0.18, "sharpe": 0.8}),
            "2026-02-01T00:00:00Z",
        ),
    )
    conn.execute(
        """
        INSERT INTO BacktestResult (id, strategyId, summary, createdAt)
        VALUES (?, ?, ?, ?)
        """,
        (
            "bt_pbr",
            "legacy_pbr_case",
            json.dumps({"cagr": -0.04, "mdd": -0.22, "sharpe": -0.1}),
            "2026-01-15T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()


def _insert_strategy_backtest(
    conn,
    *,
    strategy_id,
    name,
    description,
    settings,
    summary,
    created_at="2026-02-20T00:00:00Z",
):
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
            "legacy",
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
            created_at,
        ),
    )


def _vector_match(*, item_id, dsl, similarity, strategy_hash):
    return VectorMemoryMatch(
        id=item_id,
        similarity_score=similarity,
        document=f"Strategy DSL: {json.dumps(dsl, ensure_ascii=False, sort_keys=True)}\nStrategy summary: test",
        metadata={"strategy_hash": strategy_hash},
    )


def _vector_match_with_metadata(*, item_id, dsl, similarity, strategy_hash, metadata):
    match = _vector_match(
        item_id=item_id,
        dsl=dsl,
        similarity=similarity,
        strategy_hash=strategy_hash,
    )
    match.metadata.update(metadata)
    return match


def test_vector_memory_reranker_prioritizes_matching_dsl_over_raw_similarity():
    query_record = normalize_backtest_result(
        strategy_dsl={
            "universe": ["KOSPI200"],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "max_positions": 8,
            "hold_period_days": 126,
            "stop_loss_pct": 12,
            "initial_capital": 10000000,
        },
        metrics={},
        strategy_summary="PBR 1 이하 대형주 8종목 6개월 보유 -12% 손절",
    )
    cci_match = _vector_match(
        item_id="cci:1",
        strategy_hash="cci_hash",
        similarity=0.90,
        dsl={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "cci", "operator": "<=", "value": -100}],
            "max_positions": 20,
            "hold_period_days": 10,
            "stop_loss_pct": 12,
            "initial_capital": 10000000,
        },
    )
    pbr_match = _vector_match(
        item_id="pbr:1",
        strategy_hash="pbr_hash",
        similarity=0.55,
        dsl={
            "universe": ["KOSPI200"],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "max_positions": 8,
            "hold_period_days": 120,
            "stop_loss_pct": 12,
            "initial_capital": 10000000,
        },
    )

    ranked = _rerank_vector_matches(query_record, [cci_match, pbr_match])

    assert ranked[0].id == "pbr:1"


def test_vector_memory_reranker_deduplicates_same_strategy_hash():
    query_record = normalize_backtest_result(
        strategy_dsl={
            "universe": ["KOSPI200"],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        },
        metrics={},
    )
    first = _vector_match(
        item_id="pbr:old",
        strategy_hash="same_pbr_hash",
        similarity=0.40,
        dsl={"universe": ["KOSPI200"], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}]},
    )
    second = _vector_match(
        item_id="pbr:new",
        strategy_hash="same_pbr_hash",
        similarity=0.70,
        dsl={"universe": ["KOSPI200"], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}]},
    )

    ranked = _rerank_vector_matches(query_record, [first, second])

    assert [item.id for item in ranked] == ["pbr:new"]


def test_vector_memory_reranker_hard_filters_required_fundamental_metric():
    query_record = normalize_backtest_result(
        strategy_dsl={
            "universe": ["KOSPI200"],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        },
        metrics={},
    )
    pbr_match = _vector_match(
        item_id="pbr:1",
        strategy_hash="pbr_hash",
        similarity=0.55,
        dsl={"universe": ["KOSPI200"], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.2}]},
    )
    cci_match = _vector_match(
        item_id="cci:1",
        strategy_hash="cci_hash",
        similarity=0.95,
        dsl={"universe": ["KOSPI200"], "entry_signals": [{"indicator": "cci", "operator": "<=", "value": -100}]},
    )

    ranked = _rerank_vector_matches(query_record, [cci_match, pbr_match])

    assert [item.id for item in ranked] == ["pbr:1"]


def test_vector_memory_reranker_prefers_matching_universe_when_available():
    query_record = normalize_backtest_result(
        strategy_dsl={
            "universe": ["KOSPI200"],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        },
        metrics={},
    )
    kosdaq_match = _vector_match(
        item_id="pbr:kosdaq",
        strategy_hash="kosdaq_pbr_hash",
        similarity=0.95,
        dsl={"universe": ["KOSDAQ"], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}]},
    )
    kospi200_match = _vector_match(
        item_id="pbr:kospi200",
        strategy_hash="kospi200_pbr_hash",
        similarity=0.50,
        dsl={"universe": ["KOSPI200"], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.2}]},
    )

    ranked = _rerank_vector_matches(query_record, [kosdaq_match, kospi200_match])

    assert [item.id for item in ranked] == ["pbr:kospi200"]


def test_vector_memory_categories_do_not_mark_failed_results_successful():
    failed_match = _vector_match_with_metadata(
        item_id="failed:pbr",
        strategy_hash="failed_pbr_hash",
        similarity=0.60,
        dsl={"universe": ["KOSPI200"], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}]},
        metadata={
            "riskLevel": "low",
            "failureReason": "백테스트 실행에 실패했습니다.",
            "sharpe": 0,
            "cagr": 0,
            "mdd": 0,
        },
    )
    categories = {"failed:pbr": ["similar", "successful_low_risk"]}

    _normalize_vector_categories({"failed:pbr": failed_match}, categories)

    assert categories["failed:pbr"] == ["similar", "failed_high_risk"]


def test_load_advisor_memory_bootstraps_latest_backtest_results(monkeypatch, tmp_path):
    db_path = tmp_path / "bootstrap-memory.db"
    _create_bootstrap_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")

    strategy_cases, experiences = load_advisor_memory(limit=500)

    assert len(strategy_cases) == 2
    assert len(experiences) == 2
    rsi_case = next(item for item in experiences if item["strategy_id"] == "legacy_rsi_case")
    assert rsi_case["before_backtest"]["cagr"] == 0.06
    assert rsi_case["evaluation"]["net_effect"] == "unverified"

    conn = sqlite3.connect(db_path)
    count_after_first = conn.execute("SELECT COUNT(*) FROM AdviceExperience").fetchone()[0]
    load_advisor_memory(limit=500)
    count_after_second = conn.execute("SELECT COUNT(*) FROM AdviceExperience").fetchone()[0]
    conn.close()

    assert count_after_first == 2
    assert count_after_second == 2


def test_load_advisor_memory_enriches_with_better_historical_comparator(monkeypatch, tmp_path):
    db_path = tmp_path / "bootstrap-comparison.db"
    _create_bootstrap_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO Strategy (id, name, description, settings, strategyType, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy_rsi_better_case",
            "RSI 평균회귀 개선형",
            "과매도 RSI 매수 후 추세 필터를 함께 확인한다",
            json.dumps({
                "universe": ["KOSPI200"],
                "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 31, "period": 14}],
                "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 69, "period": 14}],
                "max_positions": 10,
                "initial_capital": 10000000,
                "timeframe": "1d",
            }),
            "legacy",
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
            "bt_rsi_better",
            "legacy_rsi_better_case",
            json.dumps({"cagr": 0.12, "maxDrawdown": -0.12, "sharpe": 1.1, "trades": 34}),
            "2026-02-15T00:00:00Z",
        ),
    )
    conn.commit()
    conn.close()

    _, experiences = load_advisor_memory(limit=500)

    rsi_case = next(item for item in experiences if item["strategy_id"] == "legacy_rsi_case")
    assert rsi_case["after_backtest"]["cagr"] == 0.12
    assert rsi_case["evaluation"]["net_effect"] == "positive"
    assert rsi_case["evaluation"]["source"] == "historical_similar_strategy"
    assert rsi_case["evaluation"]["comparison_strategy_id"] == "legacy_rsi_better_case"
    assert rsi_case["confidence"] == "medium"

    conn = sqlite3.connect(db_path)
    coverage = conn.execute(
        "SELECT dataCoverage FROM AdviceExperience WHERE strategyId = ?",
        ("legacy_rsi_case",),
    ).fetchone()[0]
    conn.close()

    assert coverage == "bootstrap_historical_comparison"


@pytest.mark.asyncio
async def test_load_vector_advisor_memory_uses_vector_memory_infrastructure(monkeypatch, tmp_path):
    pytest.importorskip("chromadb")
    db_path = tmp_path / "vector-bootstrap-route.db"
    _create_bootstrap_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")
    monkeypatch.setenv("ADVISOR_CHROMA_PATH", str(tmp_path / "chroma"))
    _use_light_embeddings(monkeypatch)

    strategy_cases, experiences = await load_vector_advisor_memory(
        "RSI 30 이하 매수, 70 이상 매도",
        {
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 31, "period": 14}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 69, "period": 14}],
            "max_positions": 10,
            "initial_capital": 10000000,
            "timeframe": "1d",
        },
    )

    assert strategy_cases
    assert experiences
    rsi_case = next(case for case in strategy_cases if "rsi" in json.dumps(case["strategy_dsl"]))
    rsi_experience = next(item for item in experiences if item["strategy_id"] == rsi_case["strategy_id"])
    assert rsi_experience["before_backtest"]["sharpe"] == 0.8
    assert rsi_experience["evaluation"]["source"] == "vector_memory_backtest_results"
    assert "Vector Memory" in rsi_experience["lesson"]


@pytest.mark.asyncio
async def test_load_vector_advisor_memory_retrieves_category_specific_cases(monkeypatch, tmp_path):
    pytest.importorskip("chromadb")
    db_path = tmp_path / "vector-category-route.db"
    _create_bootstrap_db(db_path)
    conn = sqlite3.connect(db_path)
    base_strategy = {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30, "period": 14}],
        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70, "period": 14}],
        "max_positions": 10,
        "initial_capital": 10000000,
        "stop_loss_pct": 8,
        "hold_period_days": 20,
        "timeframe": "1d",
        "marketRegime": "sideways",
    }
    _insert_strategy_backtest(
        conn,
        strategy_id="rsi_success_low_risk",
        name="RSI 성공 저위험",
        description="RSI + ATR stop sideways success",
        settings=base_strategy,
        summary={
            "cagr": 0.14,
            "mdd": -0.08,
            "sharpe": 1.2,
            "sortino": 1.6,
            "trade_count": 45,
            "marketRegime": "sideways",
            "successReason": "ATR stop and trend filter reduced drawdown.",
        },
    )
    _insert_strategy_backtest(
        conn,
        strategy_id="rsi_failure_high_risk",
        name="RSI 실패 고위험",
        description="RSI no stop high volatility failure",
        settings={**base_strategy, "stop_loss_pct": None},
        summary={
            "cagr": -0.08,
            "mdd": -0.42,
            "sharpe": -0.3,
            "trade_count": 88,
            "marketRegime": "sideways",
            "failureReason": "No stop loss caused tail risk during volatility explosion.",
        },
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")
    monkeypatch.setenv("ADVISOR_CHROMA_PATH", str(tmp_path / "category-chroma"))
    _use_light_embeddings(monkeypatch)

    strategy_cases, experiences = await load_vector_advisor_memory(
        "RSI 30 이하 매수, 70 이상 매도, 20일 보유",
        base_strategy,
        top_k=4,
    )

    assert strategy_cases
    assert experiences
    categories = {
        category
        for item in experiences
        for category in item.get("retrieval_categories", [])
    }
    assert "similar" in categories
    assert "successful_low_risk" in categories
    assert "failed_high_risk" in categories
    assert "same_market_regime" in categories
    assert "same_capital" in categories
    assert "same_holding_period" in categories
    assert "same_trade_frequency" in categories

    success = next(item for item in experiences if "successful_low_risk" in item.get("retrieval_categories", []))
    failure = next(item for item in experiences if "failed_high_risk" in item.get("retrieval_categories", []))
    assert success["before_backtest"]["sharpe"] >= 1.0
    assert "성공 원인" in success["lesson"]
    assert failure["before_backtest"]["mdd"] <= -0.30
    assert "실패 원인" in failure["lesson"]


@pytest.mark.asyncio
async def test_advisor_route_uses_bootstrapped_memory(monkeypatch, tmp_path):
    db_path = tmp_path / "bootstrap-route.db"
    _create_bootstrap_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")
    monkeypatch.setattr(advisor_routes, "build_news_context_from_strategy", lambda _parsed: [])

    req = AdvisorRequest(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 31, "period": 14}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 69, "period": 14}],
            "max_positions": 10,
            "initial_capital": 10000000,
            "timeframe": "1d",
        },
    )

    result = await advisor_routes.review_strategy(req)

    assert result.strategy_memory_context is not None
    assert result.strategy_memory_context["retrieved_cases"][0]["case_strategy_id"] == "legacy_rsi_case"
    assert result.strategy_memory_context["retrieved_cases"][0]["before_metrics"]["cagr"] == 0.06

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM AdviceExperience").fetchone()[0]
    conn.close()

    assert count == 3
