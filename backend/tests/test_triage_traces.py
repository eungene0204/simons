"""Trace 실패 분류(scripts/triage_traces.py) 회귀.

고정할 계약:
1. 판정은 구조 신호만 본다 — 사용자 원문이 달라도 구조가 같으면 신호가 같다(대원칙 1).
2. 인프라 오류(상류 429·취소)는 결함과 섞지 않고, 전파된 여러 줄을 턴당 하나로 센다.
3. 같은 질문 반복은 우리가 낸 질문 문장의 동일성으로만 판정한다.
4. 컴파일러가 뺀 조건 중 값 대기로 올라간 것은 '조용한 소실'이 아니다.
5. 리포트는 원문을 담으므로 Trace와 같은 기한으로 지운다.
"""

from __future__ import annotations

import datetime as dt
import json

from scripts import triage_traces as tt


def _agent_record(user_input="코스피 전략", *, outputs=None, inputs=None, children=None,
                  total_ms=1000.0):
    return {
        "trace_id": "t1",
        "ts": "2026-10-10T10:00:00.000+09:00",
        "root": tt._AGENT_ROOT,
        "total_ms": total_ms,
        "span": {
            "name": tt._AGENT_ROOT,
            "inputs": {"user_input": user_input, **(inputs or {})},
            "outputs": {"outcome": "ask", **(outputs or {})},
            "metadata": {"environment": "development", "session_id": "s1", "turn_kind": "create"},
            "children": children or [],
        },
    }


def _signals(record):
    return sorted((f["signal"], f["key"]) for f in tt.classify(record))


def test_classification_ignores_user_text():
    children = [{"name": tt._COMPILE_SPAN, "outputs": {"observation": {
        "dropped": ["진입 후 10거래일 경과"], "pending_conditions": []}}}]
    a = _agent_record("문장 A", children=children)
    b = _agent_record("completely different B", children=children)
    assert _signals(a) == _signals(b) == [("dropped_condition", "진입 후 10거래일 경과")]


def test_infra_error_deduped_and_separated_from_defects():
    children = [{
        "name": tt._INTERPRETER_SPAN, "error": "HTTPError: HTTP Error 429: Too Many Requests",
        "children": [{"name": "LLM · x", "error": "HTTPError: HTTP Error 429: Too Many Requests"}],
    }]
    signals = _signals(_agent_record(children=children))
    assert signals == [("infra_error", f"{tt._INTERPRETER_SPAN} · HTTPError")]


def test_interpreter_and_planner_errors_are_defects():
    children = [
        {"name": tt._INTERPRETER_SPAN, "error": "InterpreterError: 스키마 불만족"},
        {"name": tt._PLANNER_SPAN, "error": "[TurnBudgetExhausted] 턴 예산 소진"},
    ]
    assert _signals(_agent_record(children=children)) == [
        ("interpreter_error", "InterpreterError"),
        ("planner_error", "TurnBudgetExhausted"),
    ]


def test_ask_repeat_uses_question_identity_only():
    question = "포트폴리오에 최대 몇 종목을 담을까요?"
    repeated = _agent_record("답변", inputs={"pending_question": question},
                             outputs={"clarification_question": question})
    moved_on = _agent_record("답변", inputs={"pending_question": question},
                             outputs={"clarification_question": "리밸런싱 주기는요?"})
    assert ("ask_repeat", question) in _signals(repeated)
    assert _signals(moved_on) == []


def test_pending_dropped_condition_is_not_dropped_condition():
    children = [{"name": tt._COMPILE_SPAN, "outputs": {"observation": {
        "dropped": ["PER(주가수익비율)"],
        "pending_conditions": [{"role": "entry", "label": "PER(주가수익비율)"}]}}}]
    assert _signals(_agent_record(children=children)) == []


def test_validation_error_only_when_turn_did_not_answer():
    children = [{"name": tt._VALIDATE_SPAN, "outputs": {"observation": {
        "intent": {}, "report": {"errors": ["'볼린저 밴드'에 알 수 없는 파라미터 'std_dev'"]}}}}]
    asked = _agent_record(children=children)
    answered = _agent_record(children=children, outputs={"outcome": "answer"})
    assert [s for s, _ in _signals(asked)] == ["validation_error"]
    assert _signals(answered) == []


