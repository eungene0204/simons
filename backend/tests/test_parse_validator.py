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


def test_missed_sector_correction_is_applied(monkeypatch, parser):
    """룰 파서가 놓친 업종 제한("반도체 중심으로")을 검증 레이어가 sector로 교정한다.

    긴 꼬리 업종 표현은 regex 큐를 늘리는 대신 이 검증 단계에서 해결한다(하이브리드 원칙).
    교정 sector는 field_validator로 정본 섹터명에 정규화된다."""
    misparsed = _parse_rule_based_strategy("PBR 1 이하 종목 10개 1년 보유")
    assert misparsed.sector is None

    corrected_dump = misparsed.model_dump()
    corrected_dump["sector"] = "반도체"

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.9,
        "correctedStrategy": corrected_dump,
        "issues": [{"field": "sector", "severity": "error", "message": "업종 제한이 누락됨"}],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "반도체 업종 제한을 반영했습니다.",
    }))

    result, report = validate_parse(parser, "반도체 중심으로 PBR 1 이하 종목 10개 1년 보유", misparsed)

    assert result.sector == "반도체"
    assert report["correctedStrategy"]["sector"] == "반도체"


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


def test_hallucinated_ai_signal_in_correction_is_stripped(monkeypatch, parser):
    """[회귀] 교정 LLM이 사용자가 언급하지 않은 AI 신호(ai_model)를 끼워 넣으면 떨군다.

    실사례(2026-07-03): KOSDAQ 모멘텀 랭킹 프롬프트에 correctedStrategy가 'AI 매수 예측'
    진입 신호를 주입 → 스키마 검증만 통과해 그대로 적용 → 꺼둔 AI 백테스트가 실행되며 행.
    환각 신호만 떨구고 나머지 교정(종목 수 등)은 유지해야 한다.
    """
    prompt = (
        "최근 3개월 동안 꾸준히 오른 종목을 따라가는 전략을 써보고 싶어요. "
        "KOSDAQ에서 최근 60거래일 수익률이 높은 종목 상위권만 골라서 6종목 정도 나눠 사고, "
        "한 달에 한 번씩 다시 순위를 확인해 주세요. 손절은 -9%로 해주세요."
    )
    parsed = _parse_rule_based_strategy(prompt)
    assert parsed is not None
    assert parsed.entry_signals == []

    tampered = parsed.model_dump()
    tampered["entry_signals"] = [{"indicator": "ai_model", "signal_type": "buy", "threshold": 70}]
    tampered["max_positions"] = 5  # 환각 신호와 무관한 정상 교정은 유지돼야 한다

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.8,
        "correctedStrategy": tampered,
        "issues": [],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "교정했습니다.",
    }))

    result, report = validate_parse(parser, prompt, parsed)

    assert all(s.indicator != "ai_model" for s in result.entry_signals)
    assert result.max_positions == 5
    assert all(
        s["indicator"] != "ai_model" for s in report["correctedStrategy"]["entry_signals"]
    )


def test_hallucinated_universe_downgrade_in_correction_is_reverted(monkeypatch, parser):
    """[회귀] 교정 LLM이 "KOSPI 대형주"(→KOSPI200)를 그대로 "KOSPI"로 되돌리면 강제 복원한다.

    실사례(2026-07-05): "KOSPI 대형주 중에서 PBR이 1배 이하인 종목..." 프롬프트가 룰 파싱
    잔여 미해석으로 LLM 검증을 타고, correctedStrategy가 universe를 KOSPI200→KOSPI로
    되돌려 유니버스가 200종목에서 전체 코스피(800+ 종목)로 확대 → 백테스트가 크게 느려져
    전략연구소 화면이 멈춘 것처럼 보였다. 유니버스는 순수 어휘 매핑이라 교정 LLM이 원문과
    다르게 바꾸면 항상 되돌려야 한다(단, max_positions 등 숫자 필드는 교정을 존중한다).
    """
    prompt = "KOSPI 대형주 중에서 PBR이 1배 이하인 종목만 골라서 8종목 정도 나눠 사고, 6개월 보유, -12% 손절"
    parsed = _parse_rule_based_strategy(prompt)
    assert parsed is not None
    assert parsed.universe == ["KOSPI200"]

    tampered = parsed.model_dump()
    tampered["universe"] = ["KOSPI"]
    tampered["max_positions"] = 6  # 유니버스와 무관한 정상 교정은 유지돼야 한다

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.8,
        "correctedStrategy": tampered,
        "issues": [],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "교정했습니다.",
    }))

    result, report = validate_parse(parser, prompt, parsed)

    assert result.universe == ["KOSPI200"]
    assert result.max_positions == 6
    assert report["correctedStrategy"]["universe"] == ["KOSPI200"]


