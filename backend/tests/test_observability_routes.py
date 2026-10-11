"""운영 콘솔 실패 분류 엔드포인트(GET /admin/trace-triage) 회귀."""

from __future__ import annotations

import datetime as dt
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.observability_routes import router
from observability.retention import RETENTION_DAYS


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _record(total_ms):
    return {"trace_id": "t1", "ts": "2026-10-11T10:00:00", "root": "NullStock Strategy Agent",
            "total_ms": total_ms, "span": {"name": "NullStock Strategy Agent",
                                           "inputs": {"user_input": "표본"}, "outputs": {}}}


def test_returns_groups_from_trace_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))
    today = dt.date.today().isoformat()
    (tmp_path / f"{today}.jsonl").write_text(json.dumps(_record(200_000)) + "\n", encoding="utf-8")
    body = _client().get("/admin/trace-triage?days=1").json()
    assert body["range"] == [today, today] and body["total"] == 1
    assert body["retention_days"] == RETENTION_DAYS and body["tiers"][0] == "결함 후보"
    group = body["groups"][0]
    assert group["signal"] == "slow_turn" and group["samples"][0]["user_input"] == "표본"


def test_empty_dir_and_day_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path / "none"))
    client = _client()
    assert client.get("/admin/trace-triage").json()["groups"] == []
    assert client.get("/admin/trace-triage?days=0").status_code == 422
    assert client.get(f"/admin/trace-triage?days={RETENTION_DAYS + 1}").status_code == 422