def test_failure_priority_and_unsupported_and_approximated():
    children = [
        {"name": tt._VALIDATE_SPAN, "outputs": {"observation": {
            "intent": {"unsupported_features": ["5분봉 단타"]},
            "report": {"unsupported_features": ["5분봉 단타"]}}}},
        {"name": tt._INTERPRETER_SPAN, "outputs": {"strategy": {
            "entry_conditions": [{"factor": "technical.bollinger_bands", "approximated": True}]}}},
    ]
    record = _agent_record(children=children, outputs={"clarification_priority": "modify_unapplied"})
    assert _signals(record) == [
        ("approximated", "technical.bollinger_bands"),
        ("modify_unapplied", "modify_unapplied"),
        ("unsupported", "5분봉 단타"),
    ]


def test_classifier_root_failure():
    record = {"trace_id": "c1", "root": tt._CLASSIFY_SPAN, "total_ms": 10, "span": {
        "name": tt._CLASSIFY_SPAN, "inputs": {"query": "q"},
        "outputs": {"intent": "UNKNOWN", "interpretation_failed": True}}}
    assert _signals(record) == [("classifier_failed", "UNKNOWN")]


def test_triage_groups_by_tier_then_count():
    drop = [{"name": tt._COMPILE_SPAN, "outputs": {"observation": {"dropped": ["X"]}}}]
    slow = _agent_record(total_ms=200_000)
    groups = tt.triage(iter([_agent_record(children=drop), _agent_record(children=drop), slow]))
    assert [(g["signal"], g["count"], g["tier"]) for g in groups] == [
        ("dropped_condition", 2, "결함 후보"), ("slow_turn", 1, "인프라")]
    assert "결함 후보 2" in tt.render_summary(groups)


def test_error_class_normalization():
    assert tt.error_class("[NoProgress] turn=2 동일 DAG") == "NoProgress"
    assert tt.error_class("ValueError: unbalanced JSON") == "ValueError"
    assert tt.error_class("OperationCancelled: ") == "OperationCancelled"


def test_report_sweep_follows_trace_retention(tmp_path):
    today = dt.date(2026, 10, 11)
    for day in ("2026-10-08", "2026-10-09", "2026-10-11"):
        (tmp_path / f"{day}.md").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("keep", encoding="utf-8")
    tt.sweep_reports(tmp_path, today)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-10-09.md", "2026-10-11.md", "README.md"]


def test_main_reads_dated_files_only(tmp_path, capsys):
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "2026-10-10.jsonl").write_text(json.dumps(_agent_record(total_ms=200_000)) + "\n",
                                             encoding="utf-8")
    (traces / "coverage-summary.jsonl").write_text('{"date": "x"}\n', encoding="utf-8")
    assert tt.main(["--dir", str(traces), "--report-dir", str(tmp_path / "r"), "--summary"]) == 0
    assert "인프라 1" in capsys.readouterr().out


def test_report_named_by_oldest_trace_and_swept_in_every_mode(tmp_path):
    """리포트 원문이 Trace보다 오래 남지 않는다 — 이름=가장 오래된 Trace 날짜, --summary도 정리."""
    today = dt.date.today()
    traces, reports = tmp_path / "traces", tmp_path / "reports"
    traces.mkdir()
    reports.mkdir()
    oldest = today - dt.timedelta(days=tt.RETENTION_DAYS - 1)
    for day in (oldest, today):
        (traces / f"{day.isoformat()}.jsonl").write_text(json.dumps(_agent_record()) + "\n",
                                                        encoding="utf-8")
    assert tt.main(["--dir", str(traces), "--report-dir", str(reports)]) == 0
    assert sorted(p.name for p in reports.iterdir()) == [f"{oldest.isoformat()}.md"]

    expired = reports / f"{(oldest - dt.timedelta(days=1)).isoformat()}.md"
    expired.write_text("원문", encoding="utf-8")
    assert tt.main(["--dir", str(traces), "--report-dir", str(reports), "--summary"]) == 0
    assert not expired.exists()
