"""관찰 계층 계약 테스트 — 관찰이 실행을 바꾸지 않는다는 것이 검증 대상이다.

여기서 지키는 것:
- 기본값은 비활성이고, 비활성 span은 반환값·예외를 그대로 통과시킨다.
- 활성이어도 langsmith가 실패하면 실행은 계속된다.
- 예외는 기록만 되고 그대로 전파된다(폴백 판정은 호출부 소관).
- Trace 식별자는 없는 값을 지어내지 않는다.
"""

from __future__ import annotations

import logging

import pytest

from observability import metrics as obs_metrics
from observability import tracing
from observability.agent_trace import (
    dag_ascii,
    dag_snapshot,
    ollama_usage,
    responder_payload,
    state_diff,
)
from observability.identity import content_hash, trace_identity


@pytest.fixture(autouse=True)
def _no_egress(monkeypatch):
    """테스트가 LangSmith로 나가지 못하게 막는다.

    추적을 켜는 테스트가 있으므로 필요하다 — 실제로 api.smith.langchain.com으로
    POST가 나가는 것을 확인했다. 관찰 계층 테스트가 외부에 데이터를 보내면 안 된다.
    엔드포인트를 막아도 span 계약(반환값·예외 전파)은 그대로 검증된다.
    """
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    # langsmith의 백그라운드 전송 스레드가 연결 실패를 stderr로 쏟는다 — 테스트 출력이
    # 아니라 SDK 내부 잡음이다(전송 실패해도 실행은 계속된다는 것이 바로 이 계약).
    for name in ("langsmith", "langsmith.client", "langsmith._internal"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


# ── 비활성이 기본값 ───────────────────────────────────────────────────────────

def test_tracing_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    assert tracing.tracing_enabled() is False


@pytest.mark.parametrize("value,expected", [
    ("true", True), ("1", True), ("on", True), ("TRUE", True),
    ("false", False), ("", False), ("no", False),
])
def test_tracing_flag_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("LANGSMITH_TRACING", value)
    assert tracing.tracing_enabled() is expected


def test_disabled_span_is_noop_and_passes_value_through(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    with tracing.span("x", "tool", inputs={"a": 1}) as trace:
        assert trace.active is False
        # 손잡이 메서드는 비활성에서도 호출 가능해야 한다(호출부에 분기를 만들지 않는다).
        trace.output(result=1)
        trace.meta(k="v")
        trace.error("Kind", "msg")


def test_disabled_span_reraises_exception(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    with pytest.raises(ValueError, match="boom"):
        with tracing.span("x", "tool"):
            raise ValueError("boom")


# ── 활성 상태에서도 실행을 깨뜨리지 않는다 ────────────────────────────────────

def test_enabled_span_survives_langsmith_failure(monkeypatch):
    """langsmith가 터져도 감싼 코드는 정상 실행되고 값이 그대로 나온다."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    def _explode(*args, **kwargs):
        raise RuntimeError("langsmith down")

    monkeypatch.setattr("langsmith.run_helpers.trace", _explode)
    executed = {}
    with tracing.span("x", "tool") as trace:
        executed["ran"] = True
        assert trace.active is False
    assert executed == {"ran": True}


def test_enabled_span_reraises_exception(monkeypatch):
    """예외는 기록만 하고 그대로 던진다 — 삼키면 폴백 판정이 뒤집힌다."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    with pytest.raises(KeyError):
        with tracing.span("x", "tool"):
            raise KeyError("nope")


def test_use_parent_with_none_is_noop(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    with tracing.use_parent(None):
        pass
    assert tracing.current_parent() is None


# ── 성능 지표 ─────────────────────────────────────────────────────────────────

def test_metrics_accumulate_within_root(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    # 비활성이면 누적기도 걸리지 않는다(오버헤드 0).
    with tracing.span("root", "chain", root=True):
        assert obs_metrics.current_metrics() is None


def test_metrics_counters_ignore_unknown_keys():
    token = obs_metrics.bind(obs_metrics.new_metrics())
    try:
        obs_metrics.bump("tool_count")
        obs_metrics.bump("nonexistent_key")
        obs_metrics.record_duration("llm_ms", 12.5)
        obs_metrics.record_duration("bogus_bucket", 99.0)
        current = obs_metrics.current_metrics()
        assert current["tool_count"] == 1
        assert current["llm_ms"] == 12.5
        assert "nonexistent_key" not in current
        assert "bogus_bucket" not in current
    finally:
        obs_metrics.unbind(token)


def test_metrics_outside_trace_is_silent():
    """추적 밖 호출은 아무 일도 하지 않는다(예외 없음)."""
    obs_metrics.bump("tool_count")
    obs_metrics.record_duration("llm_ms", 1.0)
    assert obs_metrics.current_metrics() is None


# ── Agent 구조 어댑터 ─────────────────────────────────────────────────────────

class _Node:
    def __init__(self, **kwargs):
        self.__dict__.update({
            "id": "n", "type": "tool", "tool": None, "args": {}, "topic": None,
            "question": None, "chips": [], "depends_on": [], "requires": [],
            "produces": [], "invalidated_by": [],
        })
        self.__dict__.update(kwargs)


def test_dag_snapshot_captures_structure_and_edges():
    nodes = [
        _Node(id="a", type="tool", tool="classify_universe", args={"text": "보안주"},
              produces=["universe.type"]),
        _Node(id="b", type="ask", topic="매수조건", question="어떤 조건에서 매수할까요?",
              chips=["RSI 30 이하"], depends_on=["a"]),
    ]
    snapshot = dag_snapshot(nodes)
    assert snapshot["node_count"] == 2
    assert snapshot["edges"] == ["a → b"]
    assert snapshot["nodes"][0]["tool"] == "classify_universe"
    assert snapshot["nodes"][0]["produces"] == ["universe.type"]
    assert snapshot["nodes"][1]["question"] == "어떤 조건에서 매수할까요?"


def test_dag_snapshot_merges_statuses():
    nodes = [_Node(id="a"), _Node(id="b", depends_on=["a"])]
    snapshot = dag_snapshot(nodes, statuses={"a": "COMPLETED", "b": "PENDING"})
    assert [n["status"] for n in snapshot["nodes"]] == ["COMPLETED", "PENDING"]


def test_dag_snapshot_handles_empty():
    assert dag_snapshot(None)["node_count"] == 0
    assert dag_ascii(None) == "(빈 DAG)"


def test_dag_ascii_renders_dependency_chain():
    nodes = [
        _Node(id="a", tool="classify_universe"),
        _Node(id="b", type="ask", topic="매수조건", depends_on=["a"]),
    ]
    rendered = dag_ascii(nodes)
    assert "classify_universe" in rendered
    assert "↓ Ask(매수조건)" in rendered


def test_state_diff_reports_changed_paths():
    before = {"universe": {"type": "KOSPI", "symbols": []}, "sell": None}
    after = {"universe": {"type": "KOSPI", "symbols": []}, "sell": "MA20 Break"}
    diff = state_diff(before, after)
    assert diff["changed_fields"] == ["sell"]
    assert diff["diff"]["sell"] == {"before": None, "after": "MA20 Break"}


def test_state_diff_on_none_is_empty():
    assert state_diff(None, None)["changed_count"] == 0


def test_responder_payload_marks_ask_vs_answer():
    ask = responder_payload({"clarification_question": "어떤 조건에서 매수할까요?"})
    assert ask["outcome"] == "ask"
    answer = responder_payload({"symbol_count": 30})
    assert answer["outcome"] == "answer"
    assert responder_payload(None) == {"delivered": None}


def test_ollama_usage_reads_token_counts():
    usage = ollama_usage({"prompt_eval_count": 120, "eval_count": 40,
                          "total_duration": 5_000_000})
    assert usage["input_tokens"] == 120
    assert usage["output_tokens"] == 40
    assert usage["total_tokens"] == 160
    assert usage["ollama_total_ns"] == 5_000_000
    # self-hosted라 단가가 없다 — 비용을 지어내지 않는다.
    assert "cost" not in usage


def test_ollama_usage_tolerates_missing_fields():
    assert ollama_usage({}) == {}
    assert ollama_usage(None) == {}


# ── Trace 식별자 ──────────────────────────────────────────────────────────────

def test_identity_does_not_invent_user_id():
    identity = trace_identity("코스피 전략", None)
    assert identity["user_id"] is None
    assert identity["turn_kind"] == "create"


def test_identity_chains_turns_via_parent_strategy():
    """턴 N의 session_id는 턴 N-1의 strategy_id와 같아야 대화를 이을 수 있다."""
    previous = {"universe": {"type": "KOSPI"}}
    identity = trace_identity("RSI 추가", previous)
    assert identity["turn_kind"] == "modify"
    assert identity["session_id"] == content_hash(previous)
    assert identity["parent_strategy_id"] == content_hash(previous)


def test_content_hash_is_order_independent_and_stable():
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})
    assert content_hash(None) is None
    assert content_hash({}) is None
