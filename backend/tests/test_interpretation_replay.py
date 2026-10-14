"""Replay execution and scoring must not hide known product failures."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from interpretation_replay import replay
from interpretation_replay_contract import digest, judge, summarize

CASES = json.loads((Path(__file__).parent / "fixtures/interpretation_replay.json").read_text())["cases"]


@pytest.mark.parametrize("case,status", [(c, "PASS") for c in CASES],
    ids=[c["case_id"] for c in CASES])
def test_fixed_pipeline_replay(case, status):
    original = deepcopy(case)
    first, second = replay(case), replay(case)
    assert first["status"] == second["status"] == status
    assert first["final"] == second["final"]
    assert first["new_model_calls"] == 0
    assert case == original
    assert any(s["stage"] == "compile_strategy" for s in first["stages"])
    assert any(s["stage"] == "api_postprocessing" for s in first["stages"])
    assert "backtest_request" in first["final"] and "field_states" in first["final"]


@pytest.mark.parametrize("fault", ["truncated", "hash", "unfinished", "model", "question",
                                  "draft", "topic", "operation", "notices"])
def test_invalid_fixture_never_executes_primary(monkeypatch, fault):
    case = deepcopy(next(case for case in CASES if case["case_id"] == "entry-fill"))
    if fault == "truncated":
        case["request"][0]["content"] = "preview…(생략)"
        case["request_hash"] = digest(case["request"])
    elif fault == "hash":
        case["request_hash"] = "incorrect"
    elif fault == "unfinished":
        case["measurement"]["completed"] = False
    elif fault == "model":
        del case["measurement"]["response_model"]
    elif fault == "question":
        case["question"] = "obsolete question"
    elif fault == "draft":
        case["previous_parsed"]["entry_signals"] = [{"indicator": "rsi"}]
    elif fault == "topic":
        case["pending_ask"]["topic"] = "매도 조건"
    elif fault == "operation":
        case["operation"] = "unknown"
    else:
        del case["expected"]["channels"]["notices"]
    monkeypatch.setattr("strategy_conversation.primary.run_primary_modification",
                        lambda *a, **k: pytest.fail("Invalid replay executed"))
    assert replay(case)["status"] == "HARNESS_INVALID"


@pytest.mark.parametrize("fault", ["missing", "changed", "unused"])
def test_incomplete_recordings_cannot_fail_open(fault):
    case = deepcopy(CASES[1])
    if fault == "missing":
        case["recorded_calls"] = []
    elif fault == "changed":
        case["recorded_calls"][0]["inputs"]["user"] = "different request"
    else:
        case["recorded_calls"].append(deepcopy(case["recorded_calls"][0]))
    assert replay(case)["status"] == "HARNESS_INVALID"


def test_whole_condition_list_is_compared_with_duplicates():
    expected = {"all_items": {"/parsed/entry_signals": {
        "keys": ["indicator", "operator", "value"],
        "items": [{"indicator": "rsi", "operator": "<=", "value": 30}]}}, "channels": {}}
    final = {"parsed": {"entry_signals": [
        {"indicator": "rsi", "operator": "<=", "value": 30},
        {"indicator": "rsi", "operator": "<=", "value": 30}]}}
    assert judge(expected, final) == ["/parsed/entry_signals"]


def test_model_cache_and_completion_are_separate_measurements():
    base = {"status": "PASS", "execution_mode": "replay", "measurement": {
        "response_model": "120b", "cache": False, "completed": True}}
    variants = [deepcopy(base) for _ in range(4)]
    variants[1]["measurement"]["response_model"] = "9b"
    variants[2]["measurement"]["cache"] = True
    variants[3]["measurement"]["completed"] = False
    variants[3]["status"] = "HARNESS_INVALID"
    assert len(summarize(variants)) == 4


def test_replay_blocks_unrecorded_shared_knowledge(monkeypatch):
    from strategy_conversation import primary
    def hidden_access(*a, **k):
        from engine.knowledge_graph import get_graph
        get_graph()
    monkeypatch.setattr(primary, "run_primary_parse", hidden_access)
    assert replay(CASES[0])["status"] == "HARNESS_INVALID"


def test_numeric_types_do_not_change_semantic_expectations():
    expected = {"all_items": {"/conditions": {"keys": ["value"], "items": [{"value": 10}]}},
                "channels": {}}
    assert judge(expected, {"conditions": [{"value": 10.0}]}) == []


def test_regions_and_modes_are_not_pooled():
    rows = [{"status": "PASS", "mode": mode, "region": region}
            for mode, region in (("create", "KR"), ("modify", "KR"), ("modify", "US"))]
    assert len(summarize(rows)) == 3
