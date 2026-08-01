"""Trace 계층 테스트 — Parent-Child 관계가 실제로 유지되는지 검증한다.

스펙의 계층은 Trace → Planner → (Action DAG · Tool · State · LLM) → Responder이며
"계층 구조가 항상 유지되어야 한다"가 요구사항이다. 이 파일이 그 요구사항의 회귀
테스트다 — 특히 **스레드 경계**를 검증한다. 이 코드베이스는 parse-stream이 파스를
별도 스레드에서 돌리고 planner shadow·후행 검증도 각자 스레드라, contextvar 기반
부모 추적이 그냥은 끊긴다(자식 span이 각자 고아 루트가 된다).

실제 전송 없이 검증하기 위해 langsmith.run_helpers.trace를 기록용 스텁으로 갈아끼운다 —
파사드가 부모-자식을 어떻게 엮는지는 langsmith의 contextvar 동작에 달려 있으므로
실제 RunTree를 쓰되 전송만 막는다.
"""

from __future__ import annotations

import logging
import threading

import pytest

from observability import current_parent, span, use_parent


@pytest.fixture(autouse=True)
def _tracing_on_no_egress(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    for name in ("langsmith", "langsmith.client", "langsmith._internal"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def _trace_id(run):
    """RunTree가 속한 Trace의 루트 id."""
    return getattr(run, "trace_id", None)


def test_nested_spans_share_one_trace():
    """같은 요청 안의 span은 전부 하나의 Trace에 속한다."""
    seen = {}
    with span("root", "chain", root=True) as root:
        seen["root"] = root._run
        with span("Planner", "planner") as planner:
            seen["planner"] = planner._run
            with span("Tool", "tool") as tool:
                seen["tool"] = tool._run

    assert all(run is not None for run in seen.values()), "span이 활성화되지 않았다"
    trace_ids = {name: _trace_id(run) for name, run in seen.items()}
    assert len(set(trace_ids.values())) == 1, f"Trace가 갈라졌다: {trace_ids}"


def test_child_span_points_at_its_parent():
    """Planner span의 부모는 루트, Tool span의 부모는 Planner여야 한다."""
    with span("root", "chain", root=True) as root:
        with span("Planner", "planner") as planner:
            with span("Tool", "tool") as tool:
                assert planner._run.parent_run_id == root._run.id
                assert tool._run.parent_run_id == planner._run.id


def test_hierarchy_survives_thread_boundary():
    """스레드로 넘어간 작업도 같은 Trace에 붙는다.

    이 테스트가 없으면 parse-stream·planner shadow·후행 검증의 span이 조용히
    고아 Trace가 되고, 아무도 눈치채지 못한다.
    """
    captured = {}

    def worker(parent):
        with use_parent(parent):
            with span("shadow-planner", "planner") as child:
                captured["child"] = child._run

    with span("root", "chain", root=True) as root:
        captured["root"] = root._run
        thread = threading.Thread(target=worker, args=(current_parent(),))
        thread.start()
        thread.join()

    assert captured["child"] is not None, "스레드 안에서 span이 활성화되지 않았다"
    assert _trace_id(captured["child"]) == _trace_id(captured["root"])
    assert captured["child"].parent_run_id == captured["root"].id


def test_thread_without_parent_starts_its_own_trace():
    """부모를 넘기지 않으면 고아가 된다 — use_parent가 필요한 이유의 대조군."""
    captured = {}

    def worker():
        with span("orphan", "planner") as child:
            captured["child"] = child._run

    with span("root", "chain", root=True) as root:
        captured["root"] = root._run
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

    assert _trace_id(captured["child"]) != _trace_id(captured["root"])


def test_metrics_from_child_thread_land_in_parent_trace():
    """다른 스레드에서 잰 시간·횟수도 같은 Trace의 지표에 잡힌다."""
    from observability import current_metrics

    collected = {}

    def worker(parent):
        with use_parent(parent):
            with span("Tool · x", "tool"):
                pass

    with span("root", "chain", root=True):
        thread = threading.Thread(target=worker, args=(current_parent(),))
        thread.start()
        thread.join()
        collected.update(current_metrics() or {})

    assert collected.get("tool_count") == 1, collected


def test_exception_in_child_does_not_break_parent_span():
    """자식이 터져도 부모 span은 정상 종료된다(예외는 그대로 전파)."""
    with span("root", "chain", root=True) as root:
        with pytest.raises(RuntimeError):
            with span("Tool", "tool"):
                raise RuntimeError("tool failed")
        # 부모는 살아 있고 계속 기록할 수 있다.
        root.output(recovered=True)
        assert root._run.outputs.get("recovered") is True
