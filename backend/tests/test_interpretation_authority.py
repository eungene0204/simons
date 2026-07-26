"""해석 파이프라인의 권한 계약 테스트.

헌법: **해석 파이프라인의 어떤 레이어도 요청을 실패시킬 권한이 없다.** 레이어의 반환값은
"처리했음" 또는 "내 소관 아님(다음 레이어로)"뿐이며, 예외는 "내 소관 아님"으로 취급한다.
500은 인프라 장애(LLM 서버 다운 = 503 경로) 전용이고, 해석 실패는 되묻기로 귀결된다.

발단 사고(2026-07-26): 프론트 칩이 previous_parsed에 `metric:"roe"`(정본은 roe_or_gpa)를
심었고, 이후 모든 수정 발화가 previous 검증 ValidationError → HTTP 500으로 죽어
"무엇을 입력해도 같은 에러"인 영구 교착이 됐다.
"""

import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

import main
from engine import nl_parser
from engine.nl_parser import ParsedStrategy
from main import NLParseRequest, _run_nl_parse
from strategy_conversation import config as sc_config
from strategy_conversation import primary


def _previous(**overrides) -> dict:
    """프론트가 되돌려주는 previous_parsed(신뢰할 수 없는 입력)."""
    base = ParsedStrategy(description="PBR 1 이하 종목 10개").model_dump()
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _clean_cache():
    main._nl_parse_cache.clear()
    yield
    main._nl_parse_cache.clear()


# ── ① 오염된 previous_parsed도 받아준다(별칭 정규화 + 미지 값 드롭) ─────────────

def test_polluted_previous_metric_alias_does_not_fail_the_request():
    """프론트가 심은 레거시 표기 'roe'가 있어도 수정 요청이 500 없이 처리된다."""
    request = NLParseRequest(
        prompt="손절 10%로 바꿔줘",
        previous_parsed=_previous(
            fundamental_filters=[{"metric": "roe", "operator": ">=", "value": 15}]
        ),
    )
    result = _run_nl_parse(request)
    assert result["parsed"]["stop_loss_pct"] == 10.0
    # 별칭은 정본으로 정규화돼 조건이 살아남는다(드롭도, 실패도 아니다).
    assert result["parsed"]["fundamental_filters"] == [
        {"metric": "roe_or_gpa", "operator": ">=", "value": 15.0}
    ]


def test_unknown_metric_is_dropped_with_a_notice_not_a_500():
    """별칭 표에도 없는 지표는 그 조건만 제외하고 비차단 안내로 알린다(조용한 드롭 금지)."""
    request = NLParseRequest(
        prompt="손절 10%로 바꿔줘",
        previous_parsed=_previous(
            fundamental_filters=[
                {"metric": "roe", "operator": ">=", "value": 15},
                {"metric": "made_up_metric", "operator": ">=", "value": 1},
            ]
        ),
    )
    result = _run_nl_parse(request)
    assert result["parsed"]["stop_loss_pct"] == 10.0
    assert [f["metric"] for f in result["parsed"]["fundamental_filters"]] == ["roe_or_gpa"]
    assert any("제외했어요" in n for n in result["notices"])


def test_metric_alias_normalization_is_case_and_separator_tolerant():
    parsed = ParsedStrategy.model_validate({
        "description": "t",
        "fundamental_filters": [{"metric": "ROE", "operator": ">=", "value": 15}],
    })
    assert parsed.fundamental_filters[0].metric == "roe_or_gpa"
    assert parsed.dropped_filter_notices == []


def test_dropped_filter_notices_never_leak_into_the_strategy_dump():
    """안내 전용 필드는 직렬화에서 제외된다 — DSL·캐시키·라운드트립 비교에 영향 금지."""
    parsed = ParsedStrategy.model_validate({
        "description": "t",
        "fundamental_filters": [{"metric": "made_up_metric", "operator": ">=", "value": 1}],
    })
    assert parsed.dropped_filter_notices == ["made_up_metric >= 1"]
    assert "dropped_filter_notices" not in parsed.model_dump()


# ── ② 결정론 fast-path의 예외는 "내 소관 아님"으로 강등된다 ─────────────────────

