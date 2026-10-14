"""Final state consumes structured receipts from legacy notice producers."""
from engine.nl_parser import ParsedStrategy
from strategy_conversation.response.notice_evidence import NoticeList, producer, project
from strategy_conversation.response.notice_assembly import assemble_response_notices


def test_changed_owned_field_removes_earlier_notice():
    parsed = ParsedStrategy(initial_capital=1000000)
    result = {"parsed": parsed, "notices": producer(["초기 자금을 조정했어요"], "minimums", parsed,
                                                   fields=["initial_capital"])}
    project(result)
    parsed.initial_capital = 10000000
    decisions = project(result)
    assert result["notices"] == []
    assert decisions[0]["status"] == "STALE"


def test_independent_field_does_not_discard_minimum_notice():
    parsed = ParsedStrategy(initial_capital=300)
    notes = NoticeList(parsed, "minimums")
    parsed.initial_capital = 1000000
    notes.append("초기 자금을 조정했어요")
    result = {"parsed": parsed, "notices": notes}
    project(result)
    parsed.max_positions = 12
    project(result)
    assert result["notices"] == ["초기 자금을 조정했어요"]


def test_every_unwrapped_producer_gets_a_structured_receipt():
    result = {"parsed": ParsedStrategy(), "notices": ["기존 안내"]}
    decisions = project(result)
    assert decisions[0]["producer"] == "response_projection"
    assert decisions[0]["fields"]
    assert decisions[0]["status"] == "CURRENT"


def test_transition_remains_an_explanation_of_held_change():
    result = {"parsed": ParsedStrategy(), "notices": producer(["변경을 보류했어요"], "domain_approval",
                                                             kind="TRANSITION")}
    project(result)
    result["parsed"].max_positions = 12
    project(result)
    assert result["notices"] == ["변경을 보류했어요"]


def test_api_removes_all_internal_notice_evidence():
    result = {"parsed": ParsedStrategy(), "notices": ["기존 안내"]}
    assemble_response_notices(result, consume=True)
    assert "_notice_evidence" not in result
