import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.agent import StrategyAdvisorAgent
from advisor.experiment_learning import ExperimentLearningProvider
from advisor.response_composer import SECTION_TITLES
from advisor.schemas import AdvisorRequest, BacktestSummary


def _rsi_strategy():
    return {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
        "max_positions": 10,
        "initial_capital": 10_000_000,
    }


def test_advisor_response_sections_follow_required_order(tmp_path):
    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))

    result = agent.review(AdvisorRequest(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        parsed_strategy=_rsi_strategy(),
        memory_strategy_cases=[
            {
                "strategy_id": "case_rsi",
                "user_prompt": "과매도 매수 과매수 매도",
                "strategy_summary": "RSI 평균회귀",
                "strategy_dsl": _rsi_strategy(),
            }
        ],
        memory_experiences=[
            {
                "strategy_id": "case_rsi",
                "before_backtest": {"cagr": 0.05, "mdd": -0.28, "sharpe": 0.4},
                "after_backtest": {"cagr": 0.07, "mdd": -0.18, "sharpe": 0.7},
                "evaluation": {"advice_success": True},
                "lesson": "RSI 평균회귀는 장기 추세 필터와 함께 검증해야 한다.",
            }
        ],
    ))

    assert [section.title for section in result.response_sections] == SECTION_TITLES
    assert "현재 백테스트 결과가 없어 성과는 단정하지 않습니다" in result.response_sections[0].body
    assert "case_rsi" in result.response_sections[2].body
    assert "장기 추세 필터" in result.response_sections[3].body
    assert "개선 후 백테스트 결과가 없어" in result.response_sections[5].body
    assert "수익성 표현은 금지" in result.response_sections[6].body


def test_advisor_response_sections_include_evaluation_when_available(tmp_path):
    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))

    result = agent.review(AdvisorRequest(
        user_prompt="RSI 전략 손절 보강",
        parsed_strategy={
            **_rsi_strategy(),
            "stop_loss_pct": None,
        },
        backtest_result=BacktestSummary(cagr=0.06, mdd=-0.24, sharpe=0.5, calmar=0.25, trade_count=30),
        candidate_backtest_result=BacktestSummary(cagr=0.09, mdd=-0.16, sharpe=0.8, calmar=0.56, trade_count=35),
        evaluation_context={"oos_available": True, "oos_delta": 0.0},
    ))

    assert [section.title for section in result.response_sections] == SECTION_TITLES
    assert result.advice_evaluation is not None
    assert "net_effect=positive" in result.response_sections[6].body
    assert "OOS 검증" in result.response_sections[7].body
