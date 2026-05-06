import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.memory_retriever import retrieve_memory_context
from advisor.similarity import extract_structural_features, search_similar_strategies, structural_similarity
from advisor.strategy_identity import canonical_strategy_string, strategy_id_for
from advisor.agent import StrategyAdvisorAgent
from advisor.experiment_learning import ExperimentLearningProvider
from advisor.schemas import AdvisorRequest


def _rsi_dsl(threshold=30, exit_threshold=70):
    return {
        "universe": ["KOSPI200"],
        "entry_signals": [
            {"indicator": "rsi", "operator": "<=", "threshold": threshold, "period": 14}
        ],
        "exit_signals": [
            {"indicator": "rsi", "operator": ">=", "threshold": exit_threshold, "period": 14}
        ],
        "stop_loss_pct": 5,
        "max_positions": 10,
        "backtest_period": "3y",
        "initial_capital": 10_000_000,
    }


def _macd_dsl():
    return {
        "universe": ["KOSPI200"],
        "entry_signals": [
            {"indicator": "macd", "operator": "cross_up", "threshold": 0}
        ],
        "exit_signals": [
            {"indicator": "macd", "operator": "cross_down", "threshold": 0}
        ],
        "max_positions": 10,
        "backtest_period": "3y",
        "initial_capital": 10_000_000,
    }


def test_strategy_identity_ignores_volatile_fields_and_normalizes_numbers():
    left = {
        "id": "draft",
        "name": "RSI draft",
        "entry_signals": [{"threshold": 30.0, "indicator": "rsi"}],
        "initial_capital": 10_000_000.0,
    }
    right = {
        "entry_signals": [{"indicator": "rsi", "threshold": 30}],
        "initial_capital": 10_000_000,
    }

    assert canonical_strategy_string(left) == canonical_strategy_string(right)
    assert strategy_id_for(left) == strategy_id_for(right)


def test_structural_similarity_matches_same_dsl_despite_different_wording():
    current = extract_structural_features(_rsi_dsl())
    past = extract_structural_features(_rsi_dsl(threshold=31, exit_threshold=69))
    unrelated = extract_structural_features(_macd_dsl())

    assert structural_similarity(current, past) > 0.65
    assert structural_similarity(current, unrelated) < 0.35


def test_search_filters_text_only_strategy_when_dsl_structure_differs():
    current_dsl = _rsi_dsl()
    cases = [
        {
            "strategy_id": "case_text_only_macd",
            "user_prompt": "RSI 30 이하 매수, 70 이상 매도처럼 과매도 과매수 표현이 들어간 설명",
            "strategy_summary": "텍스트는 RSI와 비슷하지만 실제 DSL은 MACD 전환 전략",
            "strategy_dsl": _macd_dsl(),
        },
        {
            "strategy_id": "case_structural_rsi",
            "user_prompt": "과매도 구간에서 사고 과매수 구간에서 판다",
            "strategy_summary": "RSI 평균회귀 구조",
            "strategy_dsl": _rsi_dsl(threshold=31, exit_threshold=69),
        },
    ]

    results = search_similar_strategies(
        "RSI 30 이하 매수, 70 이상 매도",
        current_dsl,
        cases,
        top_k=2,
    )

    assert results[0].strategy_id == "case_structural_rsi"
    assert all(item.strategy_id != "case_text_only_macd" for item in results)


def test_search_deduplicates_strategy_ids_by_best_ranked_case():
    current_dsl = _rsi_dsl()
    cases = [
        {
            "strategy_id": "case_rsi",
            "user_prompt": "RSI 언급은 있지만 구조 정보가 부족한 오래된 기록",
            "strategy_dsl": {"universe": ["KOSPI200"]},
        },
        {
            "strategy_id": "case_rsi",
            "user_prompt": "과매도 구간에서 사고 과매수 구간에서 판다",
            "strategy_summary": "RSI 평균회귀 구조",
            "strategy_dsl": _rsi_dsl(threshold=31, exit_threshold=69),
        },
    ]

    results = search_similar_strategies(
        "RSI 30 이하 매수, 70 이상 매도",
        current_dsl,
        cases,
        top_k=5,
    )

    assert [item.strategy_id for item in results] == ["case_rsi"]
    assert results[0].structure_score > 0.65


