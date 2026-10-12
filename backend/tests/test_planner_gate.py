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


def test_llm_market_code_settles_unknown_market_wording():
    """2026-10-11 triage: '다우지수 종목'이 표에 없어 CONCEPT → planner가 4턴을 돌다 예산 소진(50건).
    보조 추출 LLM이 구절별로 적은 정본 시장 코드로 지름길을 탄다."""
    us = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["DOW30"]}}})
    plan = settle_plain_markets(us, ParseEvidence(universe_terms=["다우지수 종목"],
                                                  universe_markets=[["DOW30"]]))
    assert plan.outcome == "universe_settled" and plan.llm_turns == 0
    assert plan.executed["market_0"].observation == {"universe_type": "MARKET", "canonical": "DOW30"}


@pytest.mark.parametrize("terms,markets,universe", [
    (["다우지수 종목"], [None], {"markets": ["DOW30"]}),          # LLM이 시장만이 아니라고 봄
    (["다우지수 종목"], [["SP500"]], {"markets": ["DOW30"]}),       # 인터프리터와 불일치
    (["삼성전자"], [["KOSPI"]], {}),                                  # 표가 종목으로 짚은 구절은 덮지 않음
    (["코스피", "보안 관련주"], [["KOSPI"], None], {}),               # 한 구절이라도 시장이 아니면
])
def test_llm_market_code_never_overrides_narrowing(terms, markets, universe):
    assert settle_plain_markets(intent(**universe), ParseEvidence(
        universe_terms=terms, universe_markets=markets)) is None


def test_one_quote_naming_two_markets_settles_both():
    both = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI", "KOSDAQ"]}}})
    plan = settle_plain_markets(both, ParseEvidence(universe_terms=["KOSPI/KOSDAQ 공통 유니버스"],
                                                    universe_markets=[["KOSPI", "KOSDAQ"]]))
    assert plan is not None and plan.outcome == "universe_settled"
    assert {e.observation["canonical"] for e in plan.executed.values()} == {"KOSPI", "KOSDAQ"}
    only_kospi = settle_plain_markets(both, ParseEvidence(
        universe_terms=["KOSPI/KOSDAQ 공통 유니버스"], universe_markets=[["KOSPI"]]))
    assert only_kospi is None
