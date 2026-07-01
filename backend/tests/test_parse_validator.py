"""룰베이스 파서 결과 검증 LLM 레이어(engine.parse_validator) 테스트.

실제 LLM 호출은 하지 않는다 — _run_validation_llm을 patch해 응답을 주입하고,
파싱/자동교정/graceful degrade 동작만 검증한다.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine import parse_validator
from engine.nl_parser import NLStrategyParser, _parse_rule_based_strategy
from engine.parse_validator import (
    ParseValidationReport,
    build_validation_user_message,
    validate_parse,
)


@pytest.fixture
def parser():
    return NLStrategyParser(backend="ollama")


@pytest.fixture
def parsed_pbr():
    """룰베이스로 파싱된 단순 전략."""
    parsed = _parse_rule_based_strategy("PBR 1 이하 종목 10개 1년 보유")
    assert parsed is not None
    return parsed


def _patch_llm(monkeypatch, response):
    """_run_validation_llm이 주어진 응답(str 또는 예외)을 내도록 patch한다."""
    def fake(*_args, **_kwargs):
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(parse_validator, "_run_validation_llm", fake)


# ─── graceful degrade ────────────────────────────────────────────────

def test_degrades_when_llm_returns_nothing(monkeypatch, parser, parsed_pbr):
    """LLM 미가용(None)이면 원본을 그대로 반환하고 중립 리포트를 낸다."""
    _patch_llm(monkeypatch, None)

    result, report = validate_parse(parser, "PBR 1 이하 종목 10개 1년 보유", parsed_pbr)

    assert result is parsed_pbr
    assert report["isValid"] is True
    assert report["correctedStrategy"] is None
    assert report["userFacingMessage"] == ""


def test_degrades_when_llm_raises(monkeypatch, parser, parsed_pbr):
    """LLM 호출이 예외를 던져도 빠른 경로를 깨지 않고 원본을 반환한다."""
    _patch_llm(monkeypatch, RuntimeError("connection refused"))

    result, report = validate_parse(parser, "x", parsed_pbr)

    assert result is parsed_pbr
    assert report["isValid"] is True


def test_degrades_on_malformed_json(monkeypatch, parser, parsed_pbr):
    """LLM이 JSON이 아닌 잡음을 내면 degrade한다(예외 폴백)."""
    _patch_llm(monkeypatch, "이건 JSON이 아닙니다")

    result, report = validate_parse(parser, "x", parsed_pbr)

    assert result is parsed_pbr
    assert report["isValid"] is True


# ─── 정상 리포트 통과 ────────────────────────────────────────────────

def test_valid_report_passthrough(monkeypatch, parser, parsed_pbr):
    """correctedStrategy가 없으면 원본을 유지하고 리포트만 surface한다."""
    _patch_llm(monkeypatch, json.dumps({
        "isValid": True,
        "confidence": 0.95,
        "correctedStrategy": None,
        "issues": [],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "파싱이 원문 의도와 일치합니다.",
    }))

    result, report = validate_parse(parser, "PBR 1 이하 종목 10개 1년 보유", parsed_pbr)

    assert result is parsed_pbr
    assert report["isValid"] is True
    assert report["confidence"] == 0.95
    assert report["userFacingMessage"] == "파싱이 원문 의도와 일치합니다."


def test_issues_are_surfaced(monkeypatch, parser, parsed_pbr):
    """이슈/되묻기 항목이 리포트에 그대로 담긴다."""
    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.4,
        "correctedStrategy": None,
        "issues": [{"field": "exit_signals", "severity": "warning", "message": "청산 조건이 모호합니다."}],
        "missingFields": ["stop_loss_pct"],
        "clarificationQuestions": ["손절 기준을 추가할까요?"],
        "userFacingMessage": "확인이 필요한 부분이 있습니다.",
    }))

    _result, report = validate_parse(parser, "x", parsed_pbr)

    assert report["isValid"] is False
    assert report["issues"][0]["field"] == "exit_signals"
    assert report["missingFields"] == ["stop_loss_pct"]
    assert report["clarificationQuestions"] == ["손절 기준을 추가할까요?"]


# ─── 자동 교정(auto-apply) ──────────────────────────────────────────

def test_valid_correction_is_applied(monkeypatch, parser):
    """명백한 파싱 오류(손절↔익절 혼동)를 correctedStrategy로 자동 교정한다."""
    # 원문은 손절 5%인데 파서가 익절 5%로 잘못 넣은 상황을 모사.
    misparsed = _parse_rule_based_strategy("PBR 1 이하 종목 10개 1년 보유")
    misparsed.take_profit_pct = 5.0
    misparsed.stop_loss_pct = None

    corrected_dump = misparsed.model_dump()
    corrected_dump["take_profit_pct"] = None
    corrected_dump["stop_loss_pct"] = 5.0

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.9,
        "correctedStrategy": corrected_dump,
        "issues": [{"field": "stop_loss_pct", "severity": "error", "message": "손절이 익절로 잘못 해석됨"}],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "손절 5%로 교정했습니다.",
    }))

    result, report = validate_parse(parser, "손절 5%로 PBR 1 이하 10개 보유", misparsed)

    assert result is not misparsed
    assert result.stop_loss_pct == 5.0
    assert result.take_profit_pct is None
    assert report["correctedStrategy"]["stop_loss_pct"] == 5.0


def test_correction_preserves_original_description(monkeypatch, parser, parsed_pbr):
    """LLM이 description을 바꿔도 원문 설명은 보존한다."""
    tampered = parsed_pbr.model_dump()
    tampered["description"] = "LLM이 멋대로 바꾼 설명"
    tampered["max_positions"] = 7

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.8,
        "correctedStrategy": tampered,
        "issues": [],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "종목 수를 교정했습니다.",
    }))

    result, _report = validate_parse(parser, "PBR 1 이하 종목 10개 1년 보유", parsed_pbr)

    assert result.description == parsed_pbr.description
    assert result.max_positions == 7


def test_invalid_correction_is_discarded(monkeypatch, parser, parsed_pbr):
    """correctedStrategy가 스키마 위반이면 원본을 유지하고 correctedStrategy를 null로 비운다."""
    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.5,
        "correctedStrategy": {"universe": ["NASDAQ"], "fundamental_filters": "엉터리"},
        "issues": [],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "교정 시도",
    }))

    result, report = validate_parse(parser, "x", parsed_pbr)

    assert result is parsed_pbr
    assert report["correctedStrategy"] is None


# ─── 통합: parse()가 on_validation 콜백으로 리포트를 전달 ───────────────

def test_parse_invokes_on_validation_callback(monkeypatch, parser):
    """룰베이스 파싱이 '애매한'(설명 못 한 잔여 있음) 경우 parse()가 LLM 검증을 돌리고
    on_validation으로 리포트를 전달한다."""
    _patch_llm(monkeypatch, json.dumps({
        "isValid": True,
        "confidence": 1.0,
        "correctedStrategy": None,
        "issues": [],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "ok",
    }))

    reports = []
    # '삼성전자 같은'이 설명 못 한 잔여 → 검증 트리거.
    parsed = parser.parse("삼성전자 같은 PBR 1 이하 종목 10개 1년 보유", on_validation=reports.append)

    assert parsed is not None
    assert len(reports) == 1
    assert reports[0]["userFacingMessage"] == "ok"


def test_parse_skips_validation_for_clean_rule_parse(monkeypatch, parser):
    """[회귀] 룰 파싱이 원문 어휘를 다 설명한 '확신 파싱'이면 LLM 검증을 건너뛴다(즉답).
    흔한 명확한 입력에서 매번 붙던 검증 지연 제거."""
    called = {"llm": False}

    def _fail(*_a, **_k):
        called["llm"] = True
        raise AssertionError("clean 파싱은 LLM 검증을 호출하면 안 된다")

    monkeypatch.setattr(parser, "chat", _fail)

    reports = []
    parsed = parser.parse("PBR 1 이하 종목 10개 1년 보유", on_validation=reports.append)

    assert parsed is not None
    assert called["llm"] is False
    assert reports == []


# ─── 메시지/스키마 ──────────────────────────────────────────────────

def test_user_message_includes_input_and_parsed(parsed_pbr):
    msg = build_validation_user_message("PBR 1 이하 종목 10개", parsed_pbr.model_dump())
    assert "PBR 1 이하 종목 10개" in msg
    assert "fundamental_filters" in msg


def test_report_defaults_are_neutral():
    report = ParseValidationReport()
    assert report.isValid is True
    assert report.correctedStrategy is None
    assert report.issues == []
