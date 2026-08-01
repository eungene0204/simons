"""결정론 Evaluator 테스트.

핵심 계약 둘:
- 판정 근거가 없으면 score=None(집계 제외)이다. 근거 없이 0점을 주면 안 된다.
- **되묻기는 실패가 아니다** — 값 없는 팩터를 묻는 것은 Agent의 정상 동작이다
  (CLAUDE.md 전략 예시 QA 판정 기준과 같은 원칙).
"""

from __future__ import annotations

from observability.dataset import EXAMPLES, as_langsmith_examples
from observability.evaluators import (
    dag_well_formed,
    evaluate_trace,
    no_wasted_actions,
    response_contract_kept,
    state_change_declared,
    summarize,
    tool_selection_valid,
    turn_made_progress,
)


def _dag(nodes):
    return {"nodes": nodes, "edges": [], "node_count": len(nodes)}


_VALID_FINISH_CHAIN = [
    {"id": "v", "type": "tool", "tool": "validate_intent", "depends_on": []},
    {"id": "c", "type": "tool", "tool": "compile_strategy", "depends_on": ["v"]},
    {"id": "f", "type": "finish", "depends_on": ["c"]},
]


# ── 1. DAG 구조 ───────────────────────────────────────────────────────────────

def test_dag_well_formed_passes_valid_finish_chain():
    assert dag_well_formed(_dag(_VALID_FINISH_CHAIN))["score"] == 1.0


def test_dag_well_formed_skips_when_no_dag():
    """planner 폴백 턴은 채점 대상이 아니다 — DAG가 없는 것이지 나쁜 것이 아니다."""
    assert dag_well_formed(None)["score"] is None
    assert dag_well_formed(_dag([]))["score"] is None


def test_dag_well_formed_detects_missing_compile_dependency():
    result = dag_well_formed(_dag([{"id": "f", "type": "finish", "depends_on": []}]))
    assert result["score"] == 0.0
    assert "compile_strategy" in result["comment"]


def test_dag_well_formed_detects_missing_validate_dependency():
    result = dag_well_formed(_dag([
        {"id": "c", "type": "tool", "tool": "compile_strategy", "depends_on": []},
        {"id": "f", "type": "finish", "depends_on": ["c"]},
    ]))
    assert result["score"] == 0.0
    assert "validate_intent" in result["comment"]


def test_dag_well_formed_detects_cycle():
    result = dag_well_formed(_dag([
        {"id": "a", "type": "tool", "tool": "x", "depends_on": ["b"]},
        {"id": "b", "type": "tool", "tool": "y", "depends_on": ["a"]},
    ]))
    assert result["score"] == 0.0
    assert "순환" in result["comment"]


def test_dag_well_formed_detects_dangling_dependency():
    result = dag_well_formed(_dag([
        {"id": "a", "type": "ask", "depends_on": ["ghost"]},
    ]))
    assert result["score"] == 0.0
    assert "ghost" in result["comment"]


def test_dag_well_formed_detects_duplicate_ids():
    result = dag_well_formed(_dag([
        {"id": "a", "type": "ask", "depends_on": []},
        {"id": "a", "type": "ask", "depends_on": []},
    ]))
    assert result["score"] == 0.0
    assert "중복" in result["comment"]


# ── 2. 불필요한 Action ────────────────────────────────────────────────────────

def test_no_wasted_actions_counts_blocked_and_invalidated():
    dag = _dag([{"id": n, "type": "ask", "depends_on": []} for n in "abcd"])
    result = no_wasted_actions(dag, {"a": "COMPLETED", "b": "BLOCKED",
                                     "c": "INVALIDATED", "d": "READY"})
    assert result["score"] == 0.5


def test_no_wasted_actions_does_not_penalize_skipped():
    """SKIPPED는 낭비가 아니다 — 채워진 슬롯 재질문 가드가 동작한 결과다."""
    dag = _dag([{"id": n, "type": "ask", "depends_on": []} for n in "ab"])
    result = no_wasted_actions(dag, {"a": "COMPLETED", "b": "SKIPPED"})
    assert result["score"] == 1.0


def test_no_wasted_actions_skips_without_statuses():
    assert no_wasted_actions(None, None)["score"] is None


# ── 3. State 변경 ─────────────────────────────────────────────────────────────

def test_state_change_declared_accepts_declared_fields():
    dag = _dag([{"id": "a", "type": "tool", "tool": "classify_universe",
                 "depends_on": [], "produces": ["universe.type"]}])
    assert state_change_declared(dag, ["universe.type"])["score"] == 1.0


def test_state_change_declared_accepts_nested_path_under_declared_prefix():
    dag = _dag([{"id": "a", "type": "tool", "tool": "resolve_universe",
                 "depends_on": [], "produces": ["universe.symbols"]}])
    assert state_change_declared(dag, ["universe.symbols.0"])["score"] == 1.0


def test_state_change_declared_flags_undeclared_change():
    dag = _dag([{"id": "a", "type": "tool", "tool": "classify_universe",
                 "depends_on": [], "produces": ["universe.type"]}])
    result = state_change_declared(dag, ["universe.type", "conditions.buy"])
    assert result["score"] == 0.5
    assert "conditions.buy" in result["comment"]


