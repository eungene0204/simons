"""backtest_executor 디스패처 — 로컬/원격 분기·원격 실패 시 폴백 금지 검증."""

import pytest

import backtest_executor


class FakeEngine:
    def __init__(self):
        self.calls = []

    def run_backtest(self, req):
        self.calls.append(req)
        return {"trades": 1, "source": "local"}


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

    def fake_post(url, json=None, headers=None, timeout=None):
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

    def fake_post(url, json=None, headers=None, timeout=None):
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

    def fake_post(url, json=None, headers=None, timeout=None):
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
