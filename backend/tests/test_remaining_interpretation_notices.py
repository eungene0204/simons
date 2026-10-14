"""Application evidence must survive final API state changes without false notices."""
from engine.nl_parser import ParsedStrategy
from strategy_conversation.interpreter.models import StrategySpec, ValidationReport
from strategy_conversation.response.notice_assembly import (
    assemble_response_notices, notice_context, remember_resolution,
)


def test_etf_reflection_does_not_report_the_applied_theme_as_unsupported():
    report = ValidationReport(unsupported_features=["배당"])
    strategy = StrategySpec(universe={"markets": ["ETF"], "etf_theme": "배당"})
    parsed = ParsedStrategy(universe=["ETF"], etf_theme="배당")
    receipts = []
    remember_resolution(receipts, "배당", parsed, "compiled_etf", field="etf_theme")
    result = {"parsed": parsed, "notices": [], "_notice_context":
              notice_context(report, strategy, "배당 ETF", receipts)}
    assemble_response_notices(result)
    assert result["notices"] == []
    assert report.unsupported_features == ["배당"]


def test_api_removal_of_reflected_theme_recalculates_notice():
    report = ValidationReport(unsupported_features=["배당"])
    parsed = ParsedStrategy(universe=["ETF"], etf_theme="배당")
    receipts = []
    remember_resolution(receipts, "배당", parsed, "compiled_etf", field="etf_theme")
    result = {"parsed": parsed, "notices": [], "_notice_context":
              notice_context(report, StrategySpec(), "배당 ETF", receipts)}
    assemble_response_notices(result)
    parsed.etf_theme = None
    assemble_response_notices(result, consume=True)
    assert any("배당" in notice and "반영하지" in notice for notice in result["notices"])
    assert "_notice_context" not in result


def test_api_final_assembly_accepts_dict_parsed_and_is_idempotent():
    report = ValidationReport(unsupported_features=["파동 이론"])
    result = {"parsed": ParsedStrategy(description="x").model_dump(), "notices": ["기존 안내", "기존 안내"],
              "_notice_context": notice_context(report, StrategySpec(), "파동 이론으로 전략 작성")}
    assemble_response_notices(result)
    notices = list(result["notices"])
    assemble_response_notices(result)
    assert result["notices"] == notices
    assert notices.count("기존 안내") == 1
    assert any("파동 이론" in notice for notice in notices)


def test_scope_pending_has_no_false_unsupported_notice():
    report = ValidationReport(unsupported_features=["북극항로"])
    result = {"parsed": ParsedStrategy(description="x"), "notices": [],
              "clarification_question": "북극항로의 어느 범위인가요?",
              "_notice_context": notice_context(report, StrategySpec(), "북극항로로 변경",
                                                 scope_terms=["북극항로"])}
    assemble_response_notices(result)
    assert not any("지원하지" in notice or "반영하지" in notice for notice in result["notices"])


def test_unrelated_symbols_are_not_evidence_of_theme_application():
    report = ValidationReport(unsupported_features=["북극항로"])
    result = {"parsed": ParsedStrategy(target_symbols=["005930"]), "notices": [],
              "_notice_context": notice_context(report, StrategySpec(), "북극항로로 변경")}
    assemble_response_notices(result)
    assert any("북극항로" in notice and "반영하지" in notice for notice in result["notices"])


def test_dropped_condition_quote_cannot_suppress_an_unsupported_report():
    report = ValidationReport(unsupported_features=["PER 기준"])
    strategy = StrategySpec(entry_conditions=[{"factor": "fundamental.per", "operator": "<=",
                                               "value": 10, "source_text": "PER 기준"}])
    result = {"parsed": ParsedStrategy(description="x"), "notices": [], "_notice_context":
              notice_context(report, strategy, "PER 기준으로 종목 선정")}
    assemble_response_notices(result)
    assert any("PER 기준" in notice for notice in result["notices"])
