"""전략 템플릿 일괄 QA(backend/qa_template_coverage.py)에서 드러난 회귀 케이스.

각 테스트는 QA 리포트에서 실제로 확인된 결함을 재현한다:
  - 종목수 폴백 버그(KOSPI200 유니버스 숫자·'N개 분기'를 종목 수로 오인)
  - 파서 미탐지(ADX, 거래대금 동적 신호, 볼린저 상단 돌파, 'N개월마다 점검' 리밸런싱)
  - 파서 비결정성(완전 명시 프롬프트는 규칙 기반에서 결정적으로 처리되어야 LLM 폴백의
    실행마다 다른 결과를 피할 수 있다)
  - 코치 confabulation(parsed_strategy에 없는 지표를 '잡혀 있다'고 거짓 확언)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import (
    _extract_max_positions,
    _extract_rebalancing_period,
    _extract_hold_period_days,
    _extract_technical_signals,
    _extract_fundamental_filters,
    _parse_rule_based_strategy,
)
from api import coach_routes
from api.coach_routes import CoachRequest, _unparsed_mentions, _strip_internal_context_leak


def _indicators(signals):
    return [s.indicator for s in signals]


# ──────────────────────────────────────────────────────────────────────────
# #3 종목수 폴백 버그
# ──────────────────────────────────────────────────────────────────────────
class TestMaxPositionsFallback:
    def test_kospi200_universe_number_not_counted_as_positions(self):
        # 'KOSPI 200 종목 중 ... 20종목' → 200(유니버스 규모)이 아니라 20이어야 한다.
        prompt = "KOSPI 200 종목 중 PER 15배 이하, 20종목 동일 비중으로 편입하고 분기 리밸런싱"
        assert _extract_max_positions(prompt) == 20

    def test_kospi200_compact_universe_number_not_counted(self):
        prompt = "KOSPI200 종목 중 ADX가 23 이상, 최대 10종목, 손절 -6.5%"
        assert _extract_max_positions(prompt) == 10

    def test_n_quarter_not_counted_as_positions(self):
        # '최근 4개 분기'의 4를 종목 수로 오인하지 않고, '10종목 집중'을 잡아야 한다.
        prompt = "최근 4개 분기 영업활동현금흐름이 개선되는 기업, 10종목 집중 포트폴리오"
        assert _extract_max_positions(prompt) == 10

    def test_sector_limit_not_counted_total_wins(self):
        # '동일 업종 최대 2종목'(섹터 제한)이 아니라 '총 14종목'(포트폴리오 크기)을 잡아야 한다.
        prompt = "동일 업종 최대 2종목 제한을 두고 총 14종목 포트폴리오를 구성하겠습니다"
        assert _extract_max_positions(prompt) == 14

    @pytest.mark.parametrize(
        "prompt,expected",
        [
            ("PBR이 1배 이하인 종목만 골라서 8종목 정도 나눠 사고", 8),
            ("골든크로스 매수, 종목은 최대 10개", 10),
            ("52주 신고가, 최대 6종목, 손절 -10%", 6),
            ("PBR 1.5배 이하 ROE 8% 이상, 12종목 정도로 포트폴리오", 12),
        ],
    )
    def test_well_specified_counts_unchanged(self, prompt, expected):
        assert _extract_max_positions(prompt) == expected


# ──────────────────────────────────────────────────────────────────────────
# #2 파서 미탐지 보강
# ──────────────────────────────────────────────────────────────────────────
class TestParserCoverage:
    def test_adx_entry_signal_detected(self):
        entry, _ = _extract_technical_signals(
            "ADX가 25 이상으로 올라온 후 5일 EMA가 20일 EMA를 상향 돌파하는 시점 매수"
        )
        adx = [s for s in entry if s.indicator == "adx"]
        assert adx, "ADX 조건이 진입 신호로 잡혀야 한다"
        assert adx[0].operator == ">=" and adx[0].value == 25.0

    def test_trading_value_multiple_is_dynamic_signal(self):
        entry, _ = _extract_technical_signals("당일 거래대금이 최근 20일 평균의 2배 이상")
        assert "volume_spike" in _indicators(entry)

    def test_trading_value_rising_without_average_is_signal(self):
        entry, _ = _extract_technical_signals("최근 거래대금이 크게 늘고 주가가 5일 연속 강한")
        assert "volume_spike" in _indicators(entry)

    def test_bollinger_upper_breakout_entry_and_lower_exit(self):
        entry, exit_ = _extract_technical_signals(
            "볼린저밴드 상단을 돌파하면서 거래량도 급증한 종목만 진입, 하단에 닿으면 청산"
        )
        assert "bollinger_bands" in _indicators(entry)
        assert "bollinger_bands" in _indicators(exit_)

    def test_n_month_periodic_is_rebalancing_not_hold(self):
        prompt = "10종목 나눠 사고, 3개월마다 다시 점검해 주세요. 손절은 -10%"
        assert _extract_rebalancing_period(prompt, None) == "quarterly"
        # 'N개월마다 점검'은 보유기간이 아니다(보유 동사 없음).
        assert _extract_hold_period_days(prompt) is None

    def test_hold_period_with_holding_verb_unchanged(self):
        # '6개월은 들고 가고'는 보유기간이며 리밸런싱이 아니다.
        prompt = "PBR 1배 이하, 8종목, 6개월은 들고 가고 싶습니다"
        assert _extract_hold_period_days(prompt) == 126
        assert _extract_rebalancing_period(prompt, 126) == "none"
        # 단 '최소 6개월'(하한)은 hold_period_days(만료 청산=상한)로 뒤집지 않는다
        # (2026-07-29 계약 — 보유 동사가 있어도 하한 수식이 붙으면 추출 대상 아님).
        assert _extract_hold_period_days("PBR 1배 이하, 최소 6개월은 들고 가고 싶습니다") is None

    def test_roe_and_debt_ratio_with_particle(self):
        # 'ROE가 10% 이상이고 부채비율이 100% 이하' — 조사(이/가)가 붙어도 잡혀야 한다.
        metrics = {
            (x.metric, x.operator, x.value)
            for x in _extract_fundamental_filters("ROE가 10% 이상이고 부채비율이 100% 이하인 종목")
        }
        assert ("roe_or_gpa", ">=", 10.0) in metrics
        assert ("debt_ratio", "<=", 100.0) in metrics


# ──────────────────────────────────────────────────────────────────────────
# #4 비결정성 — 완전 명시 프롬프트는 규칙 기반에서 결정적으로 처리되어야 한다
# ──────────────────────────────────────────────────────────────────────────
# 규칙 기반이 None을 반환하면 LLM 폴백(샘플링)으로 넘어가 실행마다 결과가 달라진다.
# 아래 프롬프트는 진입·청산 슬롯이 명시돼 있어 규칙 기반에서 결정적으로 끝나야 한다.
_DETERMINISTIC_PROMPTS = [
    "KOSPI 대형주 중 PBR이 1배 이하인 종목만 골라서 8종목, 6개월 보유, 손절 -12%",
    "KOSPI 종목 중 골든크로스가 나오면 매수하고 데드크로스가 나오면 매도, 최대 10개, 손절 -8%",
    "KOSDAQ ADX가 25 이상 후 5일 EMA가 20일 EMA를 상향 돌파 시 매수, 최대 8종목, 손절 -6%",
    "KOSPI200 볼린저밴드 상단을 돌파하면서 거래량 급증 시 진입, 하단 닿으면 청산, 10종목, 손절 -6%, 익절 +20%",
]


class TestParseDeterminism:
    @pytest.mark.parametrize("prompt", _DETERMINISTIC_PROMPTS)
    def test_fully_specified_prompt_handled_by_rules(self, prompt):
        # 규칙 기반이 처리해야 LLM 폴백의 비결정성을 피한다.
        assert _parse_rule_based_strategy(prompt) is not None

    @pytest.mark.parametrize("prompt", _DETERMINISTIC_PROMPTS)
    def test_rule_based_parse_is_deterministic(self, prompt):
        first = _parse_rule_based_strategy(prompt)
        second = _parse_rule_based_strategy(prompt)
        assert first is not None and second is not None
        assert first.model_dump() == second.model_dump()


# ──────────────────────────────────────────────────────────────────────────
# #1 코치 confabulation 차단
# ──────────────────────────────────────────────────────────────────────────
class TestCoachConfabulation:
    def test_unparsed_adx_is_flagged(self):
        # 사용자는 ADX를 말했지만 전략엔 ema만 있는 경우 → ADX 미반영으로 잡아야 한다.
        ps = {"entry_signals": [{"indicator": "ema", "signal_type": "buy"}], "fundamental_filters": []}
        dropped = _unparsed_mentions("ADX가 25 이상이고 EMA 상향 돌파 시 매수", ps)
        assert "ADX" in dropped

    def test_unparsed_rsi_is_flagged(self):
        ps = {
            "entry_signals": [{"indicator": "macd", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "macd", "signal_type": "sell"}],
            "fundamental_filters": [],
        }
        dropped = _unparsed_mentions("MACD 골든크로스에 RSI 50 이상에서 매수", ps)
        assert "RSI" in dropped

    def test_present_indicator_not_flagged(self):
        ps = {"entry_signals": [{"indicator": "rsi", "signal_type": "buy"}], "fundamental_filters": []}
        assert _unparsed_mentions("RSI 30 이하에서 매수", ps) == []

    def test_build_user_message_warns_about_dropped_condition(self):
        req = CoachRequest(
            user_prompt="KOSDAQ ADX가 25 이상 후 EMA 상향 돌파 시 매수, 8종목, 손절 -6%",
            parsed_strategy={
                "universe": ["KOSDAQ"],
                "entry_signals": [{"indicator": "ema", "signal_type": "buy"}],
                "exit_signals": [{"indicator": "ema", "signal_type": "sell"}],
                "fundamental_filters": [],
                "max_positions": 8,
                "stop_loss_pct": 6.0,
            },
        )
        msg = coach_routes._build_user_message(req)
        assert "미반영 조건" in msg
        assert "ADX" in msg
        # 거짓 확언을 금지하는 지침이 포함돼야 한다.
        assert "잘 잡혀 있다" in msg or "설정되어 있다" in msg


class TestInternalLeakFilter:
    def test_strips_experiment_basis_internal_instruction(self):
        leaked = (
            "유사 실험 근거는 내부 참고용으로만 사용하세요. 판단하면 위험 대비 수익성은 "
            "비교적 양호했습니다. 현재 전략은 먼저 같은 기간과 비용 조건으로 백테스트하세요."
        )
        cleaned = _strip_internal_context_leak(leaked)
        assert "내부 참고용" not in cleaned
        assert "참고용으로만" not in cleaned
        # 정상 본문은 남아야 한다.
        assert "백테스트" in cleaned
