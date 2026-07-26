"""빌더 step-stream SSE 라우트(FR-STR-069 '검색 중...' 진행 표시) 검증.

계약:
  - 결과는 {"type":"result","data":StepResult} 단일 이벤트 + [DONE] (기존 POST와 동일 데이터).
  - 개념 해석 체인(지식그래프 조회 포함) 진입 시 {"type":"stage","stage":"kg_lookup"}가 흐른다.
  - 용어 그라운딩이 인터넷 검색에 진입하면 결과 전에 {"type":"stage","stage":"searching"}가 흐른다.
  - 예외는 {"type":"error"} 이벤트로 전달된다(스트림 200 유지).
"""

from __future__ import annotations

import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import intent_routes


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(intent_routes.router)
    return TestClient(app)


def _events(body: str) -> list[dict]:
    out = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                out.append(json.loads(line[6:]))
    return out


def test_step_stream_returns_result_event():
    with _client().stream(
        "POST", "/strategy/builder/step-stream",
        json={"state": {}, "input": "", "seed": "코스피 저PBR 전략"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert "data: [DONE]" in body
    events = _events(body)
    result = next(e for e in events if e["type"] == "result")
    # 기존 POST /strategy/builder/step과 동일한 StepResult 계약(시드가 유니버스를 채움)
    assert result["data"]["state"]["universe"] == "KOSPI"
    assert result["data"]["status"] in ("collecting", "confirmed")


def test_step_stream_emits_searching_stage_before_result(monkeypatch):
    """업종 되묻기 답이 검색 그라운딩에 진입하면 result 전에 searching stage가 흐른다."""

    def fake_helpers(on_search=None, on_kg_lookup=None):
        def sector_resolver(text):
            if on_search is not None:
                on_search()
            time.sleep(0.25)  # 폴링(0.1s) 주기가 stage 전환을 확실히 관측하도록
            return None

        return None, sector_resolver, None

    monkeypatch.setattr(intent_routes, "_builder_llm_helpers", fake_helpers)
    # '원자로 관련주' — 결정적 섹터 어휘 밖이라 sector_unresolved로 resolver가 호출된다
    with _client().stream(
        "POST", "/strategy/builder/step-stream",
        json={"state": {}, "input": "", "seed": "원자로 관련주 전략 만들어줘"},
    ) as r:
        body = "".join(r.iter_text())
    events = _events(body)
    types = [(e["type"], e.get("stage")) for e in events]
    assert ("stage", "searching") in types
    assert types.index(("stage", "searching")) < types.index(
        next(t for t in types if t[0] == "result")
    )


def test_step_stream_emits_kg_lookup_stage_before_result(monkeypatch):
    """개념 해석 체인 진입('개념 확인 중...' 표시 신호)이 result 전에 kg_lookup stage로 흐른다."""

    def fake_helpers(on_search=None, on_kg_lookup=None):
        def sector_resolver(text):
            if on_kg_lookup is not None:
                on_kg_lookup()
            time.sleep(0.25)  # 폴링(0.1s) 주기가 stage 전환을 확실히 관측하도록
            return None

        return None, sector_resolver, None

    monkeypatch.setattr(intent_routes, "_builder_llm_helpers", fake_helpers)
    with _client().stream(
        "POST", "/strategy/builder/step-stream",
        json={"state": {}, "input": "", "seed": "원자로 관련주 전략 만들어줘"},
    ) as r:
        body = "".join(r.iter_text())
    events = _events(body)
    types = [(e["type"], e.get("stage")) for e in events]
    assert ("stage", "kg_lookup") in types
    assert types.index(("stage", "kg_lookup")) < types.index(
        next(t for t in types if t[0] == "result")
    )


def test_step_stream_reports_error_event(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("빌더 내부 오류")

    monkeypatch.setattr(intent_routes, "_run_builder_step", boom)
    with _client().stream(
        "POST", "/strategy/builder/step-stream", json={"state": {}, "input": "네"},
    ) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    events = _events(body)
    assert any(e["type"] == "error" and "빌더 내부 오류" in e["detail"] for e in events)
