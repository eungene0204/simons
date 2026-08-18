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


# ── 금액 임계값 대조(2026-08-18) ────────────────────────────────────────────────

_AMOUNT_PROMPT = ("KOSPI에서 시가총액 1조 원 이상 대형주 중 PBR 1배 이하, ROE 10% 이상인 "
                  "종목만 10종목으로 추려 주세요.")


def _amount_parsed(qatd, market_cap: float):
    return {"universe": ["KOSPI"], "max_positions": 10, "fundamental_filters": [
        {"metric": "market_cap", "operator": ">=", "value": market_cap},
        {"metric": "pbr", "operator": "<=", "value": 1.0},
        {"metric": "roe_or_gpa", "operator": ">=", "value": 10.0},
    ]}


def test_amount_threshold_magnitude_error_is_fatal(qatd):
    """사고(2026-08-18): "시가총액 1조 원 이상"이 100000(=10조, 10배)으로 파싱됐는데
    커버리지 검사가 `_has_fund`로 **지표 존재만** 봐서 08-14 전수 검증을 치명 0으로
    통과했다. 억원 단위 임계값은 자릿수 하나가 전략을 10배 바꾸므로 값까지 대조한다."""
    flags = qatd.analyze(_template(qatd, _AMOUNT_PROMPT),
                         {"parsed": _amount_parsed(qatd, 100000.0)})
    assert any("시가총액 임계값 오차" in x for x in flags.fatal)


def test_amount_threshold_match_is_clean(qatd):
    """정상 값(1조=10000억)은 아무 판정도 남기지 않는다."""
    flags = qatd.analyze(_template(qatd, _AMOUNT_PROMPT),
                         {"parsed": _amount_parsed(qatd, 10000.0)})
    assert flags.fatal == [] and flags.missing == []


def test_amount_threshold_absent_metric_is_left_to_missing_lane(qatd):
    """지표 자체가 없으면 값 대조는 침묵한다 — 부재 판정은 미탐지 레인(되묻기 예외 포함)
    소관이며, 두 레인이 같은 결손을 이중으로 세면 되묻기 예외가 무력해진다."""
    parsed = {"universe": ["KOSPI"], "max_positions": 10, "fundamental_filters": [
        {"metric": "pbr", "operator": "<=", "value": 1.0}]}
    flags = qatd.analyze(_template(qatd, _AMOUNT_PROMPT),
                         {"parsed": parsed,
                          "clarification_question": "시가총액 기준을 얼마로 할까요?"})
    assert not any("임계값 오차" in x for x in flags.fatal)


def test_amount_threshold_partial_extraction_does_not_false_alarm(qatd):
    """정규식은 지표명 뒤 금액 하나만 잡는다("3000억 이상 3조 이하"→3000). 파싱에만 있는
    값(상한 30000)을 문제 삼으면 정상 예시가 붉어지므로, 대조는 기대값 포함 여부로만 한다."""
    prompt = "코스피에서 시가총액 3000억 원 이상 3조 원 이하 중형주만 8종목 담고 싶어요."
    parsed = {"universe": ["KOSPI"], "max_positions": 8, "fundamental_filters": [
        {"metric": "market_cap", "operator": ">=", "value": 3000.0},
        {"metric": "market_cap", "operator": "<=", "value": 30000.0}]}
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert flags.fatal == []


def test_expected_amount_thresholds_converts_trillion_unit(qatd):
    """기대값 추출은 조×10,000+억 산술 합산이다(표기 환산 — 의미 해석 아님)."""
    assert ("market_cap", 10000.0) in qatd.expected_amount_thresholds("시가총액 1조 원 이상")
    assert ("market_cap", 25000.0) in qatd.expected_amount_thresholds("시총 2조 5000억 넘는")
    assert ("trading_value", 50.0) in qatd.expected_amount_thresholds("거래대금 50억 원 이상")


# ── 값 대조 확장: 스칼라 설정·신호 수치(2026-08-18) ────────────────────────────

def test_risk_percent_value_error_is_fatal(qatd):
    """손절·익절은 '설정됐는지'가 아니라 '얼마인지'까지 본다."""
    prompt = "KOSPI에서 PBR 1배 이하 종목을 매수하고 손절은 -10%, 익절은 +20%로 해주세요."
    parsed = {"universe": ["KOSPI"], "max_positions": 10,
              "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
              "stop_loss_pct": 1.0, "take_profit_pct": 20.0}
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert any("손절 값 오차" in x for x in flags.fatal)
    assert not any("익절" in x for x in flags.fatal)


def test_rebalancing_value_error_is_fatal(qatd):
    """'매월 한 번'이 quarterly로 파싱되면 주기가 3배 달라진다 — 존재만 보면 통과한다."""
    prompt = "KOSPI에서 PBR 1배 이하 종목을 10종목 담고 매월 한 번 리밸런싱해 주세요."
    parsed = {"universe": ["KOSPI"], "max_positions": 10,
              "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
              "rebalancing_period": "quarterly"}
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert any("리밸런싱 값 오차" in x for x in flags.fatal)


def test_moving_average_period_loss_is_fatal(qatd):
    """실측(2026-08-18): "20일 EMA가 60일 EMA 위에"가 `ema(long=60, above)` 하나로 파싱돼
    20일 EMA가 사라졌다 — 가격이 60일선 위인지를 보는 다른 전략이 된다. 지표 귀속은 묻지
    않고 말한 기간이 신호 어딘가에 남았는지만 본다."""
    prompt = "KOSPI에서 20일 EMA가 60일 EMA 위에 있는 종목을 매수해 주세요."
    parsed = {"universe": ["KOSPI"], "max_positions": 10,
              "entry_signals": [{"indicator": "ema", "long_period": 60, "mode": "above"}]}
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert any("이동평균 기간 소실" in x and "20" in x for x in flags.fatal)


