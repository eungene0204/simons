"""요청 취소('대화 종료') — cancellation 모듈과 LLM 호출 관문·SSE 스트림 결속 검증.

사용자가 전략 분석 중 '대화 종료'를 누르면 프론트가 요청을 끊고, 백엔드는
  1. 다음 LLM 호출을 열지 않고(OperationCancelled),
  2. 진행 중인 LLM HTTP 소켓을 닫아 생성을 끊으며,
  3. 취소된 요청의 결과를 캐시에 남기지 않고,
  4. SSE 제너레이터가 정상 종료 전에 닫히면(클라이언트 연결 종료) 토큰을 취소한다.
"""

from __future__ import annotations

import asyncio
import http.server
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import cancellation
import engine.nl_parser as nl_parser
from cancellation import CancelToken, OperationCancelled
from engine.nl_parser import _ollama_ensure_warm, _ollama_open_with_retry


# ─── 토큰 기본 동작 ─────────────────────────────────────────────────────────────


def test_operation_cancelled_bypasses_except_exception():
    """취소는 파이프라인의 `except Exception` 폴백에 삼켜지지 않는다(BaseException)."""
    with pytest.raises(OperationCancelled):
        try:
            raise OperationCancelled()
        except Exception:  # noqa: BLE001 — 폴백 흉내
            pytest.fail("OperationCancelled가 except Exception에 잡혔다")


def test_bind_scopes_token_to_context():
    token = CancelToken()
    assert cancellation.current() is None
    with cancellation.bind(token):
        assert cancellation.current() is token
        assert cancellation.is_cancelled() is False
        token.cancel()
        assert cancellation.is_cancelled() is True
        with pytest.raises(OperationCancelled):
            cancellation.raise_if_cancelled()
    assert cancellation.current() is None
    # 토큰이 없는 컨텍스트에서는 확인이 no-op이다(다른 urlopen 호출·비요청 경로 보호).
    cancellation.raise_if_cancelled()


def test_bind_does_not_leak_into_other_threads():
    """토큰은 묶은 스레드(컨텍스트)에만 보인다 — 다른 요청 스레드를 취소하지 않는다."""
    token = CancelToken()
    seen: dict = {}

    def other_thread():
        seen["token"] = cancellation.current()

    with cancellation.bind(token):
        t = threading.Thread(target=other_thread)
        t.start()
        t.join()
    assert seen["token"] is None


def test_cancel_closes_tracked_socket_and_wakes_blocked_reader():
    """취소가 추적 소켓을 닫아, recv에 막힌 스레드를 깨운다(진행 중 LLM 호출 차단의 원리)."""
    a, b = socket.socketpair()
    token = CancelToken()
    token.track_socket(a)
    outcome: dict = {}

    def blocked_reader():
        try:
            outcome["data"] = a.recv(1)
        except OSError as exc:
            outcome["error"] = exc

    t = threading.Thread(target=blocked_reader)
    t.start()
    time.sleep(0.05)
    assert t.is_alive()
    token.cancel()
    t.join(timeout=2)
    assert not t.is_alive()
    assert outcome.get("data") == b"" or "error" in outcome
    b.close()


def test_track_socket_after_cancel_closes_immediately():
    a, b = socket.socketpair()
    token = CancelToken()
    token.cancel()
    token.track_socket(a)
    with pytest.raises(OSError):
        a.send(b"x")
    b.close()


def test_cancellable_io_converts_io_error_only_when_cancelled():
    token = CancelToken()
    with cancellation.bind(token):
        # 취소되지 않았으면 I/O 예외는 그대로다(진짜 장애는 장애로 남는다).
        with pytest.raises(ConnectionResetError):
            with cancellation.cancellable_io():
                raise ConnectionResetError("peer")
        token.cancel()
        with pytest.raises(OperationCancelled):
            with cancellation.cancellable_io():
                raise ConnectionResetError("closed by cancel")
        with pytest.raises(OperationCancelled):
            with cancellation.cancellable_io():
                raise urllib.error.URLError("closed by cancel")


# ─── LLM 호출 관문(_ollama_open_with_retry / _ollama_ensure_warm) ────────────────


