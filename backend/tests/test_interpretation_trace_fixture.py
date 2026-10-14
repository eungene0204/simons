"""Capture-to-replay bridge uses full evidence, never guesses missing recordings."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from observability import tracing
from observability.agent_trace import observed_call
from observability.agent_trace import record_api_world
from interpretation_replay import replay
from interpretation_trace_fixture import from_trace
from test_replay_trace_capture import records

CASES = json.loads((Path(__file__).parent / "fixtures/interpretation_replay.json").read_text())["cases"]


def captured(monkeypatch, tmp_path):
    import main
    case = deepcopy(CASES[2])
    final = replay(case)["final"]
    read = records(monkeypatch, tmp_path)
    for key, value in case["configuration"].items():
        monkeypatch.setenv(key, value)
    def execute(*args, **kwargs):
        with tracing.span("Interpreter", "chain") as trace:
            trace.local_evidence(interpreter_result={"intent": json.loads(case["initial_output"]),
                                                     "unreflected_numbers": None})
            with tracing.span("LLM", "llm") as llm:
                llm.local_evidence(requested_model="synthetic-requested", response_model="synthetic-served",
                    response_provider="synthetic", chat_arguments={
                        "system": "complete system" * 500, "user": case["user_input"]})
                llm.output(response=case["initial_output"])
        for call in case["recorded_calls"]:
            with tracing.span("Recorded dependency", "chain") as trace:
                if call["target"] == "auxiliary_llm":
                    with tracing.span("Auxiliary LLM", "llm") as llm:
                        llm.local_evidence(requested_model="synthetic-aux", response_model="synthetic-aux-served",
                                           chat_arguments=call["inputs"])
                        llm.output(response=call["output"])
                else:
                    trace.local_evidence(recorded_call={**call, "input_complete": True})
        return final
    monkeypatch.setattr(main, "_run_nl_parse_traced", execute)
    request = main.NLParseRequest(prompt=case["user_input"])
    assert main._run_nl_parse(request) == final
    annotation = {k: case[k] for k in ("case_id", "mode", "operation", "expected")}
    return read(), annotation


def test_complete_api_capture_roundtrips_with_full_prompts_and_models(monkeypatch, tmp_path):
    record, annotation = captured(monkeypatch, tmp_path)
    case = from_trace(record, annotation)
    assert len(case["request"][0]["content"]) > 4000
    assert case["measurement"]["response_model"] == "synthetic-served"
    assert case["measurement"]["models"][1]["response_model"] == "synthetic-aux-served"
    assert case["measurement"]["origin"] == "captured"
    assert replay(case)["status"] == "PASS"


@pytest.mark.parametrize("fault", ["old", "hash", "unfinished", "model", "gold", "cache"])
def test_incomplete_capture_is_rejected(monkeypatch, tmp_path, fault):
    record, annotation = captured(monkeypatch, tmp_path)
    root = record["span"]
    if fault == "old":
        del root["metadata"]["replay_evidence"]
    elif fault == "hash":
        root["metadata"]["replay_evidence"]["sha256"] = "wrong"
    elif fault == "unfinished":
        root["metadata"]["replay_completed"] = False
    elif fault == "model":
        llm = root["children"][0]["children"][0]
        llm["metadata"]["replay_evidence"]["values"]["response_model"] = None
    elif fault == "gold":
        del annotation["expected"]
    else:
        snapshot = root["metadata"]["replay_evidence"]
        snapshot["values"]["api_response"]["runtime"]["cache_hit"] = True
        snapshot.update(tracing.replay_snapshot(snapshot["values"]))
    with pytest.raises((ValueError, KeyError)):
        from_trace(record, annotation)


def test_observation_preserves_identity_and_exception(monkeypatch, tmp_path):
    records(monkeypatch, tmp_path)
    output = {"value": 1}
    assert observed_call("synthetic", lambda: output) is output
    def fails():
        raise RuntimeError("original error")
    with pytest.raises(RuntimeError, match="original error"):
        observed_call("synthetic", fails)


def test_bookkeeping_failure_does_not_replace_dependency_result(monkeypatch, tmp_path):
    records(monkeypatch, tmp_path)
    monkeypatch.setattr(tracing, "replay_snapshot", lambda *a: {"values": None, "complete": False})
    output = object()
    assert observed_call("synthetic", lambda: output) is output


def test_missing_api_observation_fields_never_change_execution(monkeypatch, tmp_path):
    records(monkeypatch, tmp_path)
    assert record_api_world(object(), {}) is None
