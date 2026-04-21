"""Unit tests for Strategy Research Agent — pure logic only.

무거운 백테스트를 실행하지 않도록 BacktestEngine은 mock으로 대체한다.
Generator, Scorer, Safeguards, MonteCarlo, HoldoutGuard, Promoter, Agent
state-machine 전환을 각각 검증한다.
"""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest


# ─────────────────────────────────────────────────────────
# Generator / Templates / Hash dedup
# ─────────────────────────────────────────────────────────


def test_generator_dedup_stable_hash():
    from research.generator import CandidateGenerator

    gen = CandidateGenerator(
        templates=["momentum"],
        universes=[["KOSPI200"]],
        seed=42,
    )
    a = gen.generate(max_n=100)
    b = gen.generate(max_n=100)
    assert len(a) > 0
    assert {c.dsl_hash for c in a} == {c.dsl_hash for c in b}  # reproducibility
    assert len({c.dsl_hash for c in a}) == len(a)  # no dupes


def test_generator_respects_max_n():
    from research.generator import CandidateGenerator

    gen = CandidateGenerator(
        templates=["momentum", "mean_reversion", "value"],
        universes=[["KOSPI200"], ["KOSDAQ"]],
        seed=7,
    )
    out = gen.generate(max_n=5)
    assert len(out) == 5


def test_generator_rejects_unknown_template():
    from research.generator import CandidateGenerator

    with pytest.raises(ValueError, match="Unknown"):
        CandidateGenerator(templates=["no_such"], universes=[["KOSPI200"]], seed=1)


def test_momentum_short_ge_long_raises():
    from research.templates import momentum

    with pytest.raises(ValueError, match=">="):
        momentum.build({"short_period": 20, "long_period": 20}, ["KOSPI200"])


# ─────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────


def test_composite_score_bounded():
    from research.scoring import composite_score

    hi = composite_score(
        {"cagr": 2.0, "sharpe": 5.0, "profitFactor": 10.0, "maxDrawdown": 0.0},
        robustness=1.0,
    )
    lo = composite_score(
        {"cagr": -1.0, "sharpe": -5.0, "profitFactor": 0.1, "maxDrawdown": 0.9},
        robustness=0.0,
    )
    assert -1.0 <= lo < 0 < hi <= 1.0


def test_composite_score_prefers_robustness_over_returns():
    """Two strategies with identical returns but different robustness.

    더 robust한 쪽의 점수가 더 커야 한다 (robustness 가중치 0.20 >= ...).
    """
    from research.scoring import composite_score

    m = {"cagr": 0.15, "sharpe": 1.0, "profitFactor": 1.5, "maxDrawdown": 0.20}
    s_robust = composite_score(m, robustness=1.0)
    s_fragile = composite_score(m, robustness=0.0)
    assert s_robust > s_fragile


def test_robustness_score_in_unit_interval():
    from research.scoring import robustness_score

    s = robustness_score(
        wfe=0.8, is_sharpe=1.0, oos_sharpe=0.6,
        mc_cagr_p05=0.05, mc_cagr_median=0.15,
        holdout_passed=True, regime_consistency=0.7,
    )
    assert 0.0 <= s <= 1.0


def test_score_weights_must_sum_to_one():
    from research.scoring import ScoreWeights

    with pytest.raises(ValueError, match="sum to 1.0"):
        ScoreWeights(cagr=0.5, sharpe=0.5, profit_factor=0.5, mdd_penalty=0.0, robustness=0.0)


def test_deflated_sharpe_penalises_multiple_testing():
    from research.scoring import deflated_sharpe

    single = deflated_sharpe(1.5, n_trials=1)
    many = deflated_sharpe(1.5, n_trials=100)
    assert many < single


# ─────────────────────────────────────────────────────────
# Safeguards
# ─────────────────────────────────────────────────────────


def test_holdout_guard_clamps_endDate():
    from research.safeguards import HoldoutGuard

    g = HoldoutGuard(holdout_start="2025-10-20")
    req = {"symbols": ["005930"], "entry": {}, "exit": {}, "risk": {}}
    clamped = g.clamp(req)
    assert clamped["endDate"] == "2025-10-19"


def test_holdout_guard_raises_on_violation():
    from research.safeguards import HoldoutGuard, HoldoutViolation

    g = HoldoutGuard(holdout_start="2025-10-20")
    req = {"endDate": "2025-11-01"}
    with pytest.raises(HoldoutViolation):
        g.clamp(req)


