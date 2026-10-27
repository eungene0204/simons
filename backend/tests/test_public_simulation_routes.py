import copy
import sys
import threading
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import internal_auth
from api import public_simulation_routes as routes
from engine.watchdog import BacktestTimeoutError
from public_simulation.window import WindowError

BASE = "/internal/public-simulation"
SNAPSHOT = {
    "symbols": ["005930"],
    "entry": {"conditions": [{"type": "indicator", "id": "rsi",
                              "params": {"signalType": "buy", "period": 14, "operator": "<", "value": 30}}]},
    "exit": {"conditions": [{"type": "indicator", "id": "ma_crossover",
                             "params": {"signalType": "sell", "shortMA": 5, "longMA": 20}}]},
    "risk": {"position_size_pct": 100, "init_cash": 10_000_000, "execution_timing": "next_open"},
    "options": {"fee_rate": 0.00015, "slippage_rate": 0.0005},
    "period": "5y",
}


def engine_result(**over):
    base = {
        "initialCapital": 10_000_000, "equity": [10_000_000, 10_400_000, 11_000_000],
        "dates": ["2023-10-30", "2025-01-02", "2026-10-22"],
        "totalReturn": 10.0, "maxDrawdown": -3.0, "cagr": 3.2, "sharpe": 0.7, "volatility": 9.0,
        "winRate": 50.0, "trades": 2,
        "perAssetStats": {"005930": {"profit": 1_000_000, "trades": 2}},
        "tradingCosts": {"buyFeeRate": 0.00015, "sellFeeRate": 0.00015, "slippageRate": 0.0005,
                         "sellTaxRate": None, "sellTaxRateRange": [0.0015, 0.002]},
        "version": "16.43.0",
    }
    base.update(over)
    return base


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    calls = []

    def fake_execute(req):
        calls.append(req)
        return engine_result()

    monkeypatch.setattr(routes, "_data_as_of", lambda: date(2026, 10, 22))
    monkeypatch.setattr(routes, "_execute", fake_execute)
    monkeypatch.setattr(routes, "_name_lookup", lambda s: {"005930": "삼성전자"}.get(s))
    monkeypatch.setattr(routes, "_window", lambda: routes.compute_window(
        __import__("datetime").datetime(2026, 10, 23, 3, 0, tzinfo=__import__("datetime").timezone.utc), date(2026, 10, 22)))
    client = TestClient(app)
    client.calls = calls
    return client


def run(client, **body):
    return client.post(f"{BASE}/run", json={"snapshot": SNAPSHOT, **body})


# ── 경로 잠금·연결 ───────────────────────────────────────────────────────────

def test_paths_are_behind_internal_token_and_router_is_wired():
    for method, path in (("GET", "/baseline"), ("POST", "/describe"), ("POST", "/run")):
        assert internal_auth.is_protected(method, BASE + path)
    main_src = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "app.include_router(public_simulation_router)" in main_src


# ── baseline / describe ─────────────────────────────────────────────────────

def test_baseline_returns_window_and_engine_version(api):
    body = api.get(f"{BASE}/baseline").json()
    assert body["requestedStart"] == "2023-10-23" and body["endDate"] == "2026-10-22"
    assert body["dataAsOf"] == "2026-10-22" and body["engineVersion"]


def test_baseline_without_index_data_is_503(api, monkeypatch):
    def boom():
        raise WindowError("NO_INDEX_DATA", "데이터 기준일을 확인할 수 없습니다.")
    monkeypatch.setattr(routes, "_window", boom)
    res = api.get(f"{BASE}/baseline")
    assert res.status_code == 503 and res.json()["code"] == "NO_INDEX_DATA"


