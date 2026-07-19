"""Modal 콜드스타트 내성 회귀 테스트.

Modal scale-to-zero 컨테이너를 깨우는 첫 코치 요청의 두 가지 실패 패턴:
  A) HTTP 4xx/5xx 즉시 반환 → 재시도로 해결
  B) 연결 hold(hang) ~90s → 단일 long timeout(110s)으로 기다려 해결
     (재시도 시 여러 번 짧게 hang → 예산 소진 → cold-start 완료 전 포기)

수정: _ollama_open_with_retry
  - HTTP 4xx/5xx·URLError → 재시도
  - TimeoutError/OSError → 재시도 않고 즉시 raise (hang 상황 전용 단일 대기)
  - 로컬 엔드포인트의 연결 실패 → 즉시 raise (콜드스타트 없음 — 서버 다운이므로
    재시도 대신 503 친화 메시지로 빠르게 안내)
"""

import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import engine.nl_parser as nl_parser
from engine.nl_parser import _ollama_ensure_warm, _ollama_open_with_retry


class _FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b""


def _http_503():
    return urllib.error.HTTPError(
        url="http://x/api/chat", code=503, msg="Service Unavailable", hdrs=None, fp=None
    )


def _http_400(body: bytes = b""):
    import io

    return urllib.error.HTTPError(
        url="http://x/api/chat", code=400, msg="Bad Request", hdrs=None, fp=io.BytesIO(body)
    )


def test_warmup_returns_when_tags_ok(monkeypatch):
    """본문 없는 GET /api/tags가 바로 200이면 warmup이 한 번만 호출하고 끝난다."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)

    _ollama_ensure_warm(budget_s=30)
    assert calls["n"] == 1


def test_warmup_retries_until_container_up(monkeypatch):
    """[원격] 콜드 컨테이너가 깰 때까지(URLError) GET을 재시도하고, 200을 받으면 반환한다."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("connection refused")
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)
    monkeypatch.setattr(nl_parser, "is_local_ollama", lambda: False)

    _ollama_ensure_warm(budget_s=30)
    assert calls["n"] == 3


def test_warmup_local_connection_refused_fails_fast(monkeypatch):
    """[로컬] 연결 거부는 콜드스타트가 아니라 서버 다운 — 재시도 없이 즉시 raise.

    회귀(2026-07-16): 로컬 Ollama가 꺼진 채 파싱 요청 → warmup이 200s 동안 재시도
    → 프록시 120s 타임아웃으로 사용자에게 timeout 오류. 503 친화 메시지로 빠르게
    안내되도록 즉시 raise해야 한다.
    """
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)
    monkeypatch.setattr(nl_parser, "is_local_ollama", lambda: True)

    with pytest.raises(urllib.error.URLError):
        _ollama_ensure_warm(budget_s=30)
    assert calls["n"] == 1


def test_retry_local_connection_refused_fails_fast(monkeypatch):
    """[로컬] POST 재시도 루프도 연결 거부를 즉시 raise한다(320s 재시도 예산 미적용)."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        raise urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)
    monkeypatch.setattr(nl_parser, "is_local_ollama", lambda: True)

    with pytest.raises(urllib.error.URLError):
        _ollama_open_with_retry(object(), timeout=120)
    assert calls["n"] == 1


def test_retry_recovers_from_cold_start_503(monkeypatch):
    """콜드스타트 503 한 번 뒤 모델이 뜨면(200) 재시도가 성공을 돌려준다."""
    calls = {"n": 0}
    ok = _FakeResp()

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_503()
        return ok

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)

    assert _ollama_open_with_retry(object(), timeout=120) is ok
    assert calls["n"] == 2


def test_retry_recovers_from_cold_start_400(monkeypatch):
    """Modal 콜드스타트 중 모델 로딩 전 반환되는 HTTP 400은 일시 오류 → 재시도로 성공한다.

    프로덕션 실측: 콜드스타트 ~60s 로딩 구간에 400이 나고, 모델이 뜨면 같은 요청이 200을 준다.
    """
    calls = {"n": 0}
    ok = _FakeResp()

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_400(b"")  # 본문 없는 콜드스타트 프록시 400
        return ok

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)

    assert _ollama_open_with_retry(object(), timeout=120) is ok
    assert calls["n"] == 2


def test_no_retry_on_permanent_400_model_required(monkeypatch):
    """설정 오류로 인한 영구 400(모델명 누락)은 재시도하지 않고 즉시 올린다."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        raise _http_400(b'{"error":"model is required"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)

    with pytest.raises(urllib.error.HTTPError):
        _ollama_open_with_retry(object(), timeout=120)
    assert calls["n"] == 1  # 재시도 없이 1번만


def test_no_retry_on_permanent_error(monkeypatch):
    """transient가 아닌 상태코드(404)는 재시도하지 않고 즉시 올린다."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        raise urllib.error.HTTPError("http://x", 404, "Not Found", None, None)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)

    with pytest.raises(urllib.error.HTTPError):
        _ollama_open_with_retry(object(), timeout=120)
    assert calls["n"] == 1


def test_timeout_raises_immediately_no_retry(monkeypatch):
    """cold-start hang(TimeoutError)은 재시도하지 않고 즉시 raise — 재시도가 역효과이기 때문."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        raise TimeoutError("read timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)

    with pytest.raises(TimeoutError):
        _ollama_open_with_retry(object(), timeout=120)
    assert calls["n"] == 1  # 재시도 없이 1번만


def test_gives_up_after_budget(monkeypatch):
    """모델이 끝내 안 뜨면(503 계속) 예산 소진 후 마지막 예외를 올린다."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        raise _http_503()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)
    monkeypatch.setattr(nl_parser, "_OLLAMA_RETRY_BUDGET_S", 0.05)

    with pytest.raises(urllib.error.HTTPError):
        _ollama_open_with_retry(object(), timeout=120)
    assert calls["n"] >= 1