def test_open_with_retry_refuses_new_call_when_cancelled(monkeypatch):
    """취소된 요청은 새 LLM 호출을 열지 않는다 — urlopen 호출 0회."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    token = CancelToken()
    token.cancel()
    with cancellation.bind(token):
        with pytest.raises(OperationCancelled):
            _ollama_open_with_retry(object(), timeout=120)
    assert calls["n"] == 0


def test_open_with_retry_reports_cancel_instead_of_retrying(monkeypatch):
    """진행 중 호출을 취소가 끊으면(URLError) 콜드스타트 재시도가 아니라 취소로 끝난다."""
    calls = {"n": 0}
    token = CancelToken()

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        token.cancel()  # 호출 도중 클라이언트가 끊김 → 소켓 닫힘
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)
    monkeypatch.setattr(nl_parser, "is_local_ollama", lambda: False)
    with cancellation.bind(token):
        with pytest.raises(OperationCancelled):
            _ollama_open_with_retry(object(), timeout=120)
    assert calls["n"] == 1


def test_open_with_retry_unaffected_without_token(monkeypatch):
    """토큰이 없는 호출(비요청 경로·다른 엔드포인트)은 종전 재시도 동작 그대로다."""
    calls = {"n": 0}
    ok = object()

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.URLError("cold")
        return ok

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)
    monkeypatch.setattr(nl_parser, "is_local_ollama", lambda: False)
    assert _ollama_open_with_retry(object(), timeout=120) is ok
    assert calls["n"] == 2


def test_warmup_refuses_when_cancelled(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    token = CancelToken()
    token.cancel()
    with cancellation.bind(token):
        with pytest.raises(OperationCancelled):
            _ollama_ensure_warm(budget_s=30)
    assert calls["n"] == 0


# ─── 실제 소켓: 응답을 기다리는 urlopen을 취소가 끊는다 ──────────────────────────


class _HangingHandler(http.server.BaseHTTPRequestHandler):
    """응답을 release 이벤트까지 보류한다 — 생성 중인 Ollama 흉내(stream:false는 헤더도 늦다)."""

    release = threading.Event()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.release.wait(10)
        try:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")
        except OSError:
            pass

    def log_message(self, *args):  # noqa: D401 — 테스트 출력 억제
        return


@pytest.fixture
def hanging_server():
    _HangingHandler.release.clear()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HangingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        _HangingHandler.release.set()
        server.shutdown()
        server.server_close()


def test_cancel_interrupts_inflight_llm_http_call(hanging_server, monkeypatch):
    """[핵심] 응답을 기다리는 진행 중 LLM 호출을 취소가 소켓을 닫아 즉시 끝낸다.

    urllib 전역 opener가 소켓을 토큰에 등록하므로(install_socket_tracking) 서버가 응답을
    보류해도 cancel()이 recv를 깨우고, 관문은 그 실패를 취소로 보고한다."""
    cancellation.install_socket_tracking()
    monkeypatch.setattr(nl_parser, "is_local_ollama", lambda: False)
    token = CancelToken()
    outcome: dict = {}

    def worker():
        with cancellation.bind(token):
            req = urllib.request.Request(
                f"{hanging_server}/api/chat", data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST",
            )
            started = time.monotonic()
            try:
                _ollama_open_with_retry(req, timeout=30)
                outcome["result"] = "returned"
            except OperationCancelled:
                outcome["result"] = "cancelled"
            except Exception as exc:  # noqa: BLE001
                outcome["result"] = f"error:{exc!r}"
            outcome["elapsed"] = time.monotonic() - started

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.3)  # 워커가 서버 응답 대기에 들어갈 시간
    assert t.is_alive(), "워커가 응답 대기 전에 끝났다"
    token.cancel()
    t.join(timeout=5)
    assert not t.is_alive(), "취소 뒤에도 워커가 응답을 기다린다"
    assert outcome["result"] == "cancelled"
    assert outcome["elapsed"] < 5


def test_untracked_context_socket_is_not_closed(hanging_server):
    """토큰이 없는 컨텍스트의 urlopen은 추적되지 않는다 — 다른 요청의 소켓을 건드리지 않는다."""
    cancellation.install_socket_tracking()
    token = CancelToken()
    outcome: dict = {}

    def worker():
        req = urllib.request.Request(
            f"{hanging_server}/api/chat", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                outcome["result"] = resp.read()
        except Exception as exc:  # noqa: BLE001
            outcome["result"] = f"error:{exc!r}"

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.3)
    token.cancel()  # 무관한 토큰 — 워커 소켓은 살아 있어야 한다
    assert t.is_alive()
    _HangingHandler.release.set()
    t.join(timeout=5)
    assert outcome["result"] == b"{}"


# ─── SSE 스트림 결속: 정상 종료 전에 닫히면 토큰 취소 ───────────────────────────
# Starlette(ASGI 2.3 경로)는 클라이언트가 끊기면 스트림 태스크를 취소한다 — 제너레이터가
# `await asyncio.sleep`에서 CancelledError를 받고 finally를 거친다. 그 경로를 그대로 흉내낸다.


def _cancelling_worker_stub(state: dict):
    """LLM 호출 흉내 — 관문처럼 토큰을 확인하며 대기하고, 취소되면 OperationCancelled."""

    def stub(*args, **kwargs):  # noqa: ARG001
        state["running"] = True
        for _ in range(500):
            if cancellation.is_cancelled():
                state["cancelled"] = True
                raise OperationCancelled()
            time.sleep(0.01)
        raise AssertionError("취소되지 않고 끝까지 돌았다")

    return stub


def _run_disconnect_scenario(make_response, state: dict) -> None:
    async def scenario():
        response = await make_response()

        async def consume():
            async for _ in response.body_iterator:
                pass

        task = asyncio.create_task(consume())
        deadline = time.monotonic() + 3
        while not state["running"] and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert state["running"], "워커 스레드가 시작되지 않았다"
        # 클라이언트 연결 종료 — Starlette가 스트림 태스크를 취소한다.
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        deadline = time.monotonic() + 3
        while not state["cancelled"] and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert state["cancelled"], "연결 종료 뒤에도 워커 스레드가 취소되지 않았다"

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(scenario())
    finally:
        loop.close()


def test_parse_stream_cancels_worker_when_client_disconnects(monkeypatch):
    """/strategy/parse-stream: 클라이언트가 스트림을 끊으면 파싱 스레드의 토큰이 취소돼
    LLM 관문에서 멈춘다."""
    import main

    state = {"running": False, "cancelled": False}
    monkeypatch.setattr(main, "_run_nl_parse", _cancelling_worker_stub(state))
    _run_disconnect_scenario(
        lambda: main.parse_nl_strategy_stream(
            main.NLParseRequest(prompt="테스트", backend="ollama")
        ),
        state,
    )


def test_builder_step_stream_cancels_worker_when_client_disconnects(monkeypatch):
    """/strategy/builder/step-stream: 같은 결속 — 스트림 조기 종료 시 스텝 스레드 토큰 취소."""
    from api import intent_routes

    state = {"running": False, "cancelled": False}
    monkeypatch.setattr(intent_routes, "_run_builder_step", _cancelling_worker_stub(state))
    _run_disconnect_scenario(
        lambda: intent_routes.strategy_builder_step_stream(
            intent_routes.BuilderStepRequest(state={"universe": "KOSPI"}, input="10개")
        ),
        state,
    )


def test_parse_stream_does_not_cancel_on_normal_completion(monkeypatch):
    """정상 종료([DONE])는 토큰을 취소하지 않는다 — 후행 검증 등 종전 동작 유지."""
    import main

    tokens: dict = {}

    def fake_parse(request, on_stage=None, defer_holder=None):  # noqa: ARG001
        tokens["token"] = cancellation.current()
        return {"parsed": {}}

    monkeypatch.setattr(main, "_run_nl_parse", fake_parse)
    loop = asyncio.new_event_loop()
    try:
        response = loop.run_until_complete(
            main.parse_nl_strategy_stream(main.NLParseRequest(prompt="테스트", backend="ollama"))
        )
        chunks = []

        async def drain():
            async for chunk in response.body_iterator:
                chunks.append(chunk)

        loop.run_until_complete(drain())
    finally:
        loop.close()
    assert any("[DONE]" in c for c in chunks)
    assert tokens["token"] is not None
    assert tokens["token"].cancelled is False


def test_parse_cache_skips_cancelled_request():
    """취소된 요청의 결과는 캐시에 남지 않는다(폴백 저품질 결과가 다음 대화로 새지 않게)."""
    import main

    key = ("cancel-test", "ollama", None)
    main._nl_parse_cache.pop(key, None)
    token = CancelToken()
    token.cancel()
    try:
        with cancellation.bind(token):
            main._store_nl_parse_cache(key, {"parsed": {}})
        assert key not in main._nl_parse_cache
        main._store_nl_parse_cache(key, {"parsed": {}})
        assert key in main._nl_parse_cache
    finally:
        main._nl_parse_cache.pop(key, None)
