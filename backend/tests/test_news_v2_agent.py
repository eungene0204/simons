"""Tests for the HeuristicNewsAgent — deterministic fallback."""

import pytest

from news_v2.agent import HeuristicNewsAgent


@pytest.mark.asyncio
async def test_heuristic_positive():
    agent = HeuristicNewsAgent()
    result = await agent.analyze(
        title="삼성전자 분기 최대 매출 신고가 돌파", body=None, symbol="005930"
    )
    assert result.sentiment == "positive"
    assert result.sentiment_score > 0


@pytest.mark.asyncio
async def test_heuristic_negative():
    agent = HeuristicNewsAgent()
    result = await agent.analyze(
        title="LG에너지솔루션 대규모 리콜로 급락 위기", body=None, symbol="373220"
    )
    assert result.sentiment == "negative"
    assert result.sentiment_score < 0


@pytest.mark.asyncio
async def test_heuristic_neutral():
    agent = HeuristicNewsAgent()
    result = await agent.analyze(title="회사 정기 주주총회 안내", body=None, symbol="005930")
    assert result.sentiment == "neutral"
    assert result.sentiment_score == 0


@pytest.mark.asyncio
async def test_heuristic_extracts_related_tickers():
    agent = HeuristicNewsAgent()
    result = await agent.analyze(
        title="005930 삼성전자 호실적, 000660 SK하이닉스 동반 상승",
        body=None,
        symbol="005930",
    )
    assert "000660" in result.related_symbols
    assert "005930" not in result.related_symbols


@pytest.mark.asyncio
async def test_heuristic_impact_level_high_when_M_and_A_present():
    agent = HeuristicNewsAgent()
    result = await agent.analyze(
        title="M&A 발표로 인수 합병 급등, 신고가 돌파",
        body=None,
        symbol="005930",
    )
    assert result.impact_level == "high"
