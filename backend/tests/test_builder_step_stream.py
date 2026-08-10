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


def test_step_seed_recognized_true_for_concrete_strategy_seed():
    """[2026-08-10 사용자 지시] 시드 발화가 전략으로 이해되면 seed_recognized=True.

    프론트가 열린 추천 안내문(STRATEGY_PICK)과 빌더 ack("…로 이해했어요") 중
    **하나만** 보이기 위한 근거 — 분류가 열린 추천으로 오판해도 빌더가 이해했으면
    안내문을 생략한다(실측: '상대 모멘텀 효과를 이용한 투자 전략'에 둘 다 나감)."""
    res = _client().post(
        "/strategy/builder/step",
        json={"state": {}, "input": "", "seed": "상대 모멘텀 효과를 이용한 투자 전략"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["state"]["strategy_type"] == "momentum"
    assert data["seed_recognized"] is True


def test_step_seed_recognized_true_for_universe_only_seed():
    """[2026-08-11] 유니버스만 이해한 시드도 seed_recognized=True.

    ack 요약(_seed_summary)에는 유니버스가 없지만(첫 질문 생략으로 드러난다),
    대상 시장을 이해했는데 '추천해 드리지는 않지만' 안내문이 나가는 것은 모순이다."""
    res = _client().post(
        "/strategy/builder/step",
        json={"state": {}, "input": "", "seed": "코스피 대상으로 투자 전략 만들어줘"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["state"]["universe"] == "KOSPI"
    assert data["seed_recognized"] is True


def test_step_seed_recognized_false_for_open_pick_seed():
    """진짜 열린 추천 발화는 시드 이해가 없다 — 안내문이 그대로 나가야 한다."""
    res = _client().post(
        "/strategy/builder/step",
        json={"state": {}, "input": "", "seed": "어떤 전략이 제일 좋아?"},
    )
    assert res.status_code == 200
    assert res.json()["seed_recognized"] is False


def test_step_seed_recognized_false_on_followup_turn():
    """시드 턴이 아니면(상태가 이미 있음) 플래그를 싣지 않는다 — 첫 턴 전용 신호."""
    res = _client().post(
        "/strategy/builder/step",
        json={"state": {"strategy_type": "momentum"}, "input": "코스피",
              "seed": "상대 모멘텀 효과를 이용한 투자 전략"},
    )
    assert res.status_code == 200
    assert res.json()["seed_recognized"] is False


def test_step_stream_seed_recognized_flag():
    """SSE 라우트도 JSON 라우트와 같은 seed_recognized 계약을 싣는다."""
    with _client().stream(
        "POST", "/strategy/builder/step-stream",
        json={"state": {}, "input": "", "seed": "상대 모멘텀 효과를 이용한 투자 전략"},
    ) as r:
        body = "".join(r.iter_text())
    result = next(e for e in _events(body) if e["type"] == "result")
    assert result["data"]["seed_recognized"] is True


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