def test_describe_lists_editable_params_or_unavailable_reason(api):
    ok = api.post(f"{BASE}/describe", json={"snapshot": SNAPSHOT}).json()
    assert ok["status"] == "executable"
    assert {"entry.conditions.0.params.period", "exit.conditions.0.params.shortMA"} <= {p["path"] for p in ok["editableParams"]}
    meta_only = api.post(f"{BASE}/describe", json={"snapshot": {"name": "x"}}).json()
    assert meta_only["status"] == "unavailable" and meta_only["reason"] == "NO_EXECUTABLE_SNAPSHOT"
    assert meta_only["editableParams"] == []


# ── run ─────────────────────────────────────────────────────────────────────

def test_unavailable_snapshot_never_reaches_the_engine(api):
    snap = copy.deepcopy(SNAPSHOT)
    del snap["options"]["slippage_rate"]
    body = api.post(f"{BASE}/run", json={"snapshot": snap}).json()
    assert body["status"] == "unavailable" and body["reason"] == "MISSING_RUN_CONDITION"
    assert body["detail"] == ["options.slippage_rate"] and api.calls == []


def test_schema_invalid_snapshot_is_unavailable(api):
    snap = copy.deepcopy(SNAPSHOT)
    del snap["risk"]["position_size_pct"]
    body = api.post(f"{BASE}/run", json={"snapshot": snap}).json()
    assert body["status"] == "unavailable" and body["reason"] == "INVALID_SNAPSHOT" and api.calls == []


def test_original_run_uses_three_year_window_and_engine_values(api):
    body = run(api).json()
    req = api.calls[0]
    assert (req["startDate"], req["endDate"]) == ("2023-10-23", "2026-10-22")
    assert req["risk"]["init_cash"] == 10_000_000 and req["options"] == SNAPSHOT["options"]
    assert body["status"] == "ready" and body["summary"]["totalReturnPct"] == 10.0
    assert body["summary"]["totalProfit"] == 1_000_000 and body["dataAsOf"] == "2026-10-22"
    assert body["conditions"]["buyFeeRate"] == 0.00015 and body["conditions"]["initialCapital"] == 10_000_000
    assert body["contributors"]["top"][0]["name"] == "삼성전자"
    assert body["appliedOverrides"] == [] and body["window"]["actualEnd"] == "2026-10-22"
    assert any(p["path"] == "entry.conditions.0.params.period" for p in body["editableParams"])


def test_modified_run_keeps_window_capital_costs_and_leaves_original_untouched(api):
    before = copy.deepcopy(SNAPSHOT)
    run(api)
    body = run(api, overrides=[{"path": "entry.conditions.0.params.period", "value": 21}]).json()
    original_req, modified_req = api.calls
    for key in ("startDate", "endDate", "options"):
        assert original_req[key] == modified_req[key]
    assert original_req["risk"]["init_cash"] == modified_req["risk"]["init_cash"]
    assert original_req["entry"]["conditions"][0]["params"]["period"] == 14
    assert modified_req["entry"]["conditions"][0]["params"]["period"] == 21
    assert body["appliedOverrides"] == [{"path": "entry.conditions.0.params.period", "value": 21}]
    # 설명자의 original은 항상 원본 값 — 폼이 수정값을 원본으로 오해하지 않게.
    period = next(p for p in body["editableParams"] if p["path"].endswith("0.params.period"))
    assert period["original"] == 14 and SNAPSHOT == before


@pytest.mark.parametrize("override", [
    {"path": "entry.conditions.0.params.period", "value": 1},
    {"path": "entry.conditions.0.params.operator", "value": 3},
    {"path": "risk.init_cash", "value": 1},
])
def test_invalid_override_is_400_and_not_executed(api, override):
    res = run(api, overrides=[override])
    assert res.status_code == 400 and res.json()["code"] == "INVALID_PARAMETER"
    assert res.json()["errors"][0]["path"] == override["path"] and api.calls == []