def test_ai_signal_in_correction_kept_when_user_mentioned_ai(monkeypatch, parser):
    """사용자가 원문에서 AI를 직접 언급했다면 교정본의 AI 신호는 환각이 아니므로 유지한다."""
    prompt = "AI가 상승 예측한 종목 매수, PBR 1 이하 종목 10개 1년 보유"
    parsed = _parse_rule_based_strategy(prompt)
    assert parsed is not None

    corrected_dump = parsed.model_dump()
    corrected_dump["entry_signals"] = [
        {"indicator": "ai_model", "signal_type": "buy", "threshold": 70}
    ]

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.9,
        "correctedStrategy": corrected_dump,
        "issues": [],
        "missingFields": [],
        "clarificationQuestions": [],
        "userFacingMessage": "교정했습니다.",
    }))

    result, _report = validate_parse(parser, prompt, parsed)

    assert any(s.indicator == "ai_model" for s in result.entry_signals)


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


# ─── 새 출력 계약: 최소 유효 출력 + correctedFields(부분 diff) ──────────

def test_minimal_valid_output_passthrough(monkeypatch, parser, parsed_pbr):
    """유효 판정은 {"isValid":true,"confidence":..} 두 필드만 출력해도 된다(생성 토큰 절감).
    나머지 리포트 필드는 스키마 기본값으로 채워진다."""
    _patch_llm(monkeypatch, json.dumps({"isValid": True, "confidence": 0.93}))

    result, report = validate_parse(parser, "PBR 1 이하 종목 10개 1년 보유", parsed_pbr)

    assert result is parsed_pbr
    assert report["isValid"] is True
    assert report["confidence"] == 0.93
    assert report["correctedStrategy"] is None
    assert report["issues"] == []


def test_corrected_fields_diff_is_merged(monkeypatch, parser):
    """correctedFields(바뀐 필드만)를 원본에 병합해 적용한다 — 손절↔익절 오귀속 교정.
    전체 전략 재출력 없이 diff만으로 교정이 성립해야 한다(검증 시간 단축의 핵심 계약)."""
    misparsed = _parse_rule_based_strategy("PBR 1 이하 종목 10개 1년 보유")
    misparsed.take_profit_pct = 5.0
    misparsed.stop_loss_pct = None

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.9,
        "correctedFields": {"take_profit_pct": None, "stop_loss_pct": 5.0},
        "issues": [{"field": "stop_loss_pct", "severity": "error", "message": "손절이 익절로 잘못 해석됨"}],
        "userFacingMessage": "손절 5%로 교정했습니다.",
    }))

    result, report = validate_parse(parser, "손절 5%로 PBR 1 이하 10개 보유", misparsed)

    assert result is not misparsed
    assert result.stop_loss_pct == 5.0
    assert result.take_profit_pct is None
    assert result.max_positions == misparsed.max_positions  # diff에 없는 필드는 보존
    # 하류 계약: 병합된 전체 교정본이 correctedStrategy로 채워진다.
    assert report["correctedStrategy"]["stop_loss_pct"] == 5.0


def test_corrected_fields_sector_fill(monkeypatch, parser):
    """놓친 업종 제한을 correctedFields {"sector": ...} 하나로 교정한다."""
    misparsed = _parse_rule_based_strategy("PBR 1 이하 종목 10개 1년 보유")
    assert misparsed.sector is None

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.9,
        "correctedFields": {"sector": "반도체"},
        "userFacingMessage": "반도체 업종 제한을 반영했습니다.",
    }))

    result, report = validate_parse(
        parser, "반도체 중심으로 PBR 1 이하 종목 10개 1년 보유", misparsed
    )

    assert result.sector == "반도체"
    assert report["correctedStrategy"]["sector"] == "반도체"


