"""내부 토큰 이중 잠금(internal_auth, NFR-SEC-012) 회귀.

2026-10-11 Next 경로 이탈 사고 — 비로그인 요청이 백엔드의 아무 경로에 닿았다. Next 쪽 가두기와
별개로, 관리자·내부·운영 변경 엔드포인트는 내부 토큰 없이는 404여야 한다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import internal_auth


def _client():
    app = FastAPI()
    app.middleware("http")(internal_auth.middleware)

    @app.get("/admin/trace-triage")
    def triage():
        return {"ok": True}

    @app.post("/market/delist/{symbol}")
    def delist(symbol: str):
        return {"ok": symbol}

    @app.post("/virtual-account/{account_id}/force-liquidate/{symbol}")
    def liquidate(account_id: str, symbol: str):
        return {"ok": account_id}

    @app.post("/strategy/parse")
    def parse():
        return {"ok": True}

    return TestClient(app)


@pytest.mark.parametrize("method,path,protected", [
    ("GET", "/admin/trace-triage", True),
    ("POST", "/admin/clear-cache", True),
    ("POST", "/internal/sync/event", True),
    ("POST", "/sync-stocks", True),
    ("GET", "/market/dart/notices", True),
    ("POST", "/market/delist/005930", True),
    ("DELETE", "/market/delist/005930", True),
    ("GET", "/market/delist/005930", False),
    ("POST", "/market/listing-status/sync", True),
    ("POST", "/virtual-account/7/force-liquidate/005930", True),
    ("POST", "/ai/runtime/metrics/reset", True),
    ("POST", "/v2/news/005930/refresh", True),
    ("POST", "/strategy/parse", False),
    ("GET", "/stock/005930/ohlcv", False),
    ("GET", "/ontology/graph", False),
])
def test_protected_rules(method, path, protected):
    assert internal_auth.is_protected(method, path) is protected


def test_fail_closed_when_token_unset(monkeypatch):
    monkeypatch.delenv(internal_auth.ENV, raising=False)
    client = _client()
    assert client.get("/admin/trace-triage").status_code == 404
    assert client.get("/admin/trace-triage", headers={"X-Internal-Token": ""}).status_code == 404
    assert client.post("/strategy/parse").status_code == 200   # 보호 대상 아님


def test_token_required_and_matched(monkeypatch):
    monkeypatch.setenv(internal_auth.ENV, "s3cret")
    client = _client()
    assert client.get("/admin/trace-triage").status_code == 404
    assert client.get("/admin/trace-triage", headers={"X-Internal-Token": "wrong"}).status_code == 404
    assert client.get("/admin/trace-triage", headers={"X-Internal-Token": "s3cret"}).json() == {"ok": True}
    assert client.post("/market/delist/005930", headers={"X-Internal-Token": "s3cret"}).status_code == 200
    assert client.post("/market/delist/005930").status_code == 404


def test_encoded_question_mark_cannot_slip_past(monkeypatch):
    """디코드된 '?'가 request.url.path를 잘라 판정을 비켜 가던 우회(2026-10-11 검토 실측)."""
    monkeypatch.setenv(internal_auth.ENV, "s3cret")
    client = _client()
    assert client.post("/market/delist/%3Fx").status_code == 404
    assert client.post("/virtual-account/7%3F/force-liquidate/005930").status_code == 404
    assert client.post("/market/delist/%3Fx", headers={"X-Internal-Token": "s3cret"}).status_code == 200