def test_holdout_build_holdout_request_uses_start():
    from research.safeguards import HoldoutGuard

    g = HoldoutGuard(holdout_start="2025-10-20")
    req = {"endDate": "2025-09-01", "period": "5Y"}
    hold = g.build_holdout_request(req)
    assert hold["startDate"] == "2025-10-20"
    assert "endDate" not in hold
    assert hold["period"] == "full"


def test_circuit_breaker_trips_after_threshold():
    from research.safeguards import CircuitBreaker, CircuitBreakerTripped

    cb = CircuitBreaker(threshold=3, label="test")
    cb.record_failure()
    cb.record_failure()
    with pytest.raises(CircuitBreakerTripped):
        cb.record_failure()


def test_circuit_breaker_resets_on_success():
    from research.safeguards import CircuitBreaker

    cb = CircuitBreaker(threshold=3)
    cb.record_failure(); cb.record_failure()
    cb.record_success()
    cb.record_failure(); cb.record_failure()  # should not trip


def test_ai_leak_guard_detects_overlap():
    from research.safeguards import AIModelLeakDetected, AIModelLeakGuard

    g = AIModelLeakGuard(ai_training_cutoff="2024-01-01")
    req = {
        "startDate": "2020-01-01",
        "entry": {"conditions": [{"id": "ai_model", "params": {}}]},
        "exit": {"conditions": []},
    }
    with pytest.raises(AIModelLeakDetected):
        g.check(req)


def test_ai_leak_guard_passes_without_ai_blocks():
    from research.safeguards import AIModelLeakGuard

    g = AIModelLeakGuard(ai_training_cutoff="2024-01-01")
    req = {
        "startDate": "2020-01-01",
        "entry": {"conditions": [{"id": "rsi", "params": {}}]},
        "exit": {"conditions": []},
    }
    g.check(req)  # should not raise


def test_prescreen_gates_reject_low_trade_count():
    from research.safeguards import PrescreenGates

    gates = PrescreenGates(min_trades=30)
    passed, _ = gates.passes({"trades": 5, "cagr": 0.2, "profitFactor": 2.0, "maxDrawdown": 0.1})
    assert not passed


def test_prescreen_gates_accept_good_strategy():
    from research.safeguards import PrescreenGates

    gates = PrescreenGates()
    passed, _ = gates.passes(
        {"trades": 100, "cagr": 0.12, "profitFactor": 1.5, "maxDrawdown": 0.15},
        years=3.0, benchmark_cagr=0.05,
    )
    assert passed


# ─────────────────────────────────────────────────────────
# Monte Carlo
# ─────────────────────────────────────────────────────────


def test_monte_carlo_short_equity_returns_error():
    from engine.monte_carlo import MonteCarloSimulator

    mc = MonteCarloSimulator()
    out = mc.run({"equity": [100, 101, 102]}, n_iterations=100, block_size=21)
    assert out["status"] == "error"


def test_monte_carlo_produces_distribution():
    import numpy as np
    from engine.monte_carlo import MonteCarloSimulator

    rng = np.random.default_rng(0)
    eq = [1_000_000.0]
    for _ in range(500):
        eq.append(eq[-1] * (1 + rng.normal(0.0005, 0.01)))
    mc = MonteCarloSimulator()
    out = mc.run({"equity": eq, "initialCapital": 1_000_000.0}, n_iterations=200, block_size=21, seed=1)
    assert out["status"] == "ok"
    assert out["cagr"]["p05"] <= out["cagr"]["median"] <= out["cagr"]["p95"]
    assert 0 <= out["prob_positive_cagr"] <= 1


# ─────────────────────────────────────────────────────────
# Agent state machine (with mocked engine)
# ─────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = tmp_path / "test_research.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE ResearchRun (
            id TEXT PRIMARY KEY, userId INTEGER, status TEXT, goal TEXT,
            config TEXT, holdoutStart TEXT, seed INTEGER,
            startedAt TEXT, finishedAt TEXT, errorMessage TEXT,
            totalCandidates INTEGER DEFAULT 0, promotedCount INTEGER DEFAULT 0
        );
        CREATE TABLE ResearchCandidate (
            id TEXT PRIMARY KEY, runId TEXT, dslHash TEXT, dslJson TEXT,
            template TEXT, stage TEXT, rejectionReason TEXT,
            prescreenMetrics TEXT, wfaResult TEXT, mcResult TEXT,
            optunaBest TEXT, holdoutMetrics TEXT,
            compositeScore REAL, robustnessScore REAL, deflatedSharpe REAL,
            promotedAccountId TEXT, createdAt TEXT,
            UNIQUE(runId, dslHash)
        );
        CREATE TABLE ResearchEvent (
            id TEXT PRIMARY KEY, runId TEXT, candidateId TEXT,
            level TEXT, event TEXT, payload TEXT, createdAt TEXT
        );
        CREATE TABLE Strategy (
            id TEXT PRIMARY KEY, name TEXT, description TEXT,
            settings TEXT, strategyType TEXT, createdAt TEXT, updatedAt TEXT
        );
        CREATE TABLE VirtualAccount (
            id TEXT PRIMARY KEY, name TEXT, initialCash REAL, currentCash REAL,
            strategyId TEXT, strategyName TEXT, tradingMode TEXT,
            createdAt TEXT, updatedAt TEXT
        );
        CREATE TABLE VirtualMarketState (
            id TEXT PRIMARY KEY, accountId TEXT UNIQUE, startDate TEXT,
            status TEXT, symbols TEXT, createdAt TEXT, updatedAt TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO ResearchRun (id, userId, status, config, holdoutStart, seed, startedAt) "
        "VALUES ('run_test', 1, 'PENDING', '{}', '2025-10-20', 42, '2026-04-01')"
    )
    conn.commit()
    yield conn
    conn.close()


