"""Complete local evidence must not change observed execution or retention."""
import hashlib
import json

import pytest

from observability import tracing


def records(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_TRACE_LOCAL", "1")
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    return lambda: json.loads(next(tmp_path.glob("*.jsonl")).read_text().splitlines()[-1])


def test_long_prompts_outputs_and_arrays_are_reconstructible(monkeypatch, tmp_path):
    read = records(monkeypatch, tmp_path)
    inputs = {"system_prompt": "s" * 9000, "user_prompt": "u" * 5000,
              "draft": {"conditions": list(range(120))}}
    with tracing.span("LLM", "llm", inputs=inputs) as trace:
        trace.output(response="r" * 8000)
        trace.meta(model="served-model")
    span = read()["span"]
    snapshot = span["metadata"]["replay_inputs"]
    assert snapshot["complete"] and snapshot["values"] == inputs
    assert snapshot["sha256"] == hashlib.sha256(
        json.dumps(inputs, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert span["metadata"]["replay_outputs"]["values"]["response"] == "r" * 8000
    assert span["metadata"]["replay_completed"] is True
    assert span["inputs"]["system_prompt"].endswith("…(생략)")


def test_credentials_are_not_saved_and_recording_is_marked_incomplete(monkeypatch, tmp_path):
    read = records(monkeypatch, tmp_path)
    with tracing.span("x", inputs={"api_key": "secret-value", "draft": {"password": "hidden"}}):
        pass
    text = json.dumps(read())
    assert "secret-value" not in text and "hidden" not in text
    assert not read()["span"]["metadata"]["replay_inputs"]["complete"]


def test_failed_execution_is_not_a_completed_recording(monkeypatch, tmp_path):
    read = records(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        with tracing.span("x"):
            raise ValueError("failure")
    assert read()["span"]["metadata"]["replay_completed"] is False


def test_output_metadata_credentials_and_unknown_objects_are_incomplete(monkeypatch, tmp_path):
    read = records(monkeypatch, tmp_path)
    with tracing.span("x", metadata={"authorization": "sensitive-header"}) as trace:
        trace.output(access_token="sensitive-output")
        trace.local_evidence(unknown=object())
    serialized = json.dumps(read())
    assert "sensitive-header" not in serialized and "sensitive-output" not in serialized
    metadata = read()["span"]["metadata"]
    assert not metadata["replay_initial_metadata"]["complete"]
    assert not metadata["replay_outputs"]["complete"]
    assert not metadata["replay_evidence"]["complete"]
