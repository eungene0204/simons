import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from advisor.agent import StrategyAdvisorAgent
from advisor.schemas import AdvisorRequest, BacktestSummary


def _review(prompt: str, parsed_strategy: dict, backtest_result: BacktestSummary | None = None):
    return StrategyAdvisorAgent().review(
        AdvisorRequest(
            user_prompt=prompt,
            parsed_strategy=parsed_strategy,
            backtest_result=backtest_result,
        )
    )


def _top_learning_advice(result) -> str:
    for item in result.advice:
        if item.title == "전략 실험 근거 기반 개선":
            return item.body
    raise AssertionError("전략 실험 근거 기반 개선 advice가 없습니다.")


def test_advisor_quality_smoke_for_representative_strategy_prompts():
    cases = [
        (
            "ma_concentrated",
            "KOSPI200에서 20일선이 60일선을 돌파하면 사고 60일선 이탈 시 매도, 최대 3종목",
            {
                "universe": ["KOSPI200"],
                "entry_signals": [{"indicator": "ma_cross", "fast": 20, "slow": 60}],
                "exit_signals": [{"indicator": "ma_cross", "fast": 20, "slow": 60, "direction": "down"}],
                "max_positions": 3,
                "initial_capital": 10_000_000,
            },
        ),
        (
            "rsi_reversion",
            "RSI 30 이하 매수, RSI 70 이상 매도",
            {
                "universe": ["KOSPI200"],
                "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
                "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
                "max_positions": 10,
                "initial_capital": 10_000_000,
            },
        ),
        (
            "value_trap",
            "PBR 0.7 이하 저평가주를 10개 매수",
            {
                "universe": ["KOSPI"],
                "entry_signals": [],
                "exit_signals": [],
                "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 0.7}],
                "max_positions": 10,
                "initial_capital": 10_000_000,
            },
        ),
    ]

    for _name, prompt, parsed_strategy in cases:
        result = _review(prompt, parsed_strategy)
        learning_advice = _top_learning_advice(result)

        assert "우선 비교할 후보" in learning_advice
        assert "각 후보를 하나씩만 바꿔 비교" in learning_advice
        assert "추가 백테스트로 먼저 검증" not in learning_advice
        assert "data_sufficiency" not in learning_advice
        assert "confidence=" not in learning_advice


def test_advisor_downgrades_broad_experiment_match_confidence():
    result = _review(
        "KOSPI200에서 20일선이 60일선을 돌파하면 사고 60일선 이탈 시 매도, 최대 3종목",
        {
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "ma_cross", "fast": 20, "slow": 60}],
            "exit_signals": [{"indicator": "ma_cross", "fast": 20, "slow": 60, "direction": "down"}],
            "max_positions": 3,
            "initial_capital": 10_000_000,
        },
    )

    insight = result.strategy_experiment_learning or {}
    assert insight["confidence"] == "low"
    assert insight["matched_patterns"][0]["similarity"] < 0.5
    assert "현재 전략과 완전히 같지는 않으므로" in _top_learning_advice(result)


def test_advisor_keeps_backtest_specific_risk_advice_visible():
    result = _review(
        "52주 신고가 돌파 후 이동평균 이탈 시 매도",
        {
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "breakout_52w"}],
            "exit_signals": [{"indicator": "ma_cross"}],
            "max_positions": 5,
            "stop_loss_pct": 15,
            "initial_capital": 10_000_000,
        },
        BacktestSummary(cagr=0.08, mdd=-0.38, sharpe=0.25, trade_count=80),
    )

    titles = [item.title for item in result.advice]
    assert any("MDD 개선" in title for title in titles)
    assert any("변동성 감소" in title for title in titles)