def test_moving_average_periods_present_anywhere_is_clean(qatd):
    """두 기간이 신호 어딘가에 남아 있으면 통과한다(칸 귀속을 따지면 오탐이 된다)."""
    prompt = "KOSPI에서 5일 이동평균선이 20일 이동평균선을 위로 뚫으면 매수해 주세요."
    parsed = {"universe": ["KOSPI"], "max_positions": 10, "entry_signals": [
        {"indicator": "ma_crossover", "short_period": 5, "long_period": 20}]}
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert flags.fatal == []


def test_trading_value_average_window_is_not_compared(qatd):
    """'20일 평균 거래대금 30억 이상'의 20일은 지표 정의(일평균거래대금)에 내장된 창이라
    파싱 결과에 담길 칸이 없다 — 대조 대상에 넣으면 정상 예시가 붉어진다(실측 3건)."""
    prompt = "KOSPI에서 최근 20일 평균 거래대금이 30억 원 이상인 종목만 매수해 주세요."
    parsed = {"universe": ["KOSPI"], "max_positions": 10, "entry_signals": [
        {"indicator": "trading_value", "operator": ">=", "value": 30.0}]}
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert flags.fatal == []


def test_duplicated_identical_exit_condition_is_fatal(qatd):
    """실측(2026-08-18, 예시 51): 'EMA 데드크로스 청산'이 exit_signals에 완전히 같은 신호로
    2개 실렸는데 08-17 전수 검증이 치명 0으로 통과했다 — 판정이 소실·값 오차만 보고 잉여를
    안 봤다(리포트엔 '청산=ema,ema'로 찍혀 있었다). 같은 역할 안 동일 조건 반복은 치명이다."""
    prompt = ("KOSPI 종목 중 ADX가 25 이상으로 추세 강도가 확인된 상태에서 5일 EMA가 20일 EMA를 "
              "위로 돌파할 때 매수하고 싶습니다. EMA 데드크로스가 나오면 청산하고, 10종목, "
              "손절 -8%로 부탁드립니다.")
    ema_sell = {"indicator": "ema", "signal_type": "sell", "short_period": 5, "long_period": 20,
                "period": None, "operator": None, "value": None, "mode": None}
    parsed = {"universe": ["KOSPI"], "max_positions": 10, "stop_loss_pct": 8.0,
              "entry_signals": [
                  {"indicator": "adx", "signal_type": "buy", "period": 14, "operator": ">=", "value": 25.0},
                  {"indicator": "ema", "signal_type": "buy", "short_period": 5, "long_period": 20}],
              "exit_signals": [ema_sell, dict(ema_sell)]}
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert any("청산 신호 중복" in x and "ema" in x for x in flags.fatal)


def test_distinct_same_indicator_conditions_are_not_duplicates(qatd):
    """기간이 다른 같은 지표(EMA 5/20·20/60 데드크로스)는 서로 다른 신호 — 중복이 아니다.
    null 필드는 없는 것으로 보고 비교하므로 직렬화 차이(누락 vs null)로 오탐하지 않는다."""
    prompt = "KOSPI에서 5일 EMA가 20일 EMA를 하향 돌파하거나 20일 EMA가 60일 EMA를 하향 돌파하면 청산해 주세요."
    parsed = {"universe": ["KOSPI"], "max_positions": 10,
              "entry_signals": [{"indicator": "rsi", "operator": "<=", "value": 30.0}],
              "exit_signals": [
                  {"indicator": "ema", "signal_type": "sell", "short_period": 5, "long_period": 20, "value": None},
                  {"indicator": "ema", "signal_type": "sell", "short_period": 20, "long_period": 60}]}
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert not any("중복" in x for x in flags.fatal)


def test_stated_scalar_lost_entirely_is_fatal(qatd):
    """[회귀] 사용자가 말한 스칼라 설정이 통째로 사라지면 치명이다.

    사고(2026-08-18): 예시 32의 '보유 기간 상한 40거래일'이 파싱에서 사라졌는데도 전수
    검증이 `치명 0`이었다. 구멍은 둘이었다 — ① 기대값 추출기가 '보유 기간 상한 N거래일'
    표기를 읽지 못해 기대값 목록에 오르지도 못했고, ② 대조 루프가 파싱값이 None이면
    건너뛰어 **값 오차는 잡고 소실은 침묵**했다. 기대값 목록에는 사용자가 말한 값만
    오르므로(값 없는 항목은 애초에 제외) 비어 있으면 소실로 세운다.
    """
    prompt = ("KOSPI 종목 중 20일 신고가 경신 종목만 편입하고 월간 리밸런싱으로 최대 12종목"
              " 포트폴리오를 유지하겠습니다. 손절 -7%, 보유 기간 상한 40거래일을 추가해 주세요.")
    # ① 기대값 추출: '상한' 표기를 읽는다.
    assert ("보유기간", "hold_period_days", 40) in qatd.expected_scalar_values(prompt)

    parsed = {
        "universe": ["KOSPI"],
        "max_positions": 12,
        "rebalancing_period": "monthly",
        "stop_loss_pct": 7.0,
        "entry_signals": [{"indicator": "breakout", "lookback_period": 20}],
        "fundamental_filters": [],
        "hold_period_days": None,
    }
    flags = qatd.analyze(_template(qatd, prompt), {"parsed": parsed})
    assert any("보유기간 소실" in x for x in flags.fatal), flags.fatal

    # 값이 살아 있으면 조용하다(정상 예시를 붉히지 않는다).
    parsed_ok = {**parsed, "hold_period_days": 40}
    assert qatd.analyze(_template(qatd, prompt), {"parsed": parsed_ok}).fatal == []
