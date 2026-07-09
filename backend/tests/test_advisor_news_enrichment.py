import json
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from api import advisor_routes
from advisor.schemas import AdvisorRequest, BacktestSummary, NewsArticleSignal, NewsContext
from advisor.strategy_identity import strategy_id_for


def _seed_memory(conn):
    """AdviceExperience 시딩. strategyId는 Strategy FK(필수)라 부모행도 먼저 넣는다."""
    strategy_dsl = {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
        "max_positions": 10,
        "initial_capital": 10_000_000,
    }
    conn.execute(
        'INSERT INTO "Strategy" (id, name, settings, "strategyType", "createdAt", "updatedAt")'
        " VALUES (?, ?, ?, ?, ?, ?)",
        ("case_rsi_memory", "RSI 평균회귀", json.dumps(strategy_dsl), "advisor_memory",
         datetime(2026, 4, 30), datetime(2026, 4, 30)),
    )
    conn.execute(
        """
        INSERT INTO "AdviceExperience" (
            id, "strategyId", "createdAt", "initialCapital", timeframe, "userPrompt",
            "strategySummary", "strategyDsl", "canonicalDsl", "strategyHash",
            "similarStrategyIds", "retrievedCases", "agentAdvice", "beforeBacktest",
            "afterBacktest", evaluation, lesson, confidence
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "exp_1",
            "case_rsi_memory",
            datetime(2026, 4, 30),
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


def test_build_news_context_reads_v2_store_and_keeps_article_url(monkeypatch):
    """회귀: 코치 '뉴스' 링크는 news_v2 저장소(load_articles_for_symbols)에서 와야 한다.

    이전엔 비어 있는 레거시 sqlite NewsArticle 테이블을 읽어 url이 사라졌다 →
    '뉴스' 단어에 링크가 안 걸렸다. v2 기사 dict가 NewsContext.articles[].url로
    그대로 흘러가고, 부정 기사 importance로 위험경보를 산정하는지 확인한다.
    """
    from advisor import news_enrichment

    rows = {
        "005930": [
            {
                "sentiment": "negative",
                "importance": "high",
                "impactScore": 0.6,
                "title": "삼성전자 리콜 이슈",
                "url": "https://news.example.com/x",
                "publishedAt": "2026-06-15T00:00:00Z",
            }
        ]
    }
    monkeypatch.setattr(
        news_enrichment,
        "load_articles_for_symbols",
        lambda symbols, as_of, limit=3: {s: rows.get(s, []) for s in symbols},
    )

    contexts = news_enrichment.build_news_context_from_strategy({"symbols": ["005930"]})

    assert len(contexts) == 1
    ctx = contexts[0]
    assert ctx.symbol == "005930"
    assert ctx.risk_alert_level == "high"
    article = ctx.articles[0]
    assert article.url == "https://news.example.com/x"
    assert article.sentiment == "negative"
    assert article.impact_direction == "down"
    assert article.impact_score == -0.6


@pytest.mark.asyncio
async def test_advisor_route_auto_injects_news_context(monkeypatch, app_db):
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
async def test_advisor_route_auto_injects_memory_context(monkeypatch, app_db):
    _seed_memory(app_db)
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
async def test_advisor_route_works_without_memory_tables(monkeypatch, app_db):
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


@pytest.mark.asyncio
async def test_advisor_route_persists_experience_memory(monkeypatch, app_db):
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

    row = app_db.execute('SELECT * FROM "AdviceExperience"').fetchone()
    strategy = app_db.execute('SELECT * FROM "Strategy"').fetchone()

    assert result.advice_evaluation is not None
    assert row is not None
    assert strategy is not None
    assert row["strategyId"] == row["strategyHash"] == strategy["id"]
    assert json.loads(row["beforeBacktest"])["cagr"] == 0.04
    assert json.loads(row["afterBacktest"])["cagr"] == 0.08
    assert json.loads(row["evaluation"])["net_effect"] == "positive"


@pytest.mark.asyncio
async def test_advisor_route_does_not_overwrite_existing_strategy(monkeypatch, app_db):
    monkeypatch.setattr(advisor_routes, "build_news_context_from_strategy", lambda _parsed: [])

    strategy_dsl = {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
        "max_positions": 10,
        "initial_capital": 10_000_000,
    }
    strategy_id = strategy_id_for(strategy_dsl)

    app_db.execute(
        'INSERT INTO "Strategy" (id, name, description, settings, "strategyType", "createdAt", "updatedAt")'
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            strategy_id,
            "사용자 저장 전략",
            "사용자가 직접 저장한 설명",
            json.dumps({"preserve": True}),
            "custom",
            datetime(2026, 1, 1),
            datetime(2026, 1, 1),
        ),
    )
    app_db.commit()

    req = AdvisorRequest(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        parsed_strategy=strategy_dsl,
        backtest_result=BacktestSummary(cagr=0.04, mdd=-0.25, sharpe=0.4),
    )

    await advisor_routes.review_strategy(req)

    strategy = app_db.execute('SELECT * FROM "Strategy" WHERE id = ?', (strategy_id,)).fetchone()
    experience_count = app_db.execute('SELECT COUNT(*) FROM "AdviceExperience"').fetchone()[0]

    assert strategy["name"] == "사용자 저장 전략"
    assert strategy["description"] == "사용자가 직접 저장한 설명"
    assert json.loads(strategy["settings"]) == {"preserve": True}
    assert strategy["strategyType"] == "custom"
    assert strategy["updatedAt"] == datetime(2026, 1, 1)
    assert experience_count == 1


@pytest.mark.asyncio
async def test_advisor_route_persists_then_retrieves_experience_memory(monkeypatch, app_db):
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
    memory_advice = next(
        item.body
        for item in second_result.advice
        if item.title == "유사 전략 경험 기반 점검"
    )
    assert "조정 후" in memory_advice
    assert "CAGR" in memory_advice
    assert "MDD" in memory_advice
    assert "Sharpe" in memory_advice
    assert "같은 기간과 비용 조건" in memory_advice
    assert "Experience Memory" not in memory_advice
    assert "투자 추천" not in memory_advice

    count = app_db.execute('SELECT COUNT(*) FROM "AdviceExperience"').fetchone()[0]

    assert count == 2
