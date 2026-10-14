"""Regression checks for QA inputs, independently of model interpretation."""
import importlib.util
from pathlib import Path

import pytest


def load_qa():
    path = Path(__file__).resolve().parents[2] / "scripts/qa_free_input.py"
    spec = importlib.util.spec_from_file_location("qa_input_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_filter_checks_all_conditions_and_rejects_missing_zero():
    qa = load_qa()
    assert qa.filt("per", "<=", 10)({"fundamental_filters": [
        {"metric": "per", "operator": ">=", "value": 5},
        {"metric": "per", "operator": "<=", "value": 10},
    ]})[0]
    assert not qa.filt("per", ">", 0)({"fundamental_filters": [
        {"metric": "per", "operator": ">", "value": None},
    ]})[0]


@pytest.mark.parametrize("slot,field,value", [
    ("entry", "fundamental_filters", [{"metric": "per", "value": 10}]),
    ("exit", "hold_period_days", 21),
    ("max_positions", "max_positions", 3),
    ("stop_loss", "stop_loss_pct", 6),
    ("initial_capital", "initial_capital", 10000000),
])
def test_conflicting_fill_fixture_is_not_executed(slot, field, value):
    qa = load_qa()
    qa.PREV = {field: value}
    qa.PREV_EXPLICIT = []
    qa.CASES = [(slot, "synthetic answer", lambda p: (True, ""))]
    qa.call = lambda *a, **k: pytest.fail("Invalid fixture reached the model")
    assert qa.run("fill")[0][2] == "HARNESS_INVALID"


def test_wrong_question_and_topic_are_invalid():
    qa = load_qa()
    assert qa.fixture_error("fill", "entry", {}, "obsolete question")
    assert qa.fixture_error("fill", "entry", {}, qa.QUESTIONS["entry"]["fill"],
                            {"topic": "매도 조건"})
    assert not qa.fixture_error("fill", "entry", {}, qa.QUESTIONS["entry"]["fill"])


def test_infrastructure_error_is_not_a_product_failure():
    qa = load_qa()
    qa.PREV = {}
    qa.PREV_EXPLICIT = []
    qa.CASES = [("entry", "synthetic answer", lambda p: (True, ""))]
    def unavailable(*a, **k):
        raise TimeoutError("unavailable")
    qa.call = unavailable
    assert qa.run("modify")[0][2] == "INFRA_BLOCKED"


def test_unreviewed_notice_cannot_count_as_pass():
    qa = load_qa()
    qa.PREV = {"max_positions": 3}
    qa.PREV_EXPLICIT = []
    qa.CASES = [("max_positions", "8종목", qa.field("max_positions", 8))]
    qa.call = lambda *a, **k: {"parsed": {"max_positions": 8}, "notices": [
        "요청을 반영하지 못했어요. 기존 전략을 그대로 유지했어요."]}
    assert qa.run("modify")[0][2] == "NOT_RUN"


def test_interrupted_run_cannot_reuse_a_completed_result(tmp_path):
    import json
    qa = load_qa()
    qa.PREV = {}
    qa.CASES = [("entry", "synthetic answer", lambda p: (True, ""))]
    def interrupted(*a, **k):
        raise KeyboardInterrupt()
    qa.call = interrupted
    journal = tmp_path / "run.json"
    journal.write_text('{"completed":true,"rows":["old pass"]}')
    with pytest.raises(KeyboardInterrupt):
        qa.run("modify", journal)
    saved = json.loads(journal.read_text())
    assert saved["completed"] is False and saved["rows"] == []


@pytest.mark.parametrize("cache,model", [(True, "120b"), (False, None)])
def test_cached_or_unknown_model_does_not_count_as_live_pass(cache, model):
    qa = load_qa()
    qa.PREV = {}
    qa.CASES = [("entry", "synthetic answer", lambda p: (True, ""))]
    qa.GUARDED = {}
    qa.call = lambda *a, **k: {"parsed": {}, "runtime": {
        "cache_hit": cache, "interpreter": {"model_name": model}}}
    assert qa.run("modify")[0][2] == "NOT_RUN"
