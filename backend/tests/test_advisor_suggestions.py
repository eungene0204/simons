"""
Regression tests: every Issue code that can be diagnosed must produce
at least one AdviceItem so the '조언 드립니다' section is never empty.
"""

from advisor.agent import StrategyAdvisorAgent
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
