import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from api import advisor_routes
from advisor.schemas import AdvisorRequest, BacktestSummary, NewsArticleSignal, NewsContext
from advisor.strategy_identity import strategy_id_for


def _create_memory_db(path):
    conn = sqlite3.connect(path)
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
    strategy_dsl = {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
        "max_positions": 10,
        "initial_capital": 10_000_000,
    }
    conn.execute(
        """
        INSERT INTO AdviceExperience (
            id, strategyId, createdAt, initialCapital, timeframe, userPrompt,
            strategySummary, strategyDsl, canonicalDsl, strategyHash,
            similarStrategyIds, retrievedCases, agentAdvice, beforeBacktest,
            afterBacktest, evaluation, lesson, confidence
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "exp_1",
            "case_rsi_memory",
            "2026-04-30T00:00:00Z",
            10_000_000,
            "1d",
            "과매도 구간에서 사고 과매수 구간에서 판다",
            "RSI 평균회귀",
            json.dumps(strategy_dsl),
            json.dumps(strategy_dsl),
            "case_rsi_memory",
            json.dumps([]),
            json.dumps([]),
            json.dumps({"advice_summary": "trend filter"}),
            json.dumps({"cagr": 0.04, "mdd": -0.28, "sharpe": 0.4}),
            json.dumps({"cagr": 0.07, "mdd": -0.18, "sharpe": 0.7}),
            json.dumps({"advice_success": True}),
            "RSI 평균회귀는 장기 추세 필터와 함께 검증해야 한다.",
            "high",
        ),
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_advisor_route_auto_injects_news_context(monkeypatch, tmp_path):
    db_path = tmp_path / "no-memory-tables.db"
    sqlite3.connect(db_path).close()
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")
    monkeypatch.setattr(
        advisor_routes,
        "build_news_context_from_strategy",
        lambda _parsed: [
            NewsContext(
                symbol="005930",
                latest_alpha=-0.15,
                risk_alert_level="high",
                articles=[
                    NewsArticleSignal(
                        event_type="guidance_cut",
                        sentiment="negative",
                        impact_direction="down",
                        impact_score=-0.7,
                        confidence_score=0.85,
                    )
                ],
            )
        ],
    )

    req = AdvisorRequest(
        user_prompt="삼성전자 전략",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi"}],
            "stop_loss_pct": 8.0,
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    result = await advisor_routes.review_strategy(req)

    assert result.news_analysis is not None
    assert result.news_analysis.risk_level == "high"
    assert "심각한 리스크 경보" in result.news_analysis.summary


@pytest.mark.asyncio
async def test_advisor_route_auto_injects_memory_context(monkeypatch, tmp_path):
    db_path = tmp_path / "advisor-memory.db"
    _create_memory_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")
    monkeypatch.setattr(advisor_routes, "build_news_context_from_strategy", lambda _parsed: [])

    req = AdvisorRequest(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    result = await advisor_routes.review_strategy(req)

    assert result.strategy_memory_context is not None
    assert result.strategy_memory_context["data_sufficiency"] == "sufficient"
    assert (
        result.strategy_memory_context["retrieved_cases"][0]["case_strategy_id"]
        == "case_rsi_memory"
    )


@pytest.mark.asyncio
async def test_advisor_route_works_without_memory_tables(monkeypatch, tmp_path):
    db_path = tmp_path / "empty.db"
    sqlite3.connect(db_path).close()
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")
    monkeypatch.setattr(advisor_routes, "build_news_context_from_strategy", lambda _parsed: [])

    req = AdvisorRequest(
        user_prompt="RSI 테스트",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi"}],
            "stop_loss_pct": 8.0,
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    result = await advisor_routes.review_strategy(req)

    assert result.strategy_memory_context is None


def _create_persistence_db(path):
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
            dataCoverage TEXT,
            FOREIGN KEY(strategyId) REFERENCES Strategy(id)
        )
        """
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_advisor_route_persists_experience_memory(monkeypatch, tmp_path):
    db_path = tmp_path / "persist-memory.db"
    _create_persistence_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")
    monkeypatch.setattr(advisor_routes, "build_news_context_from_strategy", lambda _parsed: [])

    req = AdvisorRequest(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
        backtest_result=BacktestSummary(cagr=0.04, mdd=-0.25, sharpe=0.4),
        candidate_backtest_result=BacktestSummary(cagr=0.08, mdd=-0.16, sharpe=0.8),
        evaluation_context={"oos_available": True},
    )

    result = await advisor_routes.review_strategy(req)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM AdviceExperience").fetchone()
    strategy = conn.execute("SELECT * FROM Strategy").fetchone()
    conn.close()

    assert result.advice_evaluation is not None
    assert row is not None
    assert strategy is not None
    assert row["strategyId"] == row["strategyHash"] == strategy["id"]
    assert json.loads(row["beforeBacktest"])["cagr"] == 0.04
    assert json.loads(row["afterBacktest"])["cagr"] == 0.08
    assert json.loads(row["evaluation"])["net_effect"] == "positive"


@pytest.mark.asyncio
async def test_advisor_route_persists_then_retrieves_experience_memory(monkeypatch, tmp_path):
    db_path = tmp_path / "persist-then-retrieve-memory.db"
    _create_persistence_db(db_path)
    monkeypatch.setenv("DATABASE_URL", f"file:{db_path}")
    monkeypatch.setattr(advisor_routes, "build_news_context_from_strategy", lambda _parsed: [])

    strategy_dsl = {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30, "period": 14}],
        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70, "period": 14}],
        "max_positions": 10,
        "initial_capital": 10_000_000,
    }
    expected_strategy_id = strategy_id_for(strategy_dsl)

    first_req = AdvisorRequest(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        parsed_strategy=strategy_dsl,
        backtest_result=BacktestSummary(cagr=0.04, mdd=-0.25, sharpe=0.4, trade_count=30),
        candidate_backtest_result=BacktestSummary(cagr=0.08, mdd=-0.16, sharpe=0.8, trade_count=35),
        evaluation_context={"oos_available": True, "oos_delta": 0.0},
    )

    first_result = await advisor_routes.review_strategy(first_req)

    assert first_result.advice_evaluation is not None
    assert first_result.strategy_memory_context is None

    second_req = AdvisorRequest(
        user_prompt="과매도 구간에서 사고 과매수 구간에서 판다",
        parsed_strategy={
            **strategy_dsl,
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 31, "period": 14}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 69, "period": 14}],
        },
    )

    second_result = await advisor_routes.review_strategy(second_req)

    assert second_result.strategy_memory_context is not None
    memory_context = second_result.strategy_memory_context
    assert memory_context["data_sufficiency"] == "sufficient"
    assert expected_strategy_id in memory_context["similar_strategy_ids"]
    assert memory_context["retrieved_cases"][0]["case_strategy_id"] == expected_strategy_id
    assert memory_context["retrieved_cases"][0]["before_metrics"]["cagr"] == 0.04
    assert memory_context["retrieved_cases"][0]["after_metrics"]["cagr"] == 0.08
    assert "Experience Memory" in next(
        item.body
        for item in second_result.advice
        if item.title == "유사 전략 경험 기반 점검"
    )

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM AdviceExperience").fetchone()[0]
    conn.close()

    assert count == 2