def test_memory_context_returns_retrieved_cases_and_data_sufficiency():
    current_dsl = _rsi_dsl()
    strategy_cases = [
        {
            "strategy_id": "case_structural_rsi",
            "user_prompt": "과매도 구간에서 사고 과매수 구간에서 판다",
            "strategy_summary": "RSI 평균회귀 구조",
            "strategy_dsl": _rsi_dsl(threshold=31, exit_threshold=69),
        }
    ]
    experiences = [
        {
            "strategy_id": "case_structural_rsi",
            "before_backtest": {"cagr": 0.05, "mdd": -0.28, "sharpe": 0.4},
            "after_backtest": {"cagr": 0.07, "mdd": -0.18, "sharpe": 0.7},
            "evaluation": {"advice_success": True},
            "lesson": "RSI 단독 평균회귀는 장기 추세 필터를 함께 검증해야 한다.",
        }
    ]

    context = retrieve_memory_context(
        "RSI 30 이하 매수, 70 이상 매도",
        current_dsl,
        strategy_cases,
        experiences,
    )

    assert context["data_sufficiency"] == "sufficient"
    assert context["confidence"] in {"medium", "high"}
    assert context["similar_strategy_ids"] == ["case_structural_rsi"]
    assert context["retrieved_cases"][0]["lesson"].startswith("RSI 단독")
    assert context["search_quality"]["retrieved_count"] == 1


def test_memory_context_deduplicates_experiences_for_same_strategy_id():
    current_dsl = _rsi_dsl()
    strategy_cases = [
        {
            "strategy_id": "case_structural_rsi",
            "user_prompt": "과매도 구간에서 사고 과매수 구간에서 판다",
            "strategy_summary": "RSI 평균회귀 구조",
            "strategy_dsl": _rsi_dsl(threshold=31, exit_threshold=69),
        }
    ]
    experiences = [
        {
            "strategy_id": "case_structural_rsi",
            "before_backtest": {"cagr": 0.06},
            "after_backtest": {"cagr": 0.08},
            "evaluation": {"advice_success": True},
            "lesson": "최신 RSI 경험",
        },
        {
            "strategy_id": "case_structural_rsi",
            "before_backtest": {"cagr": 0.01},
            "after_backtest": {"cagr": 0.02},
            "evaluation": {"advice_success": False},
            "lesson": "오래된 RSI 경험",
        },
    ]

    context = retrieve_memory_context(
        "RSI 30 이하 매수, 70 이상 매도",
        current_dsl,
        strategy_cases,
        experiences,
    )

    assert len(context["retrieved_cases"]) == 1
    assert context["retrieved_cases"][0]["lesson"] == "최신 RSI 경험"


def test_advisor_response_includes_memory_context_and_advice(tmp_path):
    current_dsl = _rsi_dsl()
    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))

    result = agent.review(AdvisorRequest(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        parsed_strategy=current_dsl,
        memory_strategy_cases=[
            {
                "strategy_id": "case_structural_rsi",
                "user_prompt": "과매도 구간에서 사고 과매수 구간에서 판다",
                "strategy_summary": "RSI 평균회귀 구조",
                "strategy_dsl": _rsi_dsl(threshold=31, exit_threshold=69),
            }
        ],
        memory_experiences=[
            {
                "strategy_id": "case_structural_rsi",
                "before_backtest": {"cagr": 0.05, "mdd": -0.28, "sharpe": 0.4},
                "after_backtest": {"cagr": 0.07, "mdd": -0.18, "sharpe": 0.7},
                "evaluation": {"advice_success": True},
                "lesson": "RSI 단독 평균회귀는 장기 추세 필터를 함께 검증해야 한다.",
            }
        ],
    ))

    assert result.strategy_memory_context is not None
    assert result.strategy_memory_context["data_sufficiency"] == "sufficient"
    assert any(item.title == "유사 전략 경험 기반 점검" for item in result.advice)
    memory_item = next(item for item in result.advice if item.title == "유사 전략 경험 기반 점검")
    assert "Experience Memory" in memory_item.body
    assert "투자 추천이 아니라" in memory_item.body


def test_advisor_discloses_insufficient_memory_context(tmp_path):
    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))

    result = agent.review(AdvisorRequest(
        user_prompt="RSI 30 이하 매수",
        parsed_strategy=_rsi_dsl(),
        memory_strategy_cases=[],
        memory_experiences=[],
    ))

    assert result.strategy_memory_context is None

    result_with_unmatched_memory = agent.review(AdvisorRequest(
        user_prompt="RSI 30 이하 매수",
        parsed_strategy=_rsi_dsl(),
        memory_strategy_cases=[{"strategy_id": "unrelated", "strategy_dsl": _macd_dsl()}],
        memory_experiences=[],
    ))

    assert result_with_unmatched_memory.strategy_memory_context is not None
    assert result_with_unmatched_memory.strategy_memory_context["data_sufficiency"] == "insufficient"
    assert result_with_unmatched_memory.strategy_memory_context["confidence"] == "low"
    assert result_with_unmatched_memory.strategy_memory_context["search_quality"]["matched_count"] == 0
    memory_item = next(item for item in result_with_unmatched_memory.advice if item.title == "유사 전략 경험 기반 점검")
    assert "유사 전략 검색 결과가 부족" in memory_item.body
    assert "낮은 신뢰도" in memory_item.body
