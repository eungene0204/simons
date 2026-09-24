import pytest
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.parse_evidence import ParseEvidence
from strategy_conversation.runtime.planner_gate import settle_plain_markets


def intent(**universe):
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI"], **universe}}})


def test_market_only_uses_canonical_observation_without_llm():
    plan = settle_plain_markets(intent(), ParseEvidence(universe_terms=["코스피"]))
    assert plan.outcome == "universe_settled" and plan.llm_turns == 0
    assert plan.executed["market_0"].observation["canonical"] == "KOSPI"


@pytest.mark.parametrize("terms,universe", [
    (None, {}), ([], {}), (["보안주"], {}), (["코스피", "보안주"], {}),
    (["코스닥"], {}), (["코스피"], {"markets": []}),
    (["코스피"], {"sectors": ["보안주"]}), (["코스피"], {"exclude_sectors": ["은행"]}),
    (["코스피"], {"symbols": ["삼성전자"]}), (["ETF"], {"markets": ["ETF"]}),
])
def test_omissions_conflicts_themes_and_restrictions_keep_planner(terms, universe):
    assert settle_plain_markets(intent(**universe), ParseEvidence(universe_terms=terms)) is None
