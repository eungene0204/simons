import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from api import coach_routes
from api.coach_routes import CoachRequest
from advisor.schemas import NewsArticleSignal, NewsContext


class _DummyLock:
    def priority(self, _priority):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _DummyParser:
    def __init__(self):
        self.chat_calls = 0
        self.last_user_message = ""

    def chat(self, _system_prompt, _user_message, max_tokens=512):
        self.chat_calls += 1
        self.last_user_message = _user_message
        assert max_tokens == 400
        return '{"message":"캐시된 코치 응답"}'


def _install_dummy_main(monkeypatch):
    records = []

    def _record_ai_runtime(stage, runtime):
        records.append({"stage": stage, "runtime": runtime})

    def get_ai_runtime_metrics():
        coach_records = [record for record in records if record["stage"] == "coach"]
        return {
            "stages": {
                "coach": {
                    "count": len(coach_records),
                    "cache_hits": sum(1 for record in coach_records if record["runtime"].get("cache_hit") is True),
                }
            }
        }

    dummy_main = types.SimpleNamespace(
        _mlx_inference_lock=_DummyLock(),
        _record_ai_runtime=_record_ai_runtime,
        get_ai_runtime_metrics=get_ai_runtime_metrics,
    )
    monkeypatch.setitem(sys.modules, "main", dummy_main)


def _make_request(**overrides):
    payload = {
        "user_prompt": "PBR 1 이하 전략",
        "parsed_strategy": {
            "description": "large prompt metadata should not be repeated",
            "universe": ["KOSPI200"],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "entry_signals": [],
            "exit_signals": [],
            "max_positions": 10,
            "hold_period_days": 252,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "initial_capital": 10_000_000,
            "canonical_strategy_dsl": {"irrelevant": True},
            "symbols": ["005930", "000660"],
        },
        "advisor_insight": {
            "strategy_score": 70,
            "risk_score": 55,
            "overfit_risk": "low",
            "issues": [
                {"severity": "high", "message": "첫 이슈"},
                {"severity": "medium", "message": "둘째 이슈"},
                {"severity": "low", "message": "잘려야 하는 이슈"},
            ],
            "recommendations": [
                {"priority": 1, "title": "첫 제안", "reason": "핵심"},
                {"priority": 2, "title": "둘째 제안", "reason": "잘림"},
            ],
        },
    }
    payload.update(overrides)
    return CoachRequest(**payload)


def setup_function():
    coach_routes._reset_coach_cache_for_tests()
    coach_routes.set_parser(None)
    if "main" in sys.modules and hasattr(sys.modules["main"], "_reset_ai_runtime_metrics_for_tests"):
        sys.modules["main"]._reset_ai_runtime_metrics_for_tests()


def test_build_user_message_compacts_strategy_context():
    msg = coach_routes._build_user_message(_make_request())

    assert "canonical_strategy_dsl" not in msg
    assert "symbols" not in msg
    assert "large prompt metadata" not in msg
    assert "잘려야 하는 이슈" not in msg
    assert "둘째 제안" not in msg
    assert '"fundamental_filters":[{"metric":"pbr","operator":"<=","value":1}]' in msg


def test_build_user_message_includes_memory_context_when_supplied():
    req = _make_request(
        user_prompt="PBR 1 이하 RSI 30 이하",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
        memory_strategy_cases=[
            {
                "strategy_id": "case_rsi_pbr",
                "user_prompt": "과매도 PBR 저평가 전략",
                "strategy_summary": "PBR + RSI 평균회귀",
                "strategy_dsl": {
                    "universe": ["KOSPI200"],
                    "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 31}],
                    "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 69}],
                    "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
                    "max_positions": 10,
                    "initial_capital": 10_000_000,
                },
            }
        ],
        memory_experiences=[
            {
                "strategy_id": "case_rsi_pbr",
                "before_backtest": {"cagr": 0.04, "mdd": -0.22, "sharpe": 0.4},
                "after_backtest": {"cagr": 0.07, "mdd": -0.16, "sharpe": 0.7},
                "evaluation": {"advice_success": True},
                "lesson": "PBR + RSI 전략은 추세 필터와 비용 민감도 검증이 필요하다.",
            }
        ],
    )

    msg = coach_routes._build_user_message(req)

    assert "[strategy_memory_context" in msg
    assert "confidence:" in msg
    assert "similar_strategy_ids: case_rsi_pbr" in msg
    assert "score=" in msg
    assert "case=case_rsi_pbr" in msg
    assert 'before={"cagr":0.04,"mdd":-0.22,"sharpe":0.4}' in msg
    assert 'after={"cagr":0.07,"mdd":-0.16,"sharpe":0.7}' in msg
    assert "비용 민감도 검증" in msg


