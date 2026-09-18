"""backtest_executor 디스패처 — 로컬/원격 분기·박스 우선 칸·원격 실패 시 폴백 금지 검증."""

import pytest

import backtest_executor


class FakeEngine:
    def __init__(self):
        self.calls = []

    def run_backtest(self, req):
        self.calls.append(req)
        return {"trades": 1, "source": "local"}


@pytest.fixture(autouse=True)
def _no_local_slots(monkeypatch):
    """박스 실행 칸은 테스트가 명시할 때만 연다(기본 0 = 원격 설정 시 전부 워커)."""
    monkeypatch.delenv("BACKTEST_LOCAL_SLOTS", raising=False)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_default_is_local(monkeypatch):
    """env 미설정이면 종전 그대로 로컬 엔진을 부른다."""
    monkeypatch.delenv("BACKTEST_EXECUTOR", raising=False)
    monkeypatch.delenv("BACKTEST_REMOTE_URL", raising=False)
    engine = FakeEngine()
    assert backtest_executor.run(engine, {"a": 1}) == {"trades": 1, "source": "local"}
    assert engine.calls == [{"a": 1}]


def test_modal_without_url_is_local(monkeypatch):
    """BACKTEST_EXECUTOR=modal 이어도 URL이 없으면 로컬(불완전 설정으로 원격 시도 금지)."""
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.delenv("BACKTEST_REMOTE_URL", raising=False)
    engine = FakeEngine()
    backtest_executor.run(engine, {})
    assert engine.calls == [{}]


def test_remote_success_skips_engine(monkeypatch):
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", "https://worker.example/run")
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        sent.update({"url": url, "json": json, "headers": headers})
        return FakeResponse(payload={"trades": 5, "source": "remote"})

    monkeypatch.setattr(backtest_executor.httpx, "post", fake_post)
    engine = FakeEngine()
    result = backtest_executor.run(engine, {"symbols": ["005930"]})
    assert result == {"trades": 5, "source": "remote"}
    assert engine.calls == []  # 원격 성공 시 로컬 엔진은 절대 실행되지 않는다
    assert sent["url"] == "https://worker.example/run"
    assert sent["json"] == {"symbols": ["005930"]}


def test_remote_http_error_raises_without_fallback(monkeypatch):
    """비200이면 RemoteBacktestError — 로컬 폴백(레인 오염) 금지."""
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", "https://worker.example/run")
    monkeypatch.setattr(
        backtest_executor.httpx, "post",
        lambda *a, **kw: FakeResponse(status_code=503, text="cold"),
    )
    engine = FakeEngine()
    with pytest.raises(backtest_executor.RemoteBacktestError):
        backtest_executor.run(engine, {})
    assert engine.calls == []


def test_remote_connection_error_raises_without_fallback(monkeypatch):
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", "https://worker.example/run")

    def fake_post(*a, **kw):
        raise backtest_executor.httpx.ConnectError("refused")

    monkeypatch.setattr(backtest_executor.httpx, "post", fake_post)
    engine = FakeEngine()
    with pytest.raises(backtest_executor.RemoteBacktestError):
        backtest_executor.run(engine, {})
    assert engine.calls == []


REMOTE_BT_URL = "https://eugene204--simons-backtest-run-backtest.modal.run"


def test_job_url_derivation(monkeypatch):
    """잡 URL은 run-backtest 슬러그 치환으로 파생 — Modal 함수명과 1:1."""
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", REMOTE_BT_URL)
    assert backtest_executor.job_url("run-optimize") == \
        "https://eugene204--simons-backtest-run-optimize.modal.run"
    assert backtest_executor.job_url("run-walk-forward-stream") == \
        "https://eugene204--simons-backtest-run-walk-forward-stream.modal.run"


def test_job_url_local_mode_is_none(monkeypatch):
    monkeypatch.delenv("BACKTEST_EXECUTOR", raising=False)
    monkeypatch.delenv("BACKTEST_REMOTE_URL", raising=False)
    assert backtest_executor.job_url("run-optimize") is None


def test_job_url_underivable_raises(monkeypatch):
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", "https://worker.example/custom")
    with pytest.raises(backtest_executor.RemoteBacktestError):
        backtest_executor.job_url("run-optimize")


def test_run_optimization_remote_dispatch(monkeypatch):
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", REMOTE_BT_URL)
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        sent.update({"url": url, "json": json})
        return FakeResponse(payload={"status": "ok", "best_params": {}})

    monkeypatch.setattr(backtest_executor.httpx, "post", fake_post)
    result = backtest_executor.run_optimization(
        FakeEngine(), base_request={"symbols": []}, user_prompt="p",
        ranges={"risk.stop_loss_pct": [5, 10]}, target_metric="sharpe", n_trials=5)
    assert result["status"] == "ok"
    assert sent["url"].endswith("run-optimize.modal.run")
    assert sent["json"]["n_trials"] == 5


def test_run_walk_forward_remote_dispatch(monkeypatch):
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", REMOTE_BT_URL)
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None, **kw):
        sent.update({"url": url, "json": json})
        return FakeResponse(payload={"status": "ok"})

    monkeypatch.setattr(backtest_executor.httpx, "post", fake_post)
    payload = {"base_request": {"symbols": []}, "method": "grid", "n_splits": 3}
    assert backtest_executor.run_walk_forward(FakeEngine(), payload) == {"status": "ok"}
    assert sent["url"].endswith("run-walk-forward.modal.run")
    assert sent["json"]["method"] == "grid"