def test_fast_path_exception_degrades_to_next_layer(monkeypatch):
    """fast-path가 무슨 예외를 던져도 요청을 죽이지 않고 LLM 레이어로 넘어간다."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("fast-path 내부 오류")

    monkeypatch.setattr(nl_parser, "_modify_rule_based", boom)
    parser = nl_parser.NLStrategyParser(backend="ollama")
    previous = _previous()
    monkeypatch.setattr(
        parser, "_modify_ollama",
        lambda *_a, **_k: nl_parser.ParsedStrategyDiff(stop_loss_pct=7.0),
    )

    parsed = parser.parse_modification("손절 7%로 바꿔줘", previous)
    assert parsed.stop_loss_pct == 7.0


def test_primary_fast_path_probe_treats_exception_as_not_applicable(monkeypatch):
    def boom(*_args, **_kwargs):
        raise ValueError("오염된 previous")

    monkeypatch.setattr(nl_parser, "_modify_rule_based", boom)
    assert primary.fast_path_can_handle("손절 10%로", _previous()) is False


# ── ③ 모든 해석 실패는 500이 아니라 되묻기로 귀결된다 ──────────────────────────

def test_modify_interpretation_failure_returns_clarification_and_keeps_strategy(monkeypatch):
    monkeypatch.setattr(
        nl_parser.NLStrategyParser, "parse_modification",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("해석 불가")),
    )
    request = NLParseRequest(prompt="제주반도체를 추가해줘", previous_parsed=_previous())
    result = _run_nl_parse(request)

    assert result["clarification_question"] == main._INTERPRETATION_FAILURE_MESSAGE
    assert result["clarification_priority"] == "interpretation_failed"
    assert result["clarification_suggestions"]
    # 기존 전략은 그대로 보존된다 — 교착("무엇을 입력해도 같은 에러")의 구조적 차단.
    assert result["parsed"]["description"] == "PBR 1 이하 종목 10개"


def test_initial_parse_interpretation_failure_returns_clarification(monkeypatch):
    monkeypatch.setattr(
        nl_parser.NLStrategyParser, "parse",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("해석 불가")),
    )
    result = _run_nl_parse(NLParseRequest(prompt="!!!"))
    # 전략이 없는 상태에선 '변경' 칩이 가리킬 대상이 없다 — 예시는 문장으로만 안내한다.
    assert result["clarification_question"] == main._INTERPRETATION_FAILURE_CREATE_MESSAGE
    assert result["clarification_suggestions"] is None
    assert result["clarification_priority"] == "interpretation_failed"


def test_llm_connection_failure_still_raises_503_not_a_clarification(monkeypatch):
    """인프라 장애는 되묻기로 위장하지 않는다 — 500/503은 시스템 장애 전용으로 예약."""
    monkeypatch.setattr(
        nl_parser.NLStrategyParser, "parse",
        lambda *_a, **_k: (_ for _ in ()).throw(ConnectionError("Connection refused")),
    )
    with pytest.raises(HTTPException) as exc:
        _run_nl_parse(NLParseRequest(prompt="PBR 1 이하 종목 10개"))
    assert exc.value.status_code == 503


# ── ④ 수정 경로 해석 권한 순서(env 플래그) ─────────────────────────────────────

def test_modify_interpreter_mode_defaults_to_llm_first(monkeypatch):
    monkeypatch.delenv("STRATEGY_MODIFY_INTERPRETER_MODE", raising=False)
    assert sc_config.modify_interpreter_mode() == "llm_first"


def test_modify_interpreter_mode_rollback_value_is_honored(monkeypatch):
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "fast_path_first")
    assert sc_config.modify_interpreter_mode() == "fast_path_first"
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "nonsense")
    assert sc_config.modify_interpreter_mode() == "llm_first"


def test_fast_path_first_mode_skips_the_interpreter(monkeypatch):
    """롤백 모드에서는 결정론 fast-path가 인터프리터를 선점한다(LLM 호출 없음)."""
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "fast_path_first")

    def fail_if_called(*_a, **_k):
        raise AssertionError("fast_path_first 모드에서 인터프리터가 호출되면 안 된다")

    monkeypatch.setattr(primary, "_get_interpreter", fail_if_called)
    assert primary.run_primary_modification("손절 10%로 바꿔줘", _previous()) is None


def test_llm_first_mode_defers_to_fast_path_when_interpreter_yields_no_patches(monkeypatch):
    """llm_first에서도 fast-path는 살아 있는 폴백이다 — 인터프리터가 패치를 못 내면 양보."""
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "llm_first")

    class _Intent:
        intent = "CLARIFY_STRATEGY"
        patches: list = []
        clarification_questions = ["몇 %로 할까요?"]
        unsupported_features: list = []
        confidence = 1.0

    class _Result:
        intent = _Intent()
        model_name = "test"
        prompt_version = "test"
        repair_attempts = 0
        latency_ms = 0.0

    class _Interpreter:
        def interpret(self, *_a, **_k):
            return _Result()

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interpreter())
    # None = "내 소관 아님" → 호출부가 결정론 fast-path(parse_modification 1단계)로 확정한다.
    assert primary.run_primary_modification("손절 10%로 바꿔줘", _previous()) is None
