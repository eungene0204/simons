import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from api import advisor_routes
from advisor.schemas import AdvisorRequest, NewsArticleSignal, NewsContext


@pytest.mark.asyncio
async def test_advisor_route_auto_injects_news_context(monkeypatch):
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
