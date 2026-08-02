"""파스 루트 Trace 테스트 — 사용자 요청 하나당 Trace 하나(스펙 § Trace 계층).

검증 대상은 main._run_nl_parse 래퍼다:
- 파싱 본체(_run_nl_parse_traced)의 반환값을 그대로 통과시킨다(관찰이 결과를 바꾸지 않는다).
- 추적이 꺼져 있어도 동일하게 동작한다.
- Responder span이 사용자에게 나간 내용을 담는다.
- 성능 지표가 루트 메타데이터에 붙는다.
"""

from __future__ import annotations

import logging

import pytest

import main


@pytest.fixture(autouse=True)
def _no_egress(monkeypatch):
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    # LangSmith 레인의 루트 계약만 본다 — 로컬 레인은 test_local_trace.py 소관.
    monkeypatch.setenv("AGENT_TRACE_LOCAL", "0")
    for name in ("langsmith", "langsmith.client", "langsmith._internal"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def _request(prompt="코스피 전략 만들어줘", **kwargs):
    return main.NLParseRequest(prompt=prompt, **kwargs)


_RESULT = {
    "parsed": {"universe": {"type": "KOSPI"}},
    "backtest_request": {},
    "symbol_count": 30,
    "clarification_question": "어떤 조건에서 매수할까요?",
    "clarification_suggestions": ["RSI 30 이하에서 매수"],
}


def test_result_passes_through_untouched_when_disabled(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.setattr(main, "_run_nl_parse_traced", lambda req, **kw: _RESULT)
    assert main._run_nl_parse(_request()) is _RESULT


def test_result_passes_through_untouched_when_enabled(monkeypatch):
    """추적을 켜도 반환값은 같은 객체다 — 관찰이 결과를 만지지 않는다."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setattr(main, "_run_nl_parse_traced", lambda req, **kw: _RESULT)
    assert main._run_nl_parse(_request()) is _RESULT


def test_exception_propagates_unchanged(monkeypatch):
    """파싱 예외는 삼켜지지 않는다 — 503 경로 판정이 호출부 소관이기 때문."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    def _boom(req, **kw):
        raise main.HTTPException(status_code=503, detail="LLM down")

    monkeypatch.setattr(main, "_run_nl_parse_traced", _boom)
    with pytest.raises(main.HTTPException) as exc:
        main._run_nl_parse(_request())
    assert exc.value.status_code == 503


def test_root_trace_records_responder_and_metrics(monkeypatch):
    """루트 Trace에 응답 내용과 성능 지표가 남는다."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    captured = {}

    def _inner(req, **kw):
        from observability import current_parent

        captured["parent"] = current_parent()
        return _RESULT

    monkeypatch.setattr(main, "_run_nl_parse_traced", _inner)
    main._run_nl_parse(_request())

    run = captured["parent"][0]
    assert run.name == "NullStock Strategy Agent"
    # 성능 지표(스펙 § Performance Metrics)
    assert "total_duration_ms" in run.metadata
    assert run.metadata["action_count"] == 0
    # 식별자 — user_id는 지어내지 않는다
    assert run.metadata["user_id"] is None
    assert run.metadata["turn_kind"] == "create"


def test_responder_span_carries_delivered_response(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    captured = {}

    def _inner(req, **kw):
        from observability import current_parent

        captured["parent"] = current_parent()
        return _RESULT

    monkeypatch.setattr(main, "_run_nl_parse_traced", _inner)
    main._run_nl_parse(_request())

    root = captured["parent"][0]
    responder = next((c for c in (root.child_runs or []) if c.name == "Responder"), None)
    assert responder is not None, "Responder span이 없다 — Trace 계층의 마지막 자리가 빈다"
    assert responder.outputs["clarification_question"] == "어떤 조건에서 매수할까요?"
    assert responder.outputs["outcome"] == "ask"


def test_modify_turn_links_to_previous_strategy(monkeypatch):
    """수정 턴의 session_id는 직전 전략의 해시 — 대화를 잇는 유일한 근거다."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    from observability.identity import content_hash

    previous = {"universe": {"type": "KOSPI"}}
    captured = {}

    def _inner(req, **kw):
        from observability import current_parent

        captured["parent"] = current_parent()
        return _RESULT

    monkeypatch.setattr(main, "_run_nl_parse_traced", _inner)
    main._run_nl_parse(_request("RSI 조건 추가해줘", previous_parsed=previous))

    metadata = captured["parent"][0].metadata
    assert metadata["turn_kind"] == "modify"
    assert metadata["session_id"] == content_hash(previous)
