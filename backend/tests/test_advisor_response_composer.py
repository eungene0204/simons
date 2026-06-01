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
            },
            {
                "strategy_id": "case_rsi_failure",
                "user_prompt": "RSI 단독 평균회귀 손절 없음",
                "strategy_summary": "RSI 실패 평균회귀",
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
                "retrieval_categories": [
                    "similar",
                    "successful_low_risk",
                    "same_market_regime",
                    "same_capital",
                    "same_holding_period",
                    "same_trade_frequency",
                ],
            },
            {
                "strategy_id": "case_rsi_failure",
                "before_backtest": {"cagr": -0.03, "mdd": -0.42, "sharpe": -0.2},
                "after_backtest": {},
                "evaluation": {"advice_success": False},
                "lesson": "손절 없는 RSI 평균회귀는 변동성 확대 구간에서 MDD가 커졌다.",
                "retrieval_categories": ["failed_high_risk"],
            }
        ],
    ))

    assert [section.title for section in result.response_sections] == SECTION_TITLES
    assert "RSI 30 이하 매수, 70 이상 매도" not in result.response_sections[0].body
    assert "백테스트 전이라 성과는 미확정" in result.response_sections[0].body
    assert "검색된 유사 전략 수" in result.response_sections[1].body
    assert "유사 성공/저위험" in result.response_sections[1].body
    assert "유사 실패/고위험" in result.response_sections[1].body
    assert "case_rsi" not in result.response_sections[1].body
    assert "유사 성공 전략의 공통점" in result.response_sections[2].body
    assert "장기 추세 필터" in result.response_sections[2].body
    assert "저위험 검색" in result.response_sections[2].body
    assert "유사 실패 전략의 공통점" in result.response_sections[3].body
    assert "고위험 검색" in result.response_sections[3].body
    assert "시장 레짐 적합성" in result.response_sections[4].body
    assert "동일 레짐" in result.response_sections[4].body
    assert "위험 요소" in result.response_sections[5].body
    assert "사용자 조건 적합 검색" in result.response_sections[5].body
    assert "과최적화 가능성" in result.response_sections[6].body
    assert "개선 조건" in result.response_sections[7].body
    assert "추천 필터" in result.response_sections[8].body
    assert "ATR stop loss" in result.response_sections[8].body
    assert "개선 효과 미확정" in result.response_sections[9].body
    assert "수익성 표현 금지" in result.response_sections[9].body
    assert "조건으로 비교 백테스트해 개선 여부 확인" in result.response_sections[9].body
    assert "앱에서" not in result.response_sections[9].body
    assert "RAG 검색" not in result.response_sections[9].body


def test_advisor_summary_counts_fundamental_filters_as_entry_signals(tmp_path):
    agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(tmp_path))

    result = agent.review(AdvisorRequest(
        user_prompt="KOSPI 대형주 중 PBR 1배 이하 8종목을 6개월 보유하고 -12% 손절",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "entry_signals": [],
            "exit_signals": [],
            "max_positions": 8,
            "hold_period_days": 126,
            "stop_loss_pct": 12,
            "initial_capital": 10_000_000,
        },
    ))

    summary = result.response_sections[0].body
    assert "진입 신호 1개" in summary
    assert "매수 대상 필터" not in summary
    assert "타이밍 진입 신호" not in summary
    assert "다음 액션" in result.response_sections[9].body
    assert "조건으로 비교 백테스트해 개선 여부 확인" in result.response_sections[9].body
    assert "앱에서" not in result.response_sections[9].body
    assert all(len(section.body) <= 240 for section in result.response_sections)


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
    assert "net_effect=positive" in result.response_sections[5].body
    assert "OOS" in result.response_sections[9].body
    assert "OOS 비교 백테스트로 개선 유지 여부 확인" in result.response_sections[9].body
    assert "앱에서" not in result.response_sections[9].body
