"""로컬 Agent Trace 레코더 계약 테스트 — LangSmith 없이 같은 정보가 남는가.

여기서 지키는 것:
- LangSmith가 꺼져 있어도 로컬 레인만으로 span 계층·입출력·오류·지표가 기록된다.
- Trace 하나가 JSONL 한 줄로 남고, 콘솔에는 key = value 컬럼 트리로 찍힌다.
- AGENT_TRACE_LOCAL=0이면 완전한 no-op(파일·출력 없음, 반환값·예외 불변).
- 스레드 경계(current_parent/use_parent)에서 루트 방출 후 도착한 span은
  같은 trace_id의 late_attach 레코드로 남는다(방출된 트리를 소급 수정하지 않는다).
"""

from __future__ import annotations

import json
import threading

import pytest

from observability import current_parent, span, use_parent
from observability import local_trace


@pytest.fixture(autouse=True)
def _local_on(monkeypatch, tmp_path):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.setenv("AGENT_TRACE_LOCAL", "1")
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))
    yield tmp_path


def _records(tmp_path):
    lines = []
    for path in sorted(tmp_path.glob("*.jsonl")):
        lines += [json.loads(line) for line in path.read_text().splitlines() if line]
    return lines


# ── 기록 내용 ─────────────────────────────────────────────────────────────────

def test_span_tree_written_as_single_jsonl_record(_local_on):
    with span("NullStock Strategy Agent", "chain", root=True,
              inputs={"user_input": "RSI 30 이하 매수"}) as trace:
        with span("Interpreter · 전략 해석", "llm") as inner:
            inner.output(intent="CREATE")
        trace.output(outcome="answer")

    records = _records(_local_on)
    assert len(records) == 1
    record = records[0]
    assert record["root"] == "NullStock Strategy Agent"
    assert record["total_ms"] >= 0
    root = record["span"]
    assert root["inputs"]["user_input"] == "RSI 30 이하 매수"
    assert root["outputs"]["outcome"] == "answer"
    children = root["children"]
    assert [c["name"] for c in children] == ["Interpreter · 전략 해석"]
    assert children[0]["outputs"]["intent"] == "CREATE"
    assert children[0]["duration_ms"] is not None


def test_root_metadata_collects_metrics_without_langsmith(_local_on):
    with span("root", "chain", root=True):
        with span("LLM 호출", "llm"):
            pass
        with span("Tool · classify_universe", "tool"):
            pass
    record = _records(_local_on)[0]
    meta = record["span"]["metadata"]
    assert meta["llm_calls"] == 1
    assert meta["tool_count"] == 1
    assert meta["llm_ms"] >= 0
    assert meta["total_duration_ms"] == record["total_ms"]
    # 루트 공통 메타데이터(LangSmith와 동일한 정보 평가 축)도 실린다.
    assert meta["agent"] == "Strategy Planner"


def test_exception_recorded_and_reraised(_local_on):
    with pytest.raises(ValueError, match="boom"):
        with span("root", "chain", root=True):
            with span("Tool · compile", "tool"):
                raise ValueError("boom")
    record = _records(_local_on)[0]
    child = record["span"]["children"][0]
    assert "ValueError" in child["error"]
    assert child["metadata"]["error_kind"] == "ValueError"


def test_handle_error_records_nonexception_failure(_local_on):
    with span("root", "chain", root=True) as trace:
        trace.error("PlannerBudget", "예산 소진")
    record = _records(_local_on)[0]
    assert record["span"]["error"] == "[PlannerBudget] 예산 소진"
    assert record["span"]["metadata"]["failure_count"] == 1


def test_console_renders_tree_with_key_value_columns(_local_on, capsys):
    with span("root", "chain", root=True, inputs={"user_input": "코스피 전략"}) as trace:
        with span("Planner · Action DAG", "planner"):
            pass
        trace.output(outcome="ask")
    out = capsys.readouterr().out
    assert "[AGENT-TRACE] trace=" in out
    assert "Planner · Action DAG" in out
    # raw JSON 한 줄 덤프 금지 — key = value 컬럼(_flatten_json_columns 선례).
    assert 'in.user_input' in out
    assert '= "코스피 전략"' in out
    assert '{"user_input"' not in out


# ── 비활성 = 완전한 no-op ─────────────────────────────────────────────────────

def test_disabled_local_lane_is_noop(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("AGENT_TRACE_LOCAL", "0")
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))
    with span("root", "chain", root=True) as trace:
        assert trace.active is False
        trace.output(x=1)
    assert _records(tmp_path) == []
    assert "[AGENT-TRACE]" not in capsys.readouterr().out


def test_disabled_span_reraises(monkeypatch):
    monkeypatch.setenv("AGENT_TRACE_LOCAL", "0")
    with pytest.raises(KeyError):
        with span("root", "chain"):
            raise KeyError("x")


# ── 스레드 경계 ───────────────────────────────────────────────────────────────

def test_late_attach_after_root_emitted(_local_on):
    """SSE 후행 검증 시나리오 — 루트 방출 뒤 다른 스레드에서 같은 Trace에 붙는다."""
    holder = {}
    with span("root", "chain", root=True):
        holder["parent"] = current_parent()

    def _deferred():
        with use_parent(holder["parent"]):
            with span("Validation · 후행 파스 검증", "state") as trace:
                trace.output(corrected=False)

    worker = threading.Thread(target=_deferred)
    worker.start()
    worker.join()

    records = _records(_local_on)
    assert len(records) == 2
    root_rec, late_rec = records
    assert late_rec["late_attach"] is True
    assert late_rec["trace_id"] == root_rec["trace_id"]
    assert late_rec["span"]["name"] == "Validation · 후행 파스 검증"
    assert late_rec["span"]["outputs"]["corrected"] is False


def test_same_thread_child_attaches_before_emit(_local_on):
    """루트가 아직 열려 있는 동안 넘긴 부모는 일반 자식으로 붙는다."""
    with span("root", "chain", root=True):
        parent = current_parent()
        result = {}

        def _worker():
            with use_parent(parent):
                with span("Planner Shadow", "planner"):
                    result["ran"] = True

        worker = threading.Thread(target=_worker)
        worker.start()
        worker.join()
        assert result == {"ran": True}

    records = _records(_local_on)
    assert len(records) == 1
    assert [c["name"] for c in records[0]["span"]["children"]] == ["Planner Shadow"]


# ── 렌더링 단위 ───────────────────────────────────────────────────────────────

def test_console_row_overflow_is_capped(_local_on, capsys):
    with span("root", "chain", root=True) as trace:
        trace.output(big={f"k{i}": i for i in range(100)})
    out = capsys.readouterr().out
    assert "전문은 JSONL" in out
