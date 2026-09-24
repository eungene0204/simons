import concurrent.futures
import threading
import time

import pytest

import cancellation
import ui_language
from nl_cache import nl_cache_key
from strategy_conversation.runtime.singleflight import SingleFlight


def test_identical_requests_share_work_and_isolate_cancellation_and_results():
    flight = SingleFlight()
    entered, release = threading.Event(), threading.Event()
    token = cancellation.CancelToken()
    calls = []

    def compute(stage):
        calls.append(ui_language.get_ui_language())
        stage("thinking")
        entered.set()
        assert release.wait(3)
        cancellation.raise_if_cancelled()
        return {"conditions": [1]}

    def run(cancel=None):
        with cancellation.bind(cancel or cancellation.CancelToken()), ui_language.bind("en"):
            return flight.run("same", compute)

    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        first = pool.submit(run, token)
        assert entered.wait(3)
        second, third = pool.submit(run), pool.submit(run)
        deadline = time.monotonic() + 3
        while flight._flights["same"].subscribers != 3 and time.monotonic() < deadline:
            time.sleep(.005)
        assert flight._flights["same"].subscribers == 3
        token.cancel()
        with pytest.raises(cancellation.OperationCancelled):
            first.result(timeout=3)
        release.set()
        a, b = second.result(timeout=3), third.result(timeout=3)
    a["conditions"].append(2)
    assert b == {"conditions": [1]}
    assert calls == ["en"]
    assert flight._flights == {}


def test_last_cancellation_stops_shared_work_and_new_request_can_retry():
    flight = SingleFlight()
    entered, stopped = threading.Event(), threading.Event()
    token = cancellation.CancelToken()

    def compute(stage):
        entered.set()
        try:
            while True:
                cancellation.raise_if_cancelled()
                time.sleep(.005)
        finally:
            stopped.set()

    def run():
        with cancellation.bind(token):
            flight.run("same", compute)

    with concurrent.futures.ThreadPoolExecutor() as pool:
        pending = pool.submit(run)
        assert entered.wait(3)
        token.cancel()
        with pytest.raises(cancellation.OperationCancelled):
            pending.result(timeout=3)
        assert stopped.wait(3)
    assert flight.run("same", lambda stage: 42) == 42
    with pytest.raises(ValueError):
        flight.run("error", lambda stage: (_ for _ in ()).throw(ValueError()))
    assert flight.run("error", lambda stage: 1) == 1


def test_cache_identity_includes_all_request_state_and_runtime(monkeypatch):
    def key(context):
        return nl_cache_key("same", "ollama", None, {}, request_context=context)
    base = key({})
    for field in ("previous_explicit_fields", "previous_declined_fields", "previous_artifacts",
                  "previous_field_states", "previous_field_metadata", "previous_coach_text"):
        assert key({field: "different"}) != base
    monkeypatch.setenv("OPENROUTER_MODEL", "another-model")
    assert key({}) != base


def test_primary_entrypoint_shares_requests_but_not_different_provenance(monkeypatch):
    import main
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "primary")
    entered, release = threading.Event(), threading.Event()
    calls = []
    flights = SingleFlight()
    monkeypatch.setattr(main, "_nl_parse_flights", flights)
    def parse(request, stage=None, defer_holder=None):
        calls.append(request.previous_declined_fields)
        entered.set()
        assert release.wait(3)
        return {"parsed": {"declined": request.previous_declined_fields}}
    monkeypatch.setattr(main, "_run_nl_parse_impl", parse)
    request = main.NLParseRequest(prompt="same")
    with concurrent.futures.ThreadPoolExecutor(3) as pool:
        a = pool.submit(main._run_nl_parse_traced, request)
        assert entered.wait(3)
        b = pool.submit(main._run_nl_parse_traced, request)
        c = pool.submit(main._run_nl_parse_traced, main.NLParseRequest(
            prompt="same", previous_declined_fields=["stop_loss"]))
        deadline = time.monotonic() + 3
        while sum(f.subscribers for f in list(flights._flights.values())) < 3 and time.monotonic() < deadline:
            time.sleep(.005)
        assert sum(f.subscribers for f in flights._flights.values()) == 3
        release.set()
        assert a.result(timeout=3) == b.result(timeout=3)
        assert c.result(timeout=3)["parsed"]["declined"] == ["stop_loss"]
    assert len(calls) == 2