def test_state_change_declared_no_change_is_full_score():
    dag = _dag([{"id": "a", "type": "ask", "depends_on": []}])
    assert state_change_declared(dag, [])["score"] == 1.0


# ── 4. Tool 선택 ──────────────────────────────────────────────────────────────

def test_tool_selection_valid_flags_forbidden_tool():
    result = tool_selection_valid(["classify_universe", "kg_theme_companies"],
                                  forbidden=["kg_theme_companies"])
    assert result["score"] == 0.0
    assert "kg_theme_companies" in result["comment"]


def test_tool_selection_valid_flags_duplicate_calls():
    """같은 도구를 두 번 부르면 관찰 재사용(call_cache)이 안 된 것이다."""
    result = tool_selection_valid(["classify_universe", "classify_universe"])
    assert result["score"] == 0.0
    assert "중복" in result["comment"]


def test_tool_selection_valid_passes_clean_run():
    assert tool_selection_valid(["classify_universe", "resolve_universe"])["score"] == 1.0


def test_tool_selection_skips_without_record():
    assert tool_selection_valid(None)["score"] is None


# ── 5. 응답 계약 ──────────────────────────────────────────────────────────────

def test_response_contract_flags_financial_terms_for_etf():
    """ETF 유니버스에 개별 기업 재무 지표 칩이 나오면 계약 위반."""
    response = {"clarification_question": "어떤 조건에서 매수할까요?",
                "pending_ask": {"chips": ["PER 10 이하", "RSI 30 이하"]}}
    result = response_contract_kept(response, forbidden_terms=["PER", "ROE"])
    assert result["score"] == 0.0
    assert "PER" in result["comment"]


def test_response_contract_passes_when_clean():
    response = {"clarification_question": "어떤 조건에서 매수할까요?",
                "pending_ask": {"chips": ["RSI 30 이하", "골든크로스"]}}
    assert response_contract_kept(response, forbidden_terms=["PER", "ROE"])["score"] == 1.0


def test_response_contract_skips_without_labels():
    assert response_contract_kept({"clarification_question": "q"})["score"] is None


# ── 6. 진전 ───────────────────────────────────────────────────────────────────

def test_clarification_counts_as_progress():
    """되묻기는 실패가 아니다 — 말하지 않은 값을 묻는 것이 Agent의 계약이다."""
    result = turn_made_progress({"clarification_question": "최대 몇 종목을 보유할까요?",
                                 "outcome": "ask"})
    assert result["score"] == 1.0


def test_answer_counts_as_progress():
    assert turn_made_progress({"outcome": "answer", "symbol_count": 30})["score"] == 1.0


def test_no_question_and_no_answer_is_failure():
    assert turn_made_progress({"outcome": "ask"})["score"] == 0.0
    assert turn_made_progress(None)["score"] == 0.0


# ── 집계 ──────────────────────────────────────────────────────────────────────

def test_evaluate_trace_returns_all_six_axes():
    results = evaluate_trace({
        "dag": _dag(_VALID_FINISH_CHAIN),
        "node_statuses": {"v": "COMPLETED", "c": "COMPLETED", "f": "COMPLETED"},
        "changed_fields": [],
        "called_tools": ["validate_intent", "compile_strategy"],
        "response": {"outcome": "answer", "symbol_count": 10},
    })
    assert len(results) == 6
    assert summarize(results)["mean"] == 1.0


def test_summarize_excludes_unscored_axes():
    results = evaluate_trace({"response": {"clarification_question": "q"}})
    summary = summarize(results)
    # DAG·State·Tool·응답계약은 근거가 없어 채점되지 않는다.
    assert summary["skipped"] == 5
    assert summary["scored"] == 1
    assert summary["mean"] == 1.0


def test_summarize_with_no_scored_axes_reports_none():
    assert summarize([{"key": "x", "score": None, "comment": ""}])["mean"] is None


# ── Dataset ───────────────────────────────────────────────────────────────────

def test_dataset_covers_spec_examples():
    assert len(EXAMPLES) == 21
    categories = {e["category"].split("/")[0] for e in EXAMPLES}
    assert {"생성", "수정", "제어", "규제", "테마"} <= categories


def test_dataset_examples_have_unique_inputs():
    inputs = [e["input"] for e in EXAMPLES]
    assert len(inputs) == len(set(inputs))


def test_dataset_rows_carry_labels_as_metadata():
    rows = as_langsmith_examples()
    assert len(rows) == len(EXAMPLES)
    etf = next(r for r in rows if r["inputs"]["user_input"] == "반도체 ETF 투자 전략")
    # ETF는 개별 기업 재무 지표를 쓸 수 없다는 계약이 라벨로 실려야 한다.
    assert "PER" in etf["metadata"]["forbidden_terms"]
    # 정답 전략(reference output)은 두지 않는다 — 되묻기가 정상 동작이기 때문.
    assert etf["outputs"] == {}