def test_corrected_fields_ignores_description_and_unknown_keys(monkeypatch, parser, parsed_pbr):
    """description(사용자 원문)과 미지 필드는 diff에서 걸러낸다 — 나머지 교정은 유지."""
    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.8,
        "correctedFields": {
            "description": "LLM이 멋대로 바꾼 설명",
            "unknown_field": 123,
            "max_positions": 7,
        },
        "userFacingMessage": "종목 수를 교정했습니다.",
    }))

    result, _report = validate_parse(parser, "PBR 1 이하 종목 10개 1년 보유", parsed_pbr)

    assert result.description == parsed_pbr.description
    assert result.max_positions == 7


def test_corrected_fields_hallucinated_signal_is_stripped(monkeypatch, parser):
    """diff 경로에서도 환각 신호 가드(_validate_signals)가 동작한다 — AI 미언급 원문에
    ai_model 신호를 끼워 넣으면 떨구고 나머지 교정(종목 수)은 유지."""
    prompt = "KOSDAQ에서 최근 60거래일 수익률 상위 6종목, 한 달마다 리밸런싱, 손절 -9%"
    parsed = _parse_rule_based_strategy(prompt)
    assert parsed is not None

    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.8,
        "correctedFields": {
            "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 70}],
            "max_positions": 5,
        },
        "userFacingMessage": "교정했습니다.",
    }))

    result, report = validate_parse(parser, prompt, parsed)

    assert all(s.indicator != "ai_model" for s in result.entry_signals)
    assert result.max_positions == 5
    assert all(
        s["indicator"] != "ai_model" for s in report["correctedStrategy"]["entry_signals"]
    )


def test_invalid_corrected_fields_discarded(monkeypatch, parser, parsed_pbr):
    """correctedFields 병합본이 스키마 위반이면 원본을 유지하고 리포트 교정 필드를 비운다."""
    _patch_llm(monkeypatch, json.dumps({
        "isValid": False,
        "confidence": 0.5,
        "correctedFields": {"fundamental_filters": "엉터리"},
        "userFacingMessage": "교정 시도",
    }))

    result, report = validate_parse(parser, "x", parsed_pbr)

    assert result is parsed_pbr
    assert report["correctedStrategy"] is None
    assert report["correctedFields"] is None


def test_validation_message_omits_null_fields(monkeypatch, parser, parsed_pbr):
    """검증 LLM에 보내는 파싱 JSON은 null 필드를 뺀다(입력 토큰 절감).
    프롬프트가 '누락=null'을 명시하므로 의미는 보존된다."""
    captured = {}

    def fake(_parser, _system, user_message):
        captured["msg"] = user_message
        return None  # degrade — 메시지 캡처만 목적

    monkeypatch.setattr(parse_validator, "_run_validation_llm", fake)
    assert parsed_pbr.sector is None

    validate_parse(parser, "PBR 1 이하 종목 10개 1년 보유", parsed_pbr)

    assert '"sector"' not in captured["msg"]
    assert '"fundamental_filters"' in captured["msg"]


# ─── 비차단(후행) 검증: defer_validation ─────────────────────────────

def test_parse_defers_validation_when_requested(monkeypatch, parser):
    """defer_validation=True면 검증 LLM을 돌리지 않고 룰 파스를 즉시 반환하며,
    on_validation에 {"pending": True}로 검증 필요를 알린다(SSE 후행 검증용)."""
    def _fail(*_a, **_k):
        raise AssertionError("defer 모드는 인라인 검증 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parse_validator, "_run_validation_llm", _fail)

    reports = []
    # '삼성전자 같은'이 설명 못 한 잔여 → 원래라면 검증 트리거.
    parsed = parser.parse(
        "삼성전자 같은 PBR 1 이하 종목 10개 1년 보유",
        on_validation=reports.append,
        defer_validation=True,
    )

    assert parsed is not None
    assert reports == [{"pending": True}]


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
