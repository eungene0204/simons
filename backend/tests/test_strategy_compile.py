"""'전략 확정' 컴파일 라우트(/strategy/compile) — 재해석 없이 누적 전략을 그대로 컴파일한다.

결정적 조건 플로우의 확정이 대화 전체를 LLM에 재파싱시키던 시절, 규칙 파서가 표현 못 하는
조건('영업이익 흑자' → operating_income_growth 필터)을 LLM이 비결정적으로 떨어뜨려 완성
전략의 매수 조건이 사라진 채 다시 되묻는 사고가 있었다. 이 라우트는 누적 parsed를 진실로
삼아 컴파일만 수행해야 한다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.intent_routes import router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _confirmed_parsed():
    # LLM 해석으로만 얻을 수 있는 진입 필터('영업이익 흑자' → 영업이익증가율 ≥ 0)를 포함한
    # 완성 전략 — 규칙 파서 재해석으로는 재현 불가하므로 그대로 보존돼야 한다.
    return {
        "description": "영업이익 흑자인 기업 투자 전략",
        "universe": ["KOSPI"],
        "fundamental_filters": [
            {"metric": "operating_income_growth", "operator": ">=", "value": 0.0}
        ],
        "entry_signals": [],
        "exit_signals": [
            {"indicator": "rsi", "signal_type": "sell", "operator": ">=", "value": 70}
        ],
        "max_positions": 10,
        "rebalancing_period": "monthly",
        "stop_loss_pct": 15.0,
        "take_profit_pct": 30.0,
        "backtest_period": "5y",
        "initial_capital": 10_000_000,
    }


def test_compile_preserves_llm_only_entry_filter(client):
    res = client.post("/strategy/compile", json={"parsed": _confirmed_parsed()})
    assert res.status_code == 200
    body = res.json()

    filters = body["parsed"]["fundamental_filters"]
    assert len(filters) == 1
    assert filters[0]["metric"] == "operating_income_growth"
    assert filters[0]["operator"] == ">="

    # 백테스트 요청에도 진입(필터) 조건이 그대로 반영된다.
    entry_conditions = body["backtest_request"]["entry"]["conditions"]
    assert any(c.get("id") == "operating_income_growth" for c in entry_conditions)


def test_compile_keeps_confirmed_settings(client):
    res = client.post("/strategy/compile", json={"parsed": _confirmed_parsed()})
    assert res.status_code == 200
    parsed = res.json()["parsed"]
    assert parsed["stop_loss_pct"] == 15.0
    assert parsed["take_profit_pct"] == 30.0
    assert parsed["max_positions"] == 10
    assert parsed["rebalancing_period"] == "monthly"
    assert parsed["initial_capital"] == 10_000_000


def test_compile_applies_minimum_guards(client):
    payload = _confirmed_parsed()
    payload["initial_capital"] = 300  # 하한선 아래 — 공통 방어 보정이 clamp + 안내
    res = client.post("/strategy/compile", json={"parsed": payload})
    assert res.status_code == 200
    body = res.json()
    assert body["parsed"]["initial_capital"] > 300
    assert body["notices"]


def test_compile_invalid_parsed_422(client):
    res = client.post(
        "/strategy/compile",
        json={"parsed": {"exit_signals": [{"indicator": "no_such_indicator"}]}},
    )
    assert res.status_code == 422