def test_engine_failures_are_distinguishable_and_do_not_leak_details(api, monkeypatch):
    def fail(req):
        raise RuntimeError("secret path /srv/data/x.parquet")
    monkeypatch.setattr(routes, "_execute", fail)
    res = run(api)
    assert res.status_code == 500 and res.json()["code"] == "ENGINE_ERROR"
    assert "secret" not in res.text and "summary" not in res.json()

    monkeypatch.setattr(routes, "_execute", lambda req: (_ for _ in ()).throw(BacktestTimeoutError("t")))
    assert run(api).status_code == 504 and run(api).json()["code"] == "TIMEOUT"

    monkeypatch.setattr(routes, "_execute", lambda req: (_ for _ in ()).throw(routes.SimulationBusy()))
    res = run(api)
    assert res.status_code == 429 and res.json()["code"] == "BUSY" and res.json()["retryAfterSeconds"] > 0


@pytest.mark.parametrize("bad, code", [
    ({"totalReturn": 25.0}, "INCONSISTENT_RESULT"),                       # 평가자산과 어긋남
    ({"equity": [], "dates": []}, "EMPTY_RESULT"),
    ({"dates": ["2023-10-01", "2025-01-02", "2026-10-22"]}, "WINDOW_VIOLATION"),  # 요청 시작 이전
    ({"dates": ["2023-10-30", "2025-01-02", "2026-10-23"]}, "WINDOW_VIOLATION"),  # 데이터 기준일 이후(미래)
    ({"tradingCosts": None}, "MISSING_TRADING_COSTS"),
])
def test_bad_engine_result_is_failure_not_zero_or_no_trades(api, monkeypatch, bad, code):
    monkeypatch.setattr(routes, "_execute", lambda req: engine_result(**bad))
    res = run(api)
    assert res.status_code == 500 and res.json()["code"] == code
    assert "summary" not in res.json()


def test_no_trades_result_is_reported_as_no_trades(api, monkeypatch):
    flat = engine_result(equity=[10_000_000] * 3, totalReturn=0.0, maxDrawdown=0.0, trades=0, perAssetStats={})
    monkeypatch.setattr(routes, "_execute", lambda req: flat)
    body = run(api).json()
    assert body["status"] == "no_trades" and body["summary"]["trades"] == 0


# ── _execute: 동시 한도·슬롯 해제 ────────────────────────────────────────────

@pytest.fixture
def executor(monkeypatch):
    import backtest_executor
    monkeypatch.setitem(sys.modules, "main", SimpleNamespace(engine=object()))
    monkeypatch.setattr(routes, "_slots", threading.BoundedSemaphore(1))
    return backtest_executor, monkeypatch


def test_execute_rejects_when_slot_is_taken_and_releases_after_success(executor):
    backtest_executor, mp = executor
    mp.setattr(backtest_executor, "run", lambda engine, req: {"ok": True})
    assert routes._execute({}) == {"ok": True}
    assert routes._slots.acquire(blocking=False)          # 풀렸다면 다시 잡힌다
    with pytest.raises(routes.SimulationBusy):
        routes._execute({})
    routes._slots.release()


def test_execute_releases_slot_after_engine_error(executor):
    backtest_executor, mp = executor

    def boom(engine, req):
        raise RuntimeError("x")
    mp.setattr(backtest_executor, "run", boom)
    with pytest.raises(RuntimeError):
        routes._execute({})
    assert routes._slots.acquire(blocking=False)
    routes._slots.release()


def test_execute_holds_slot_until_abandoned_worker_finishes(executor):
    backtest_executor, mp = executor
    gate = threading.Event()
    mp.setenv("PUBLIC_SIMULATION_TIMEOUT_S", "0.05")
    mp.setattr(backtest_executor, "run", lambda engine, req: gate.wait(5))
    with pytest.raises(BacktestTimeoutError):
        routes._execute({})
    with pytest.raises(routes.SimulationBusy):             # 워치독이 버렸어도 계산 중이면 새 실행은 거절
        routes._execute({})
    gate.set()
    deadline = time.time() + 2
    while time.time() < deadline and not routes._slots.acquire(blocking=False):
        time.sleep(0.01)
    else:
        routes._slots.release()
        return
    pytest.fail("slot was never released")
