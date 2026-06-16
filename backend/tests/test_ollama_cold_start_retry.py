"""Modal 콜드스타트 내성 회귀 테스트.

Modal scale-to-zero 컨테이너를 깨우는 첫 코치 요청의 두 가지 실패 패턴:
  A) HTTP 4xx/5xx 즉시 반환 → 재시도로 해결
  B) 연결 hold(hang) ~90s → 단일 long timeout(110s)으로 기다려 해결
     (재시도 시 여러 번 짧게 hang → 예산 소진 → cold-start 완료 전 포기)

수정: _ollama_open_with_retry
  - HTTP 4xx/5xx·URLError → 재시도
  - TimeoutError/OSError → 재시도 않고 즉시 raise (hang 상황 전용 단일 대기)
"""

import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import engine.nl_parser as nl_parser
from engine.nl_parser import _ollama_open_with_retry


class _FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_503():
    return urllib.error.HTTPError(
        url="http://x/api/chat", code=503, msg="Service Unavailable", hdrs=None, fp=None
    )


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
