"""
Regression tests: every Issue code that can be diagnosed must produce
at least one AdviceItem so the '조언 드립니다' section is never empty.
"""

import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.agent import StrategyAdvisorAgent
from advisor.performance_evaluation import NullLearningProvider
from advisor.schemas import AdvisorRequest

agent = StrategyAdvisorAgent()


def _review(parsed_strategy: dict):
    req = AdvisorRequest(
        user_prompt="테스트 전략",
        parsed_strategy=parsed_strategy,
    )
    return agent.review(req)


def test_no_entry_signals_has_advice():
    result = _review({
        "universe": ["KOSPI200"],
        "entry_signals": [],
        "fundamental_filters": [],
        "stop_loss_pct": 10.0,
        "max_positions": 10,
        "initial_capital": 10_000_000,
    })
    assert len(result.advice) > 0, "조언 항목이 비어있으면 안 됩니다"
    titles = [a.title for a in result.advice]
    assert any("진입 신호" in t for t in titles)


def test_no_stop_loss_has_advice():
    result = _review({
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi"}],
        "fundamental_filters": [],
        "stop_loss_pct": None,
        "max_positions": 10,
        "initial_capital": 10_000_000,
    })
    assert len(result.advice) > 0
    assert any(a.severity in ("high", "medium") for a in result.advice)


def test_no_take_profit_has_advice():
    result = _review({
        "universe": ["KOSPI"],
        "entry_signals": [],
        "exit_signals": [],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        "max_positions": 8,
        "stop_loss_pct": 12.0,
        "take_profit_pct": None,
        "hold_period_days": 126,
        "initial_capital": 10_000_000,
    })
    assert len(result.advice) > 0, "조언 항목이 비어있으면 안 됩니다"
    assert any("익절" in a.title for a in result.advice)


def test_existing_stop_loss_does_not_repeat_stop_loss_addition_advice():
    policy_agent = StrategyAdvisorAgent(learning_provider=NullLearningProvider())
    result = policy_agent.review(AdvisorRequest(
        user_prompt="KOSPI 대형주 중 PBR 1배 이하를 8종목 사고 6개월 보유, -12% 손절",
        parsed_strategy={
            "universe": ["KOSPI"],
            "entry_signals": [],
            "exit_signals": [],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "max_positions": 8,
            "stop_loss_pct": 12.0,
            "take_profit_pct": None,
            "hold_period_days": 126,
            "initial_capital": 10_000_000,
        },
    ))

    advice_text = " ".join(
        " ".join([
            item.title,
            item.body,
            item.proposed_change.description if item.proposed_change else "",
        ])
        for item in result.advice
    )

    assert "손절 조건 추가" not in advice_text
    assert "손절 또는 트레일링 스탑 추가" not in advice_text
    assert any("익절" in item.title for item in result.advice)


def test_ma_crossover_with_exit_does_not_default_to_trailing_stop_experiment():
    policy_agent = StrategyAdvisorAgent(learning_provider=NullLearningProvider())
    result = policy_agent.review(AdvisorRequest(
        user_prompt=(
            "KOSPI 종목 중 골든크로스가 나오면 매수하고, "
            "데드크로스가 나오면 매도합니다. 최대 10개, 손절은 -8%입니다."
        ),
        parsed_strategy={
            "universe": ["KOSPI"],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "fundamental_filters": [],
            "max_positions": 10,
            "stop_loss_pct": 8.0,
            "take_profit_pct": None,
            "trailing_stop_pct": None,
            "hold_period_days": None,
            "initial_capital": 10_000_000,
        },
    ))

    assert all("트레일링 스탑" not in experiment for experiment in result.suggested_experiments)
    assert all("언제 팔아야 할지" not in item.body for item in result.advice)


def test_advice_items_have_body():
    """모든 advice 항목은 title과 body를 가져야 한다."""
    result = _review({
        "entry_signals": [{"indicator": "rsi"}],
        "stop_loss_pct": None,
        "universe": ["KOSPI"],
        "max_positions": 10,
        "initial_capital": 10_000_000,
    })
    for item in result.advice:
        assert item.title, "title이 비어있으면 안 됩니다"
        assert item.severity in ("low", "medium", "high")


def test_issues_always_produce_advice():
    """진단이 있으면 반드시 advice 항목이 생성되어야 한다."""
    scenarios = [
        {"entry_signals": [{"indicator": "rsi"}], "stop_loss_pct": None,
         "universe": ["KOSPI"], "max_positions": 10, "initial_capital": 10_000_000},
        {"entry_signals": [], "fundamental_filters": [], "stop_loss_pct": 10.0,
         "universe": ["KOSPI200"], "max_positions": 10, "initial_capital": 10_000_000},
        {"entry_signals": [{"indicator": "rsi"}], "stop_loss_pct": 1.0,
         "exit_signals": [{"indicator": "rsi"}],
         "universe": ["KOSPI200"], "max_positions": 10, "initial_capital": 10_000_000},
        {"entry_signals": [], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
         "stop_loss_pct": 12.0, "hold_period_days": 126,
         "universe": ["KOSPI"], "max_positions": 8, "initial_capital": 10_000_000},
    ]
    for ps in scenarios:
        result = _review(ps)
        assert len(result.advice) > 0, (
            f"조언 항목이 비어있습니다. strategy={ps}"
        )


def test_low_overfit_advice_omits_zero_filter_message_without_evidence():
    req = AdvisorRequest(
        user_prompt="테스트 전략",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi"}],
            "exit_signals": [{"indicator": "ma_cross"}],
            "fundamental_filters": [],
            "stop_loss_pct": 10.0,
            "take_profit_pct": 15.0,
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    result = agent.review(req)

    assert all(item.title != "과최적화 위험 낮음" for item in result.advice)
    assert all("필터 조건 0개로 적정합니다" not in item.body for item in result.advice)


def test_low_overfit_advice_omits_filter_only_message_without_backtest():
    req = AdvisorRequest(
        user_prompt="테스트 전략",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [],
            "exit_signals": [],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    result = agent.review(req)

    assert all(item.title != "과최적화 위험 낮음" for item in result.advice)
    assert all("필터 조건 1개" not in item.body for item in result.advice)


def test_low_overfit_advice_remains_when_backtest_has_concrete_evidence():
    req = AdvisorRequest(
        user_prompt="테스트 전략",
        parsed_strategy={
            "universe": ["KOSPI"],
            "entry_signals": [{"indicator": "rsi"}],
            "exit_signals": [{"indicator": "ma_cross"}],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
            "stop_loss_pct": 10.0,
            "take_profit_pct": 20.0,
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
        backtest_result={
            "cagr": 0.18,
            "trade_count": 63,
            "mdd": -0.12,
            "sharpe": 0.9,
            "profit_factor": 1.4,
            "win_rate": 0.57,
        },
    )

    result = agent.review(req)

    overfit_items = [item for item in result.advice if item.title == "과최적화 위험 낮음"]
    assert len(overfit_items) == 1
    assert "거래 횟수 63회로 통계적 신뢰도가 충분합니다" in overfit_items[0].body
    assert "필터 조건 1개(PBR)로 적정합니다" in overfit_items[0].body
    assert "필터 조건 0개로 적정합니다" not in overfit_items[0].body
