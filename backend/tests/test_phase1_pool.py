"""Phase1 프로세스 풀(engine/phase1_pool.py) — 스레드 경로와 결과 동일 + 세션 캐시가 워커에서 적중.

실제 BacktestEngine + 합성 parquet(mock_data_dir)로 spawn 워커 2개를 띄운다.
"""

import copy
import json

import pytest

from backtest_engine import BacktestEngine
from engine import phase1_pool


def _req(symbols, threshold=45, stop_loss=0.05):
    return {
        "symbols": symbols,
        "universe_id": None,
        "period": "full",
        "startDate": "2023-04-01",
        "endDate": "2023-12-15",
        "entry": {"logic": "AND", "conditions": [
            {"id": "rsi", "type": "entry", "params": {"period": 14, "operator": "<", "value": threshold}},
        ]},
        "exit": {"logic": "OR", "conditions": [
            {"id": "rsi", "type": "exit", "params": {"period": 14, "operator": ">", "value": 55}},
        ]},
        "risk": {"init_cash": 10_000_000, "stop_loss": stop_loss, "take_profit": None, "max_positions": 3},
        "options": {"execution_type": "next_open"},
    }


# mock_data_dir의 합성 시세는 hash(symbol)에 좌우돼 실행마다 다르다 — 거래가 흔히 나는 넓은 RSI 임계값(45/55)을 쓴다.
def _comparable(res):
    r = dict(res)
    r.pop("timing", None)
    r.pop("rebalanceComparison", None)
    r["warnings"] = sorted(r.get("warnings") or [])
    r["resolution_logs"] = sorted(json.dumps(x, sort_keys=True) for x in (r.get("resolution_logs") or []))
    return json.dumps(r, sort_keys=True, default=str)


@pytest.fixture(autouse=True)
def _reset_pools():
    yield
    phase1_pool.shutdown_all()


def test_shard_is_deterministic_and_in_range():
    assert phase1_pool.shard_of("005930", 4) == phase1_pool.shard_of("005930", 4)
    assert all(0 <= phase1_pool.shard_of(s, 3) < 3 for s in ("A", "B", "C", "005930", "GAMMA"))


def test_pool_disabled_when_workers_le_1(monkeypatch):
    monkeypatch.setenv("BACKTEST_PHASE1_WORKERS", "1")
    assert phase1_pool.get_pool({"data_dir": "/nonexistent"}) is None
    monkeypatch.setenv("BACKTEST_PHASE1_WORKERS", "0")
    assert phase1_pool.get_pool({"data_dir": "/nonexistent"}) is None


def test_pool_results_match_thread_path_and_session_hits_in_workers(mock_data_dir, monkeypatch):
    symbols = ["ALPHA", "BETA", "GAMMA"]
    engine = BacktestEngine(data_dir=mock_data_dir)
    cases = [_req(symbols, 45, 0.05), _req(symbols, 40, 0.05), _req(symbols, 45, 0.10)]

    # 스레드 경로(풀 비활성)
    monkeypatch.setenv("BACKTEST_PHASE1_WORKERS", "1")
    plain_raw = [engine.run_backtest(copy.deepcopy(c)) for c in cases]
    assert all((r.get("trades") or 0) > 0 for r in plain_raw), "거래가 있는 전략이어야 동일성 검증이 의미 있다"
    plain = [_comparable(r) for r in plain_raw]

    # 프로세스 풀 경로 — 종목 3개라 최소 종목 수 문턱을 1로 낮춘다
    monkeypatch.setenv("BACKTEST_PHASE1_WORKERS", "2")
    monkeypatch.setenv("BACKTEST_PHASE1_POOL_MIN_SYMBOLS", "1")
    pooled_raw = [engine.run_backtest(copy.deepcopy(c)) for c in cases]
    pooled = [_comparable(r) for r in pooled_raw]
    assert pooled == plain
    # 리밸런싱 기간별 비교(FR-BT-064)는 풀 워커가 Format과 겹쳐 계산한다 — 동기 경로와 같아야 한다
    for a, b in zip(plain_raw, pooled_raw):
        assert a["rebalanceComparison"] == b["rebalanceComparison"]
        assert len(a["rebalanceComparison"]["periods"]) == 6

    # 최적화 세션: 워커 캐시가 적중해야 한다(2·3번째 케이스는 값만 달라 지표 동일)
    with engine.optimization_session():
        in_session = [_comparable(engine.run_backtest(copy.deepcopy(c))) for c in cases]
    assert in_session == plain
    pool = phase1_pool.get_pool(engine.worker_spec())
    assert pool is not None
    stats = pool.last_session_stats
    assert stats["hits"] == 6 and stats["misses"] == 3, stats


def test_pool_below_min_symbols_uses_thread_path(mock_data_dir, monkeypatch, capsys):
    monkeypatch.setenv("BACKTEST_PHASE1_WORKERS", "2")
    monkeypatch.setenv("BACKTEST_PHASE1_POOL_MIN_SYMBOLS", "10")
    engine = BacktestEngine(data_dir=mock_data_dir)
    res = engine.run_backtest(_req(["ALPHA", "BETA", "GAMMA"]))
    assert res.get("trades") is not None
    out = capsys.readouterr().out
    # 문턱 미만이면 Phase1은 스레드 경로(워커 표기 없음). 리밸런싱 비교는 풀을 써도 된다.
    phase1_line = next(l for l in out.splitlines() if "Phase1 시작" in l)
    assert "workers=" not in phase1_line
    assert len(res["rebalanceComparison"]["periods"]) == 6
