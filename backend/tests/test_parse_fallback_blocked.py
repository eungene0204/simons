"""초기 파스 정규식 폴백 차단 (계약 § 8 · 로드맵 1c, 2026-07-26).

원칙: "폴백은 자연어 재해석이 아니라 실패 보고여야 한다."
- primary 모드에서 인터프리터가 해석하지 못하면(None) 규칙 파서(_parse_rule_based_strategy,
  원문 정규식)로 재해석하지 않고 실패 보고(interpretation_failed 되묻기)로 끝낸다.
- LLM 서버 연결 장애는 None으로 삼키지 않고 그대로 던져 main의 503 경로가 처리한다
  (인프라 장애가 "입력을 바꿔라"로 위장되는 것 방지).
- primary가 꺼진 환경(off/shadow)에서는 규칙 하이브리드가 기본 경로로 그대로 동작한다
  (폴백이 아니라 primary — 1d 이관 전까지 유지).
"""

import pytest

import main
from main import NLParseRequest, _run_nl_parse
from strategy_conversation import primary
from strategy_conversation.interpreter.llm_strategy_interpreter import InterpreterError


@pytest.fixture(autouse=True)
def _clean_cache():
    # _nl_parsers도 비운다 — 다른 테스트 모듈이 남긴 더미 파서가 재사용되면
    # 클래스 레벨 monkeypatch가 적용되지 않아 순서 의존 실패가 난다.
    main._nl_parse_cache.clear()
    main._nl_parsers.clear()
    yield
    main._nl_parse_cache.clear()
    main._nl_parsers.clear()


def test_primary_parse_failure_reports_instead_of_rule_parser(monkeypatch):
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "primary")
    monkeypatch.setattr(primary, "run_primary_parse", lambda *a, **k: None)

    called = {"rule": False}
    from engine.nl_parser import NLStrategyParser

    original_parse = NLStrategyParser.parse

    def _spy_parse(self, *a, **k):
        called["rule"] = True
        return original_parse(self, *a, **k)

    monkeypatch.setattr(NLStrategyParser, "parse", _spy_parse)

    result = _run_nl_parse(NLParseRequest(prompt="골든크로스 매수 전략"))

    assert called["rule"] is False, "인터프리터 실패가 규칙 파서 재해석으로 폴백되면 안 된다"
    assert result["clarification_priority"] == "interpretation_failed"
    assert result["parsed"]["description"] == "골든크로스 매수 전략"


def test_primary_off_keeps_rule_hybrid_as_primary(monkeypatch):
    """off/shadow 환경의 규칙 하이브리드는 폴백이 아니라 기본 경로 — 차단 대상이 아니다."""
    monkeypatch.setenv("STRATEGY_INTERPRETER_MODE", "off")

    from engine.nl_parser import NLStrategyParser, ParsedStrategy

    sentinel = ParsedStrategy(description="규칙 경로 결과")
    monkeypatch.setattr(NLStrategyParser, "parse", lambda self, *a, **k: sentinel)

    result = _run_nl_parse(NLParseRequest(prompt="골든크로스 매수 전략"))
    assert result["parsed"]["description"] == "규칙 경로 결과"


def test_run_primary_parse_returns_none_on_interpreter_error(monkeypatch):
    class _Interpreter:
        def interpret(self, *_a, **_k):
            raise InterpreterError("재생성까지 실패")

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())
    assert primary.run_primary_parse("골든크로스 매수 전략") is None


def test_run_primary_parse_propagates_transport_errors(monkeypatch):
    """연결 장애는 실패 보고(되묻기)로 위장되지 않고 그대로 던져진다(503 경로 소관)."""

    class _Interpreter:
        def interpret(self, *_a, **_k):
            raise OSError("connection refused")

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())
    with pytest.raises(OSError):
        primary.run_primary_parse("골든크로스 매수 전략")


def test_regex_fallback_builder_removed():
    """원문 정규식 폴백 함수 자체가 제거됐다(1c) — 부활 방지 가드."""
    import engine.nl_parser as nl

    assert not hasattr(nl, "_build_fallback_strategy")
