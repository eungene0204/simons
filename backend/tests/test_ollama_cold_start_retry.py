"""Modal 콜드스타트 내성 회귀 테스트.

버그: Ollama를 Modal serverless GPU(scale-to-zero)에 띄우면, 잠든 컨테이너를 깨우는
첫 코치 요청이 모델 로딩(~60s) 중 프록시 HTTP 400을 받고 그대로 실패한다 →
프로덕션에서 "코칭을 못 받음". 재시도가 없어 콜드스타트 한 번에 코칭이 죽었다.

수정: _ollama_open_with_retry 가 transient 실패(콜드스타트 400/5xx/타임아웃)를
예산 안에서 재시도한다.
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


def _http_400():
    return urllib.error.HTTPError(
        url="http://x/api/chat", code=400, msg="Bad Request", hdrs=None, fp=None
    )


def test_retry_recovers_from_cold_start_400(monkeypatch):
    """콜드스타트 400 한 번 뒤 모델이 뜨면(200) 재시도가 성공을 돌려준다."""
    calls = {"n": 0}
    ok = _FakeResp()

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_400()  # 콜드스타트: 모델 로딩 중
        return ok  # 컨테이너 warm → 성공

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)  # 테스트 빠르게

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


def test_gives_up_after_budget(monkeypatch):
    """모델이 끝내 안 뜨면 예산 소진 후 마지막 예외를 올린다(무한 재시도 금지)."""
    calls = {"n": 0}

    def fake_urlopen(req, timeout):  # noqa: ARG001
        calls["n"] += 1
        raise _http_400()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(nl_parser.time, "sleep", lambda s: None)
    # 예산을 짧게 줄여 빠르게 소진
    monkeypatch.setattr(nl_parser, "_OLLAMA_RETRY_BUDGET_S", 0.05)

    with pytest.raises(urllib.error.HTTPError):
        _ollama_open_with_retry(object(), timeout=120)
    assert calls["n"] >= 1
