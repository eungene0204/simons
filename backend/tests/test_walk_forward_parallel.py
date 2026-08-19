"""워크포워드 창 단위 프로세스 병렬(engine/wfa_workers.py) — 순차 실행과 결과 동일 + 진행률 합산.

실제 BacktestEngine + 합성 parquet(mock_data_dir)로 spawn 워커 2개를 띄운다.
"""

import copy
import json
import os

import pytest

from backtest_engine import BacktestEngine
from engine.walk_forward import WalkForwardAnalyzer, resolve_worker_count


def _req(symbols):
    return {
        "symbols": symbols,
        "universe_id": None,
        "period": "full",
        "startDate": "2023-01-15",
        "endDate": "2023-12-15",
        "entry": {"logic": "AND", "conditions": [
            {"id": "rsi", "type": "entry", "params": {"period": 14, "operator": "<", "value": 45}},
        ]},
        "exit": {"logic": "OR", "conditions": [
            {"id": "rsi", "type": "exit", "params": {"period": 14, "operator": ">", "value": 55}},
        ]},
        "risk": {"init_cash": 10_000_000, "stop_loss": 0.05, "take_profit": None, "max_positions": 3},
        "options": {"execution_type": "next_open"},
    }


_RANGES = {"risk.stop_loss": [0.05, 0.10]}


def _strip(result):
    return json.dumps(result, sort_keys=True, default=str)


# ── 워커 수 결정 ────────────────────────────────────────────────────

def test_resolve_worker_count_env_and_bounds(monkeypatch):
    monkeypatch.delenv("WALK_FORWARD_WORKERS", raising=False)
    assert resolve_worker_count(1) == 1                     # 창 1개면 항상 순차
    monkeypatch.setenv("WALK_FORWARD_WORKERS", "1")
    assert resolve_worker_count(6) == 1                     # 명시 1 = 순차
    monkeypatch.setenv("WALK_FORWARD_WORKERS", "4")
    assert resolve_worker_count(6) == 4
    assert resolve_worker_count(3) == 3                     # 창 수를 넘지 않는다
    monkeypatch.setenv("WALK_FORWARD_WORKERS", "abc")
    assert resolve_worker_count(6) >= 1                     # 잘못된 값은 자동 결정으로


def test_stub_engine_without_worker_spec_runs_sequentially(monkeypatch):
    """worker_spec()이 없는 엔진(테스트 스텁)은 워커 수 설정과 무관하게 순차로 돈다."""
    monkeypatch.setenv("WALK_FORWARD_WORKERS", "4")

    class Stub:
        def run_backtest(self, req):
            n = 400
            return {"dates": [f"2020-{(i // 28) % 12 + 1:02d}-{i % 28 + 1:02d}" for i in range(n)],
                    "equity": [1.0] * n, "cagr": 1.0}

    analyzer = WalkForwardAnalyzer(Stub())
    called = {}
    analyzer._run_windows_parallel = lambda *a, **k: called.setdefault("parallel", True) or {"status": "error", "message": "x"}
    result = analyzer.analyze(base_request={"symbols": ["A"], "entry": {"conditions": []}, "exit": {"conditions": []}},
                              ranges={"risk.stop_loss": [0.05, 0.1]}, method="grid", n_splits=3, train_pct=0.5)
    assert "parallel" not in called
    assert result["status"] == "ok"


# ── 실제 엔진: 병렬 == 순차 ────────────────────────────────────────

def test_parallel_windows_match_sequential_and_report_aggregated_progress(mock_data_dir, monkeypatch):
    symbols = ["ALPHA", "BETA", "GAMMA"]
    engine = BacktestEngine(data_dir=mock_data_dir)
    kwargs = dict(base_request=_req(symbols), ranges=_RANGES, method="grid", is_bars=100, oos_bars=40)

    monkeypatch.setenv("WALK_FORWARD_WORKERS", "1")
    seq_events = []
    seq = WalkForwardAnalyzer(engine).analyze(progress_callback=seq_events.append, **copy.deepcopy(kwargs))
    assert seq["status"] == "ok" and len(seq["windows"]) >= 2, seq.get("message")
    assert any((w.get("oos_metrics") or {}).get("trades") for w in seq["windows"]), "거래가 있는 창이 있어야 한다"

    monkeypatch.setenv("WALK_FORWARD_WORKERS", "2")
    par_events = []
    par = WalkForwardAnalyzer(engine).analyze(progress_callback=par_events.append, **copy.deepcopy(kwargs))
    assert par["status"] == "ok", par.get("message")

    assert _strip(par) == _strip(seq)

    # 병렬 진행률: 창별 시도 이벤트를 합산한 필드가 붙는다
    window_events = [e for e in par_events if e.get("stage") == "window"]
    assert window_events, "창 진행 이벤트가 있어야 한다"
    assert all("trials_done" in e and "windows_done" in e and e.get("workers") == 2 for e in window_events)
    last = window_events[-1]
    assert last["windows_done"] == len(seq["windows"])
    assert last["trials_done"] == len(seq["windows"]) * 2   # 그리드 2조합 × 창 수
    # 순차 이벤트에는 병렬 전용 필드가 없다(기존 프론트 계약 유지)
    assert all("trials_done" not in e for e in seq_events)


def test_parallel_cancel_returns_cancelled(mock_data_dir, monkeypatch):
    symbols = ["ALPHA", "BETA", "GAMMA"]
    engine = BacktestEngine(data_dir=mock_data_dir)
    monkeypatch.setenv("WALK_FORWARD_WORKERS", "2")
    seen = {"n": 0}

    def should_cancel():
        seen["n"] += 1
        return seen["n"] > 3   # 몇 번 물은 뒤 취소

    result = WalkForwardAnalyzer(engine).analyze(
        base_request=_req(symbols), ranges={"risk.stop_loss": [0.03, 0.05, 0.08, 0.10, 0.12, 0.15]},
        method="grid", is_bars=100, oos_bars=40, should_cancel=should_cancel,
    )
    assert result["status"] == "cancelled"
