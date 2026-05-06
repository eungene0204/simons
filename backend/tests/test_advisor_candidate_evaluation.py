import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.advice_evaluator import build_reusable_lesson, evaluate_advice
from advisor.agent import StrategyAdvisorAgent
from advisor.candidate_generator import generate_candidate_strategy
from advisor.schemas import AdviceItem, AdvisorRequest, BacktestSummary, ProposedChange


def test_generate_candidate_strategy_applies_proposed_changes():
    base = {
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi", "threshold": 30}],
        "fundamental_filters": [],
        "max_positions": 3,
        "initial_capital": 10_000_000,
    }
    advice = [
        AdviceItem(
            severity="high",
            title="손절 추가",
            body="",
            proposed_change=ProposedChange(
                field="stop_loss_pct",
                action="set",
                value=10,
                description="10% 손절",
            ),
        ),
        AdviceItem(
            severity="medium",
            title="거래대금 필터",
            body="",
            proposed_change=ProposedChange(
                field="fundamental_filters",
                action="add",
                value={"metric": "trading_value", "operator": ">=", "value": 3.0},
                description="거래대금 3억 이상",
            ),
        ),
    ]

    candidate = generate_candidate_strategy(base, advice)

    assert candidate is not None
    assert candidate["stop_loss_pct"] == 10
    assert candidate["fundamental_filters"] == [{"metric": "trading_value", "operator": ">=", "value": 3.0}]
    assert candidate["_advisor_candidate"]["requires_backtest"] is True
    assert base.get("stop_loss_pct") is None


def test_evaluate_advice_requires_risk_adjusted_improvement_not_cagr_only():
    before = {"cagr": 0.08, "mdd": -0.18, "sharpe": 0.8, "trade_count": 40}
    after = {"cagr": 0.15, "mdd": -0.35, "sharpe": 0.5, "trade_count": 45}

    evaluation = evaluate_advice(before, after, {"oos_available": True, "oos_delta": 0.0})

    assert evaluation["advice_success"] is False
    assert "cagr" in evaluation["improved_metrics"]
    assert "mdd" in evaluation["worsened_metrics"]
    assert "sharpe" in evaluation["worsened_metrics"]
    assert evaluation["net_effect"] in {"neutral", "negative"}


def test_evaluate_advice_fails_when_trade_count_explodes():
    before = {"cagr": 0.08, "mdd": -0.25, "sharpe": 0.7, "trade_count": 30}
    after = {"cagr": 0.12, "mdd": -0.18, "sharpe": 0.9, "trade_count": 90}

    evaluation = evaluate_advice(before, after, {"oos_available": True, "oos_delta": 0.0})

    assert evaluation["advice_success"] is False
    assert "거래 횟수" in evaluation["reason"]


def test_evaluate_advice_marks_balanced_improvement_success():
    before = {"cagr": 0.08, "mdd": -0.25, "sharpe": 0.7, "calmar": 0.32, "trade_count": 35}
    after = {"cagr": 0.11, "mdd": -0.18, "sharpe": 0.9, "calmar": 0.61, "trade_count": 45}

    evaluation = evaluate_advice(before, after, {"oos_available": True, "oos_delta": 0.01})

    assert evaluation["advice_success"] is True
    assert evaluation["net_effect"] == "positive"
    assert evaluation["overfitting_risk"] == "low"


def test_advisor_response_includes_candidate_and_evaluation():
    agent = StrategyAdvisorAgent()
    result = agent.review(AdvisorRequest(
        user_prompt="RSI 전략인데 손절 없이 테스트",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi"}],
            "fundamental_filters": [],
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
        backtest_result=BacktestSummary(cagr=0.08, mdd=-0.25, sharpe=0.7, calmar=0.32, trade_count=35),
        candidate_backtest_result=BacktestSummary(cagr=0.11, mdd=-0.18, sharpe=0.9, calmar=0.61, trade_count=45),
        evaluation_context={"oos_available": True, "oos_delta": 0.01},
    ))

    assert result.candidate_strategy is not None
    assert result.candidate_strategy.get("stop_loss_pct") is not None
    assert result.advice_evaluation is not None
    assert result.advice_evaluation["advice_success"] is True


def test_build_reusable_lesson_is_specific_and_reusable():
    lesson = build_reusable_lesson(
        "RSI 평균회귀",
        {
            "advice_success": False,
            "reason": "CAGR은 개선되었지만 MDD가 크게 증가했습니다.",
        },
    )

    assert "RSI 평균회귀" in lesson
    assert "비슷한 전략" in lesson
    assert "CAGR은 개선" in lesson