def test_system_prompt_requires_memory_evidence_discipline():
    prompt = coach_routes.COACH_SYSTEM_PROMPT

    assert "strategy_memory_context" in prompt
    assert "data_sufficiency가 insufficient" in prompt
    assert "꾸며내지 마라" in prompt
    assert "백테스트 결과가 없으면" in prompt
    assert "제공되지 않은 백테스트 사례" in prompt
    assert "검색/계산/판정 엔진이 아니라" in prompt


@pytest.mark.asyncio
async def test_coach_strategy_reuses_backend_cache(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)

    req = _make_request()
    first = await coach_routes.coach_strategy(req)
    second = await coach_routes.coach_strategy(req)

    assert first.message == "캐시된 코치 응답"
    assert second.message == "캐시된 코치 응답"
    assert first.runtime["cache_hit"] is False
    assert first.runtime["inference_ms"] >= 0
    assert second.runtime["cache_hit"] is True
    assert parser.chat_calls == 1

    metrics = sys.modules["main"].get_ai_runtime_metrics()
    assert metrics["stages"]["coach"]["count"] == 2
    assert metrics["stages"]["coach"]["cache_hits"] == 1


@pytest.mark.asyncio
async def test_coach_strategy_auto_injects_news_context(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)

    monkeypatch.setattr(
        coach_routes,
        "build_news_context_from_strategy",
        lambda _parsed: [
            NewsContext(
                symbol="005930",
                latest_alpha=-0.12,
                risk_alert_level="high",
                articles=[
                    NewsArticleSignal(
                        event_type="earnings_miss",
                        sentiment="negative",
                        impact_direction="down",
                        impact_score=-0.8,
                        confidence_score=0.9,
                    )
                ],
            )
        ],
    )
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())

    req = _make_request(advisor_insight=None, news_agent_insight=None)
    response = await coach_routes.coach_strategy(req)

    assert response.message == "캐시된 코치 응답"
    assert "[news_agent_insight" in parser.last_user_message
    assert "risk_alert=high" in parser.last_user_message
    assert "earnings_miss" in parser.last_user_message


@pytest.mark.asyncio
async def test_coach_strategy_auto_injects_memory_context(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)

    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())
    monkeypatch.setattr(
        coach_routes,
        "load_advisor_memory",
        lambda: (
            [
                {
                    "strategy_id": "case_auto_memory",
                    "user_prompt": "RSI 평균회귀",
                    "strategy_summary": "RSI 평균회귀",
                    "strategy_dsl": {
                        "universe": ["KOSPI200"],
                        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
                        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
                        "max_positions": 10,
                        "initial_capital": 10_000_000,
                    },
                }
            ],
            [
                {
                    "strategy_id": "case_auto_memory",
                    "before_backtest": {"cagr": 0.03, "mdd": -0.25, "sharpe": 0.3},
                    "after_backtest": {"cagr": 0.06, "mdd": -0.18, "sharpe": 0.6},
                    "evaluation": {"advice_success": True},
                    "lesson": "RSI 평균회귀는 장기 추세 필터 검증이 필요하다.",
                }
            ],
        ),
    )

    req = _make_request(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        advisor_insight=None,
        news_agent_insight=None,
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    response = await coach_routes.coach_strategy(req)

    assert response.message == "캐시된 코치 응답"
    assert "[strategy_memory_context" in parser.last_user_message
    assert "case=case_auto_memory" in parser.last_user_message
    assert "장기 추세 필터" in parser.last_user_message


async def _empty_memory():
    return [], []


@pytest.mark.asyncio
async def test_coach_strategy_prefers_vector_memory_context(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)

    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])

    async def _vector_memory(_user_prompt, _parsed_strategy):
        return (
            [
                {
                    "strategy_id": "vector_case",
                    "user_prompt": "RSI vector memory",
                    "strategy_summary": "Vector RSI memory",
                    "strategy_dsl": {
                        "universe": ["KOSPI200"],
                        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
                        "max_positions": 10,
                        "initial_capital": 10_000_000,
                    },
                }
            ],
            [
                {
                    "strategy_id": "vector_case",
                    "before_backtest": {"cagr": 0.02, "mdd": -0.30, "sharpe": 0.2},
                    "after_backtest": {"cagr": 0.05, "mdd": -0.18, "sharpe": 0.6},
                    "evaluation": {"advice_success": True},
                    "lesson": "Vector DB 검색 사례는 변동성 필터 검증이 필요하다.",
                    "retrieval_categories": ["similar", "successful_low_risk"],
                }
            ],
        )

    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", _vector_memory)
    monkeypatch.setattr(
        coach_routes,
        "load_advisor_memory",
        lambda: pytest.fail("load_advisor_memory should not run when vector memory is available"),
    )

    req = _make_request(
        user_prompt="RSI 30 이하 매수",
        advisor_insight=None,
        news_agent_insight=None,
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    response = await coach_routes.coach_strategy(req)

    assert response.message == "캐시된 코치 응답"
    assert "[strategy_memory_context" in parser.last_user_message
    assert "case=vector_case" in parser.last_user_message
    assert "변동성 필터 검증" in parser.last_user_message