def _make_mock_engine():
    engine = MagicMock()
    # Default backtest output: decent strategy
    engine.run_backtest.return_value = {
        "cagr": 0.15, "sharpe": 1.2, "profitFactor": 1.5, "maxDrawdown": 0.18,
        "trades": 60, "totalReturn": 0.55,
        "equity": [1_000_000.0 * (1 + 0.0005 * i) for i in range(500)],
        "dates": [f"2023-01-{i+1:02d}" for i in range(28)] * 18,
        "initialCapital": 1_000_000.0,
    }
    return engine


def test_agent_generator_populates_candidates(tmp_db):
    from research.agent import AgentConfig, StrategyResearchAgent

    engine = _make_mock_engine()
    cfg = AgentConfig(
        holdout_start="2025-10-20",
        seed=1,
        templates=["momentum"],
        universes=[["KOSPI200"]],
        max_candidates=6,
    )
    agent = StrategyResearchAgent(engine=engine, db=tmp_db, config=cfg, run_id="run_test")
    cands = agent._generate()
    assert len(cands) > 0

    rows = tmp_db.execute("SELECT stage FROM ResearchCandidate WHERE runId='run_test'").fetchall()
    assert len(rows) == len(cands)
    assert all(r["stage"] == "GENERATED" for r in rows)


def test_agent_prescreen_rejects_no_trade_candidates(tmp_db):
    from research.agent import AgentConfig, StrategyResearchAgent

    engine = _make_mock_engine()
    engine.run_backtest.return_value = {
        **engine.run_backtest.return_value,
        "trades": 0,
    }
    cfg = AgentConfig(
        holdout_start="2025-10-20", seed=1,
        templates=["momentum"], universes=[["KOSPI200"]],
        max_candidates=3,
    )
    agent = StrategyResearchAgent(engine=engine, db=tmp_db, config=cfg, run_id="run_test")
    cands = agent._generate()
    results = agent._prescreen(cands)
    assert results == []  # all rejected


def test_promoter_creates_account_and_strategy(tmp_db):
    from research.generator import Candidate
    from research.promoter import Promoter

    promoter = Promoter(tmp_db)
    cand = Candidate(
        template="momentum",
        dsl_hash="deadbeef",
        backtest_request={"symbols": ["005930"], "universe_id": "kospi200"},
        parsed_dsl={"description": "test"},
    )
    out = promoter.promote(candidate=cand, user_id=1, strategy_name="agent-test")
    assert out["strategyId"].startswith("strat_")
    assert out["accountId"].startswith("va_")

    va = tmp_db.execute(
        "SELECT tradingMode, strategyId FROM VirtualAccount WHERE id = ?",
        (out["accountId"],),
    ).fetchone()
    assert va["tradingMode"] == "auto"
    assert va["strategyId"] == out["strategyId"]

    state = tmp_db.execute(
        "SELECT status FROM VirtualMarketState WHERE accountId = ?",
        (out["accountId"],),
    ).fetchone()
    assert state["status"] == "stopped"  # agent does not auto-start


# ─────────────────────────────────────────────────────────
# Search space
# ─────────────────────────────────────────────────────────


def test_search_space_cardinality_positive():
    from research.search_space import get_search_space, space_cardinality

    for t in ("momentum", "mean_reversion", "value", "volume_breakout", "ai_signal"):
        s = get_search_space(t)
        assert s, f"{t} has empty search space"
        assert space_cardinality(s) > 1


def test_search_space_unknown_returns_empty():
    from research.search_space import get_search_space

    assert get_search_space("no_such") == {}
