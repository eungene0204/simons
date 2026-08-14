"""전략 예시 QA 하니스(scripts/qa_template_detect.py)의 판정 계약 회귀 테스트.

[2026-07-29 판정 수정] 값이 빠진 팩터를 되묻는 것은 전략 에이전트의 정상 동작이다
(사용자가 말하지 않은 값을 질문 없이 기본값으로 확정하지 않는다는 계약). 하니스가
그 되묻기를 '치명(예시가 전략이 되지 못함)'으로 세는 바람에, 정상 동작하는 예시 6개가
게이트를 붉게 만들고 있었다. 하니스가 잡아야 하는 것은 **조용한** 소실 —
질문도 없이 조건이 사라지거나 빈 전략이 나가는 경우다.

이 계약이 다시 조여지면(되묻기=실패) 정상 예시가 실패로 잡히므로 테스트로 고정한다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HARNESS = Path(__file__).resolve().parents[2] / "scripts" / "qa_template_detect.py"


@pytest.fixture(scope="module")
def qatd():
    spec = importlib.util.spec_from_file_location("qa_template_detect", _HARNESS)
    module = importlib.util.module_from_spec(spec)
    # dataclass 처리에 sys.modules 등록이 필요하다(cls.__module__ 조회).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name, None)


def _template(qatd, prompt: str):
    return qatd.Template(category="가치투자", level="beginner", title="t", prompt=prompt)


EMPTY_ENTRY = {"universe": ["KOSPI"], "max_positions": 10, "fundamental_filters": []}


def test_asking_for_missing_values_is_not_fatal(qatd):
    """값 없이 언급된 조건을 되묻는 중이면 진입 규칙 공백은 치명이 아니다."""
    prompt = "KOSPI에서 부채비율과 ROE 조건을 충족하는 종목을 대상으로 설정해 주세요."
    flags = qatd.analyze(
        _template(qatd, prompt),
        {
            "parsed": EMPTY_ENTRY,
            "clarification_question": "부채비율과 ROE 조건을 충족하는 종목을 매수할까요?",
        },
    )
    assert flags.fatal == []
    # 되묻는 팩터는 '미탐지(소실)'로도 세지 않는다.
    assert flags.missing == []


def test_silent_empty_entry_is_still_fatal(qatd):
    """되묻지도 않고 진입 규칙이 비면 빈 전략이 그대로 나간다 — 치명 유지."""
    prompt = "KOSPI에서 부채비율과 ROE 조건을 충족하는 종목을 대상으로 설정해 주세요."
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": EMPTY_ENTRY})
    assert any("진입 규칙 없음" in x for x in flags.fatal)
    # 질문 없이 사라진 조건은 미탐지로 드러나야 한다.
    assert set(flags.missing) >= {"ROE", "부채비율"}


def test_interpretation_failure_stays_fatal_even_with_question(qatd):
    """해석 실패는 되묻기가 있어도 치명이다 — 빈 전략(기본값)이 나간 경우."""
    flags = qatd.analyze(
        _template(qatd, "KOSPI에서 ROE 15% 이상인 종목"),
        {
            "parsed": EMPTY_ENTRY,
            "clarification_priority": "interpretation_failed",
            "clarification_question": "다시 말씀해 주시겠어요?",
        },
    )
    assert any("해석 실패" in x for x in flags.fatal)


def test_value_given_but_dropped_without_question_is_missing(qatd):
    """값을 명시했는데 파싱에도 없고 묻지도 않으면 조용한 소실 — 미탐지."""
    flags = qatd.analyze(
        _template(qatd, "KOSPI에서 PER 10 이하인 종목을 매수"),
        {"parsed": {**EMPTY_ENTRY, "entry_signals": [{"indicator": "rsi"}]}},
    )
    assert "PER" in flags.missing


def test_pending_condition_is_not_missing(qatd):
    """[2026-08-14] 값-대기 큐(pending_conditions)에 오른 조건은 순차 되묻기 대상이다.

    이번 턴 질문 텍스트에 아직 안 나왔다는 이유로 미탐지(소실)로 세면, 정상 동작(값-대기
    조건 채널)이 게이트를 붉게 만든다 — 실측: 예시 4건이 이 오탐으로 잡혔다.
    """
    prompt = "KOSPI 종목 중 PER이 낮고 부채비율이 낮은 기업만 남긴 뒤 8종목 정도 투자해 주세요."
    flags = qatd.analyze(
        _template(qatd, prompt),
        {
            "parsed": EMPTY_ENTRY,
            "clarification_question": "진입 조건의 PER 기준값을 얼마로 할까요?",
            "pending_conditions": [
                {"role": "entry", "label": "부채비율", "source_text": "부채비율이 낮은"},
            ],
        },
    )
    assert flags.fatal == []
    assert flags.missing == []


def test_parse_call_failure_counts_fatal(qatd, monkeypatch, tmp_path, capsys):
    """[2026-08-14] 파싱 호출 자체가 죽으면 치명으로 집계돼 종료 코드 1이어야 한다.

    실측: localhost:8000을 다른 프로세스가 선점해 81건 전부 HTTP 501이었는데
    '치명 0 · exit 0'으로 조용히 통과했다 — 검증이 성립하지 않은 실행은 실패다.
    """
    tpl = _template(qatd, "KOSPI에서 PER 10 이하 종목 매수")
    monkeypatch.setattr(qatd, "load_templates", lambda: [tpl])

    def _boom(prompt):
        raise RuntimeError("HTTP Error 501: Unsupported method ('POST')")

    monkeypatch.setattr(qatd, "parse_strategy", _boom)
    monkeypatch.setattr(qatd, "RAW_CACHE", tmp_path / "cache.json")
    monkeypatch.setattr(sys, "argv", ["qa_template_detect.py", "--refresh"])
    assert qatd.main() == 1
    assert "파싱 호출 실패" in capsys.readouterr().out


def test_notice_covered_condition_is_not_missing(qatd):
    """[2026-08-14] 안내(notices)로 알린 조건은 조용한 소실이 아니다 — 미탐지 제외.

    실측: '최근 거래대금이 30일 평균보다 높은'을 거래량 급증 조건으로 근사 반영하면서
    안내를 냈는데도 하니스가 '거래대금 미탐지'로 세어 게이트를 붉게 만들었다. 백엔드
    본경로가 제외 조건의 '설명됨' 판정에 notices를 쓰는 것과 같은 계약이다.
    """
    prompt = "KOSDAQ에서 최근 거래대금이 30일 평균보다 높은 경우만 진입해 주세요."
    flags = qatd.analyze(
        _template(qatd, prompt),
        {
            "parsed": {**EMPTY_ENTRY, "entry_signals": [{"indicator": "volume_spike"}]},
            "notices": ["'최근 거래대금이 30일 평균보다 높은 경우' 조건은 거래대금의 평균"
                        " 대비 비교를 지원하지 않아 거래량 급증 조건으로 반영했어요."],
        },
    )
    assert flags.missing == []
    assert flags.fatal == []
