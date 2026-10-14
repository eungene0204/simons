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


def _sector_interpreter(text, state):
    """KR 해석은 LLM 인터프리터가 낸 연산으로 상태를 채운다 — 정본에 없는 업종 용어는 짧은 문자열로
    resolver(검색 그라운딩·지식그래프 조회)에 넘어간다."""
    return {"sector_unresolved": True, "sector_hint": "원자로 관련주"}, []


def _events(body: str) -> list[dict]:
    out = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                out.append(json.loads(line[6:]))
    return out


def test_step_stream_returns_result_event(monkeypatch):
    monkeypatch.setattr(
        intent_routes, "_builder_llm_helpers",
        lambda on_search=None, on_kg_lookup=None: (None, None, lambda text, state: ({"universe": "KOSPI"}, [])),
    )
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


def test_step_seed_recognized_false_for_open_pick_seed():
    """진짜 열린 추천 발화는 시드 이해가 없다 — 안내문이 그대로 나가야 한다."""
    res = _client().post(
        "/strategy/builder/step",
        json={"state": {}, "input": "", "seed": "어떤 전략이 제일 좋아?"},
    )
    assert res.status_code == 200
    assert res.json()["seed_recognized"] is False


def test_step_stream_emits_searching_stage_before_result(monkeypatch):
    """업종 되묻기 답이 검색 그라운딩에 진입하면 result 전에 searching stage가 흐른다."""

    def fake_helpers(on_search=None, on_kg_lookup=None):
        def sector_resolver(text):
            if on_search is not None:
                on_search()
            time.sleep(0.25)  # 폴링(0.1s) 주기가 stage 전환을 확실히 관측하도록
            return None

        return None, sector_resolver, _sector_interpreter

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

        return None, sector_resolver, _sector_interpreter

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


def test_step_stream_emits_retrying_stage_during_llm_retry(monkeypatch):
    """LLM 호출 재시도 구간(llm_progress.retrying)이 result 전에 retrying stage('재확인 중...')로
    흐르고, 재시도가 끝나면 이전 단계로 되돌아간다(사용자 지시 2026-09-08)."""
    import llm_progress

    def fake_helpers(on_search=None, on_kg_lookup=None):
        def sector_resolver(text):
            if on_kg_lookup is not None:
                on_kg_lookup()
            time.sleep(0.25)
            with llm_progress.retrying():  # 전송 계층이 재시도에 들어간 상황
                time.sleep(0.25)
            time.sleep(0.25)
            return None

        return None, sector_resolver, _sector_interpreter

    monkeypatch.setattr(intent_routes, "_builder_llm_helpers", fake_helpers)
    with _client().stream(
        "POST", "/strategy/builder/step-stream",
        json={"state": {}, "input": "", "seed": "원자로 관련주 전략 만들어줘"},
    ) as r:
        body = "".join(r.iter_text())
    types = [(e["type"], e.get("stage")) for e in _events(body)]
    assert ("stage", "retrying") in types
    result_idx = types.index(next(t for t in types if t[0] == "result"))
    retry_idx = types.index(("stage", "retrying"))
    assert retry_idx < result_idx
    # 재시도가 끝나면 이전 단계(kg_lookup)로 되돌아간 이벤트가 다시 흐른다
    assert ("stage", "kg_lookup") in types[retry_idx + 1:result_idx]
