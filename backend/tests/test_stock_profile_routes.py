"""단일 종목 연구 프로파일 API 계약 (FR-STR-068b)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.stock_profile_routes import router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_invalid_symbol_404(client):
    assert client.get("/stock/../research-profile").status_code == 404
    assert client.get("/stock/abc/research-profile").status_code == 404


def test_missing_data_404(client, monkeypatch):
    import engine.stock_profile as sp
    monkeypatch.setattr(sp, "get_stock_profile", lambda symbol: None)
    res = client.get("/stock/999999/research-profile")
    assert res.status_code == 404
    assert "데이터가 없어" in res.json()["detail"]


def test_profile_payload_contract(client, monkeypatch):
    import engine.stock_profile as sp
    from tests.test_stock_profile import _profile_with

    monkeypatch.setattr(sp, "get_stock_profile", lambda symbol: _profile_with())
    res = client.get("/stock/999990/research-profile")
    assert res.status_code == 200
    body = res.json()
    assert body["stock"]["symbol"] == "999990"
    assert body["profile_summary"]["data_period"]
    assert body["recommended_questions"] and body["excluded_questions"]
    # 기본 모드에서는 재무(고급) 질문이 노출되지 않는다.
    assert all(not q["advanced"] for q in body["recommended_questions"])

    res_adv = client.get("/stock/999990/research-profile?include_advanced=true")
    adv_ids = {q["question_id"] for q in res_adv.json()["recommended_questions"]}
    assert "historical_pbr_entry" in adv_ids
