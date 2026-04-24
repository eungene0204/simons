"""
Regression tests: every Issue code that can be diagnosed must produce
at least one Recommendation so the '해결 방법' section is never empty
when '진단' has entries.
"""

from advisor.agent import StrategyAdvisorAgent
from advisor.schemas import AdvisorRequest

agent = StrategyAdvisorAgent()


def _review(parsed_strategy: dict) -> tuple[list, list]:
    req = AdvisorRequest(
        user_prompt="테스트 전략",
        parsed_strategy=parsed_strategy,
    )
    result = agent.review(req)
    return result.issues, result.recommendations


def test_no_entry_signals_has_recommendation():
    """NO_ENTRY_SIGNALS issue must produce a recommendation."""
    issues, recs = _review({
        "universe": ["KOSPI200"],
        "entry_signals": [],
        "fundamental_filters": [],
        "stop_loss_pct": 10.0,
        "max_positions": 10,
        "initial_capital": 10_000_000,
    })
    issue_codes = {i.code for i in issues}
    assert "NO_ENTRY_SIGNALS" in issue_codes
    assert len(recs) > 0, "해결 방법이 비어있으면 안 됩니다"


def test_no_stop_loss_has_recommendation():
    """NO_STOP_LOSS issue must produce a recommendation."""
    issues, recs = _review({
        "universe": ["KOSPI200"],
        "entry_signals": [{"indicator": "rsi"}],
        "fundamental_filters": [],
        "stop_loss_pct": None,
        "max_positions": 10,
        "initial_capital": 10_000_000,
    })
    issue_codes = {i.code for i in issues}
    assert "NO_STOP_LOSS" in issue_codes or "MISSING_EXIT_RULE" in issue_codes
    assert len(recs) > 0


def test_no_take_profit_has_recommendation():
    """NO_TAKE_PROFIT issue must produce a recommendation."""
    issues, recs = _review({
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
    issue_codes = {i.code for i in issues}
    assert "NO_TAKE_PROFIT" in issue_codes
    assert len(recs) > 0, "해결 방법이 비어있으면 안 됩니다"


def test_issues_always_have_recommendations():
    """When issues exist, recommendations must not be empty."""
    scenarios = [
        # No exit, no stop
        {"entry_signals": [{"indicator": "rsi"}], "stop_loss_pct": None,
         "universe": ["KOSPI"], "max_positions": 10, "initial_capital": 10_000_000},
        # No entry signals
        {"entry_signals": [], "fundamental_filters": [], "stop_loss_pct": 10.0,
         "universe": ["KOSPI200"], "max_positions": 10, "initial_capital": 10_000_000},
        # Too tight stop
        {"entry_signals": [{"indicator": "rsi"}], "stop_loss_pct": 1.0,
         "exit_signals": [{"indicator": "rsi"}],
         "universe": ["KOSPI200"], "max_positions": 10, "initial_capital": 10_000_000},
        # Stop loss only, no take profit (screenshot scenario)
        {"entry_signals": [], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
         "stop_loss_pct": 12.0, "hold_period_days": 126,
         "universe": ["KOSPI"], "max_positions": 8, "initial_capital": 10_000_000},
    ]
    for ps in scenarios:
        issues, recs = _review(ps)
        if issues:
            assert len(recs) > 0, (
                f"이슈가 있는데 해결방안이 없습니다. "
                f"issue_codes={[i.code for i in issues]}, strategy={ps}"
            )
