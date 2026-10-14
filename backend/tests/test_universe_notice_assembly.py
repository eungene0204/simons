"""Universe notices depend on per-expression evidence and the final state."""
from types import SimpleNamespace

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


def report_for(*terms):
    _, report = run_validation(StrategyIntent.model_validate({"intent": "CREATE_STRATEGY",
        "strategy": {"universe": {"markets": ["KOSPI"], "sectors": list(terms)}}}))
    return report


def test_resolved_theme_has_no_stale_catalog_notice():
    from strategy_conversation.response.notice_assembly import assemble_sector_notices, remember_resolution
    report = report_for("북극항로")
    parsed = SimpleNamespace(target_symbols=["005930", "000660"], sector=None)
    receipts = []
    remember_resolution(receipts, "북극항로", parsed, "theme_chain")
    output = assemble_sector_notices(report, parsed, receipts)
    assert output["notices"] == [] and output["unsupported_features"] == []
    assert output["decisions"][0]["resolved"] is True
    assert report.errors and report.unsupported_features
    assert "_universe_findings" not in report.model_dump()


def test_partial_success_keeps_other_expression_and_condition_errors():
    from strategy_conversation.response.notice_assembly import assemble_sector_notices, initial_validation_notices, remember_resolution
    report = report_for("북극항로", "없는테마")
    report.errors.append("another condition error")
    report.unsupported_features.append("unrelated condition")
    report.warnings.append("another warning")
    parsed = SimpleNamespace(target_symbols=["005930"], sector=None)
    receipts = []
    remember_resolution(receipts, "북극항로", parsed, "theme_chain")
    output = assemble_sector_notices(report, parsed, receipts)
    assert output["notices"] == ["'없는테마'은(는) 지원 섹터 목록에 없습니다"]
    assert output["unsupported_features"] == ["unrelated condition"]
    assert initial_validation_notices(report) == ["another warning", "another condition error"]


def test_unrelated_symbols_and_overwritten_resolution_do_not_hide_a_failure():
    from strategy_conversation.response.notice_assembly import assemble_sector_notices, remember_resolution
    report = report_for("북극항로")
    parsed = SimpleNamespace(target_symbols=["005930"], sector=None)
    assert assemble_sector_notices(report, parsed, [])["notices"]
    receipts = []
    remember_resolution(receipts, "북극항로", parsed, "theme_chain")
    parsed.target_symbols = ["000660"]
    assert assemble_sector_notices(report, parsed, receipts)["notices"]


def test_learned_sector_is_checked_in_the_final_sector_field():
    from strategy_conversation.response.notice_assembly import assemble_sector_notices, remember_resolution
    report = report_for("학습표현")
    parsed = SimpleNamespace(target_symbols=["005930"], sector=["기계/장비"])
    receipts = []
    remember_resolution(receipts, "학습표현", parsed, "sector_grounding", field="sector")
    assert not assemble_sector_notices(report, parsed, receipts)["notices"]
    parsed.sector = None
    assert assemble_sector_notices(report, parsed, receipts)["notices"]


def test_scope_question_is_not_resolution_or_an_unsupported_notice():
    from strategy_conversation.response.notice_assembly import assemble_sector_notices
    report = report_for("범위표현", "다른미해결")
    parsed = SimpleNamespace(target_symbols=[], sector=None)
    output = assemble_sector_notices(report, parsed, [], scope_terms={"범위표현"})
    assert output["decisions"][0]["awaiting_scope"] is True
    assert output["decisions"][0]["resolved"] is False
    assert output["notices"] == ["'다른미해결'은(는) 지원 섹터 목록에 없습니다"]


def test_label_with_two_known_terms_is_not_hidden_by_partial_success():
    from strategy_conversation.response.notice_assembly import assemble_sector_notices, remember_resolution
    report = report_for("북극항로", "미확인테마")
    report.unsupported_features.append("북극항로와 미확인테마")
    parsed = SimpleNamespace(target_symbols=["005930"], sector=None)
    receipts = []
    remember_resolution(receipts, "북극항로", parsed, "theme_chain")
    output = assemble_sector_notices(report, parsed, receipts)
    assert "북극항로와 미확인테마" not in output["unsupported_features"]
    assert any("북극항로와 미확인테마" in notice and "'북극항로' 투자 대상: 반영됨" in notice
               and "'미확인테마' 투자 대상: 미해결" in notice for notice in output["notices"])


def test_planner_receipts_preserve_each_application_before_a_later_overwrite(monkeypatch):
    import engine.nl_parser as parser
    from strategy_conversation import primary
    from strategy_conversation.response.notice_assembly import assemble_sector_notices
    from test_planner_first import _plan_result
    def apply(parsed, term):
        parsed.target_symbols = {"북극항로": ["005930"], "미확인테마": ["000660"]}[term]
        return "applied"
    monkeypatch.setattr(parser, "apply_theme_companies", apply)
    observations = [("kg_theme_companies", term, {"found": True, "companies": [{"symbol": "synthetic"}]})
                    for term in ("북극항로", "미확인테마")]
    parsed = SimpleNamespace(universe=["KOSPI"], target_symbols=[], sector=None)
    receipts = []
    primary._apply_planner_first_universe(_plan_result(observations), parsed, [], resolution_evidence=receipts)
    output = assemble_sector_notices(report_for("북극항로", "미확인테마"), parsed, receipts)
    assert [d["resolved"] for d in output["decisions"]] == [False, True]
    assert receipts[0]["value"] == ["005930"]


def test_mini_planner_sector_application_supplies_final_state_evidence(monkeypatch):
    import engine.nl_parser as parser
    from strategy_conversation import primary
    from strategy_conversation.response.notice_assembly import assemble_sector_notices
    monkeypatch.setattr(parser, "apply_theme_companies", lambda *a: None)
    monkeypatch.setattr(primary, "_apply_theme_via_canonical_match", lambda *a: False)
    monkeypatch.setattr("strategy_conversation.planner.shadow._default_chat", lambda: None)
    monkeypatch.setattr("strategy_conversation.planner.mini_planner.plan_universe_resolution",
                        lambda *a: SimpleNamespace(outcome="resolved", sector="기계/장비", companies=[]))
    parsed = SimpleNamespace(target_symbols=[], sector=None)
    receipts = []
    assert primary._resolve_sector_terms_planner_primary(parsed, ["학습표현"], [],
                                                        resolution_evidence=receipts) == (None, None)
    assert assemble_sector_notices(report_for("학습표현"), parsed, receipts)["notices"] == []
