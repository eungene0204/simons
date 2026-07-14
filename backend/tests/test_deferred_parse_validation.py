"""비차단(후행) LLM 검증 경로 테스트 — main._run_nl_parse(defer_holder)와
main._complete_deferred_validation.

SSE 스트림(/strategy/parse-stream)은 룰 파스 결과를 먼저 내보내고 검증 LLM을 후행으로
돌린다(수 초~수십 초 검증 대기가 첫 응답을 막지 않도록). 여기서는 그 2단계 계약을 검증한다:
- defer 모드의 _run_nl_parse가 후행 검증 컨텍스트(defer_holder)를 채우고 즉시 결과를 낸다
- _complete_deferred_validation이 교정 시에만 갱신 payload를 반환하고 캐시를 교정본으로 갱신
- 교정이 없으면 None을 반환하고 캐시의 parse_validation만 채운다
실제 LLM 호출은 하지 않는다(engine.parse_validator._run_validation_llm patch).
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import main
from engine import parse_validator
from main import NLParseRequest, _complete_deferred_validation, _run_nl_parse

# '삼성전자 같은'이 룰 파스가 설명 못 한 잔여 → 검증 대상 파싱.
AMBIGUOUS_PROMPT = "삼성전자 같은 PBR 1 이하 종목 10개 1년 보유"


@pytest.fixture(autouse=True)
def _clean_cache():
    main._nl_parse_cache.clear()
    yield
    main._nl_parse_cache.clear()


def _patch_llm(monkeypatch, response):
    def fake(*_args, **_kwargs):
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(parse_validator, "_run_validation_llm", fake)


def _run_deferred(monkeypatch):
    """defer 모드로 _run_nl_parse를 실행해 (result, defer_holder)를 반환한다."""
    # 인라인 경로에서 검증 LLM이 호출되면 안 된다 — defer 계약 위반을 즉시 드러낸다.
    _patch_llm(monkeypatch, AssertionError("defer 모드에서 인라인 검증이 호출됨"))
    defer_holder: dict = {}
    request = NLParseRequest(prompt=AMBIGUOUS_PROMPT, backend="ollama")
    result = _run_nl_parse(request, defer_holder=defer_holder)
    return result, defer_holder


def test_run_nl_parse_defers_validation_and_fills_holder(monkeypatch):
    result, holder = _run_deferred(monkeypatch)

    assert result["parse_validation"] == {"pending": True}
    assert result["parsed"]["fundamental_filters"]
    assert holder["parsed"] is not None
    assert holder["request"].prompt == AMBIGUOUS_PROMPT
    assert holder["cache_key"] in main._nl_parse_cache


def test_deferred_correction_returns_update_and_refreshes_cache(monkeypatch):
    result, holder = _run_deferred(monkeypatch)
    assert result["parsed"]["sector"] is None

    # 후행 검증: 놓친 업종 제한을 diff로 교정.
    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.9,
        "correctedFields": {"sector": "반도체"},
        "userFacingMessage": "반도체 업종 제한을 반영했습니다.",
    }))

    updated = _complete_deferred_validation(holder)

    assert updated is not None
    assert updated["parsed"]["sector"] == "반도체"
    assert updated["parse_validation"]["correctedStrategy"]["sector"] == "반도체"
    # 캐시도 교정본으로 갱신 — 동일 프롬프트 재요청이 교정 전 결과를 돌려주면 안 된다.
    assert main._nl_parse_cache[holder["cache_key"]]["parsed"]["sector"] == "반도체"


def test_deferred_no_correction_returns_none_and_updates_cache_report(monkeypatch):
    _result, holder = _run_deferred(monkeypatch)

    _patch_llm(monkeypatch, json.dumps({"isValid": True, "confidence": 0.95}))

    updated = _complete_deferred_validation(holder)

    assert updated is None
    cached = main._nl_parse_cache[holder["cache_key"]]
    assert cached["parse_validation"]["isValid"] is True
    assert cached["parse_validation"]["confidence"] == 0.95


def test_deferred_llm_unreachable_returns_none(monkeypatch):
    """후행 검증도 graceful degrade — LLM 미가용이면 갱신 없음(스트림은 조용히 종료)."""
    _result, holder = _run_deferred(monkeypatch)

    _patch_llm(monkeypatch, None)

    assert _complete_deferred_validation(holder) is None