def test_run_walk_forward_local_calls_analyzer(monkeypatch):
    monkeypatch.delenv("BACKTEST_EXECUTOR", raising=False)
    monkeypatch.delenv("BACKTEST_REMOTE_URL", raising=False)
    import engine.walk_forward as wf

    captured = {}

    class FakeAnalyzer:
        def __init__(self, engine):
            captured["engine"] = engine

        def analyze(self, **kwargs):
            captured["kwargs"] = kwargs
            return {"status": "ok", "lane": "local"}

    monkeypatch.setattr(wf, "WalkForwardAnalyzer", FakeAnalyzer)
    engine = FakeEngine()
    result = backtest_executor.run_walk_forward(engine, {"base_request": {"a": 1}, "n_splits": 3})
    assert result["lane"] == "local"
    assert captured["engine"] is engine
    assert captured["kwargs"]["n_splits"] == 3


def test_walk_forward_stream_error_becomes_sse_event(monkeypatch):
    """스트림 연결 실패는 예외가 아니라 SSE error 이벤트로 — 클라이언트 프로토콜 보존."""
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", REMOTE_BT_URL)

    def fake_stream(*a, **kw):
        raise backtest_executor.httpx.ConnectError("refused")

    monkeypatch.setattr(backtest_executor.httpx, "stream", fake_stream)
    chunks = b"".join(backtest_executor.iter_walk_forward_stream({"base_request": {}}))
    assert b'"type": "error"' in chunks
    assert b"[DONE]" in chunks


def test_remote_follows_modal_303_redirect(monkeypatch):
    """Modal은 150초 넘는 요청에 303(결과 조회 URL)을 준다 — 따라가야 결과를 받는다.

    2026-09-17 사고: ETF 1270종목 콜드 168s 요청이 워커에서 끝났는데 "원격 백테스트 워커 HTTP 303"으로 실패.
    """
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", REMOTE_BT_URL)
    sent = {}

    def fake_post(url, **kw):
        sent.update(kw)
        return FakeResponse(payload={"trades": 1})

    monkeypatch.setattr(backtest_executor.httpx, "post", fake_post)
    backtest_executor.run(FakeEngine(), {})
    assert sent["follow_redirects"] is True


def _remote_marker(monkeypatch):
    monkeypatch.setenv("BACKTEST_EXECUTOR", "modal")
    monkeypatch.setenv("BACKTEST_REMOTE_URL", REMOTE_BT_URL)
    remote_calls = []

    def fake_post(url, json=None, **kw):
        remote_calls.append(json)
        return FakeResponse(payload={"source": "remote"})

    monkeypatch.setattr(backtest_executor.httpx, "post", fake_post)
    return remote_calls


def test_free_local_slot_runs_on_box(monkeypatch):
    """박스 우선: 빈 칸이 있으면 원격 설정이어도 박스 엔진으로 돈다."""
    remote_calls = _remote_marker(monkeypatch)
    monkeypatch.setenv("BACKTEST_LOCAL_SLOTS", "1")
    engine = FakeEngine()
    assert backtest_executor.run(engine, {"a": 1})["source"] == "local"
    assert engine.calls == [{"a": 1}]
    assert remote_calls == []


class NestedEngine(FakeEngine):
    """실행 도중 다른 요청이 들어온 상황 — 칸을 쥔 채로 두 번째 run을 부른다."""

    inner_results: list = []

    def run_backtest(self, req):
        self.calls.append(req)
        if req.get("outer"):
            NestedEngine.inner_results.append(backtest_executor.run(NESTED_SHARED["engine"], {"inner": True}))
        return {"source": "local", "engine": id(self)}


NESTED_SHARED: dict = {}


def test_full_local_slots_overflow_to_modal(monkeypatch):
    """칸이 다 차 있으면 기다리지 않고 워커로 넘친다."""
    remote_calls = _remote_marker(monkeypatch)
    monkeypatch.setenv("BACKTEST_LOCAL_SLOTS", "1")
    engine = NestedEngine()
    NESTED_SHARED["engine"] = engine
    NestedEngine.inner_results = []
    assert backtest_executor.run(engine, {"outer": True})["source"] == "local"
    assert NestedEngine.inner_results == [{"source": "remote"}]
    assert remote_calls == [{"inner": True}]


def test_concurrent_local_runs_use_separate_engine_instances(monkeypatch):
    """엔진은 실행별 상태(self.warnings)를 인스턴스에 들고 있다 — 동시 박스 실행은 인스턴스를 나눈다."""
    remote_calls = _remote_marker(monkeypatch)
    monkeypatch.setenv("BACKTEST_LOCAL_SLOTS", "2")
    engine = NestedEngine()
    NESTED_SHARED["engine"] = engine
    NestedEngine.inner_results = []
    outer = backtest_executor.run(engine, {"outer": True})
    inner = NestedEngine.inner_results[0]
    assert outer["engine"] == id(engine)
    assert inner["source"] == "local" and inner["engine"] != id(engine)
    assert remote_calls == []


def test_local_slot_released_after_engine_error(monkeypatch):
    """박스 실행이 예외로 끝나도 칸은 반납된다(다음 요청이 영영 워커로 가지 않게)."""
    remote_calls = _remote_marker(monkeypatch)
    monkeypatch.setenv("BACKTEST_LOCAL_SLOTS", "1")

    class BoomEngine(FakeEngine):
        def run_backtest(self, req):
            raise ValueError("boom")

    with pytest.raises(ValueError):
        backtest_executor.run(BoomEngine(), {})
    engine = FakeEngine()
    assert backtest_executor.run(engine, {"b": 2})["source"] == "local"
    assert remote_calls == []


@pytest.mark.parametrize("raw", ["", "abc", "-3"])
def test_invalid_local_slots_mean_zero(monkeypatch, raw):
    monkeypatch.setenv("BACKTEST_LOCAL_SLOTS", raw)
    assert backtest_executor.local_slots() == 0
