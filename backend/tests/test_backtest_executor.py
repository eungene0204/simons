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
