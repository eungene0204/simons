"""Trace 보관 정책 테스트 — 원문 3일, 집계 후 폐기(사용자 결정 2026-08-11).

고정할 계약 셋:
1. 기한(오늘 포함 3일)을 넘긴 날짜 파일만 지운다 — 최근 파일·비날짜 파일은 불변.
2. 폐기 전 집계에는 **사용자 원문이 없다** — 개수·라벨 분포뿐이다.
3. 집계 실패는 폐기를 막지 않는다 — 보관 기한이 정책이고 집계는 부가물이다.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

from observability import retention


_TODAY = dt.date(2026, 8, 11)


def _trace_line(query: str, intent: str, **outputs) -> str:
    return json.dumps({
        "trace_id": "t1",
        "root": "Classifier · 의도 분류",
        "span": {
            "name": "Classifier · 의도 분류",
            "inputs": {"query": query},
            "outputs": {"intent": intent, **outputs},
            "children": [],
        },
    }, ensure_ascii=False)


def _write(trace_dir, name: str, lines: list[str]) -> None:
    (trace_dir / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_sweep_removes_only_expired_date_files(tmp_path):
    _write(tmp_path, "2026-08-07.jsonl", [_trace_line("옛 질문", "UNKNOWN")])
    _write(tmp_path, "2026-08-08.jsonl", [_trace_line("옛 질문2", "GREETING")])
    _write(tmp_path, "2026-08-09.jsonl", [_trace_line("보관분", "STRATEGY_ADVICE")])
    _write(tmp_path, "2026-08-11.jsonl", [_trace_line("오늘", "STRATEGY_ADVICE")])
    _write(tmp_path, "notes.jsonl", ["{}"])  # 날짜 형식이 아니면 대상 아님

    removed = retention.sweep(tmp_path, _TODAY)

    assert [p.name for p in removed] == ["2026-08-07.jsonl", "2026-08-08.jsonl"]
    remaining = {p.name for p in tmp_path.glob("*.jsonl")}
    # 오늘 포함 3일(09·10·11)은 남고, 요약 파일이 새로 생긴다.
    assert remaining == {
        "2026-08-09.jsonl", "2026-08-11.jsonl", "notes.jsonl",
        retention.SUMMARY_FILENAME,
    }


def test_summary_counts_without_raw_text(tmp_path):
    """집계에는 발화 원문이 실리지 않는다 — 폐기의 목적 자체가 원문 제거다."""
    secret = "삼성전자 계좌에 3억 있는데 PER 얼마야?"
    _write(tmp_path, "2026-08-01.jsonl", [
        _trace_line(secret, "STOCK_ANALYSIS", fact_metric="per"),
        _trace_line("반도체 목록", "STOCK_PICK", list_scope="반도체"),
        _trace_line("모르는 말", "UNKNOWN", interpretation_failed=True),
    ])

    retention.sweep(tmp_path, _TODAY)

    summary_text = (tmp_path / retention.SUMMARY_FILENAME).read_text(encoding="utf-8")
    assert secret not in summary_text and "반도체 목록" not in summary_text
    summary = json.loads(summary_text)
    assert summary["date"] == "2026-08-01"
    assert summary["traces"] == 3
    assert summary["classify_intents"] == {
        "STOCK_ANALYSIS": 1, "STOCK_PICK": 1, "UNKNOWN": 1,
    }
    assert summary["fact_metric_answers"] == 1
    assert summary["list_scope_answers"] == 1
    assert summary["interpretation_failures"] == 1


def test_unreadable_file_is_still_discarded(tmp_path):
    """집계가 실패해도(파손 파일) 원문은 폐기된다 — 기한이 정책이다."""
    (tmp_path / "2026-08-01.jsonl").write_bytes(b"\xff\xfe not json")

    removed = retention.sweep(tmp_path, _TODAY)

    assert [p.name for p in removed] == ["2026-08-01.jsonl"]
    assert not (tmp_path / "2026-08-01.jsonl").exists()


def test_maybe_sweep_runs_once_per_day(tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "_last_sweep_date", None)
    calls = []
    monkeypatch.setattr(retention, "sweep", lambda d, t: calls.append(t))

    retention.maybe_sweep(tmp_path, _TODAY)
    retention.maybe_sweep(tmp_path, _TODAY)          # 같은 날 — 스킵
    retention.maybe_sweep(tmp_path, _TODAY + dt.timedelta(days=1))  # 다음 날 — 실행

    assert calls == [_TODAY, _TODAY + dt.timedelta(days=1)]


def test_emit_triggers_retention(tmp_path, monkeypatch):
    """기록 경로가 스윕을 부른다 — cron 없이 Trace가 도는 곳에서 정리된다."""
    monkeypatch.setenv("AGENT_TRACE_LOCAL", "1")
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr(retention, "_last_sweep_date", None)
    old = tmp_path / f"{_TODAY - dt.timedelta(days=10):%Y-%m-%d}.jsonl"
    _write(tmp_path, old.name, [_trace_line("옛 질문", "UNKNOWN")])

    from observability import local_trace

    node, token = local_trace.start("테스트", "chain", {}, {})
    local_trace.finish(node, token, 1.0)

    assert not old.exists()
    assert (tmp_path / retention.SUMMARY_FILENAME).exists()
