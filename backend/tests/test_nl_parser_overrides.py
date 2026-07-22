import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import (
    FundamentalFilter,
    NLStrategyParser,
    ParsedStrategy,
    ParsedStrategyDiff,
    TechnicalSignal,
    _apply_prompt_overrides,
    _extract_explicit_universe,
    _build_fallback_strategy,
    detect_missing_entry_clarification,
    _extract_technical_signals,
    _extract_fundamental_filters,
    _extract_initial_capital,
    _extract_rebalancing_period,
    _match_risk_pct,
    extract_risk_field_overrides,
    synthesize_risk_overrides,
    ParsedStrategy,
    _merge_signals,
    _parse_rule_based_strategy,
    _mentions_unsupported_concept,
    _rule_parse_red_flag,
    _rule_parse_unexplained,
    _extract_guard_decision,
    _parse_model_json_response,
    _validate_signals,
    _STOP_LOSS_CUE,
    _STOP_LOSS_BLOCK,
    _TAKE_PROFIT_CUE,
    _TAKE_PROFIT_BLOCK,
    _TRAILING_CUE,
    _TRAILING_BLOCK,
)

# ─── 진행 단계(on_stage) 콜백 테스트 ────────────────────────────────────────


def test_parse_rule_based_path_does_not_emit_thinking_stage():
    """규칙 기반으로 즉시 파싱되면 on_stage('thinking')를 호출하지 않는다."""
    parser = NLStrategyParser(backend="ollama")
    stages = []
    parsed = parser.parse("PBR 1 이하 종목 10개 1년 보유", on_stage=stages.append)

    assert parsed is not None
    assert "thinking" not in stages


def test_parse_emits_thinking_stage_before_llm_fallback(monkeypatch):
    """규칙 기반이 못 풀어 LLM으로 넘어가기 직전 on_stage('thinking')를 호출한다."""
    from engine import nl_parser as nl

    monkeypatch.setattr(nl, "_parse_rule_based_strategy", lambda _user_input: None)

    parser = NLStrategyParser(backend="ollama")
    fallback = _build_fallback_strategy("애매한 전략")
    monkeypatch.setattr(parser, "_parse_ollama", lambda _user_input: fallback)

    stages = []
    parser.parse("애매한 전략", on_stage=stages.append)

    assert stages == ["thinking"]


# ─── 삭제 의도 테스트 ─────────────────────────────────────────────────────────


def test_apply_prompt_overrides_deletes_stop_loss_on_explicit_delete():
    """'손절 -7%를 삭제하자' → stop_loss_pct가 None으로 설정되어야 함"""
    base = make_base_strategy().model_copy(update={"stop_loss_pct": 7.0})
    parsed = _apply_prompt_overrides(base, "손절 -7%를 삭제하자")

    assert parsed.stop_loss_pct is None


def test_apply_prompt_overrides_deletes_stop_loss_various_delete_keywords():
    """다양한 삭제 키워드에서 손절이 제거되어야 함"""
    for prompt in ["손절 없애줘", "손절 제거해줘", "손절 지워줘", "손절 빼줘"]:
        base = make_base_strategy().model_copy(update={"stop_loss_pct": 10.0})
        parsed = _apply_prompt_overrides(base, prompt)
        assert parsed.stop_loss_pct is None, f"prompt={prompt!r}에서 stop_loss_pct가 남아있음"


def test_apply_prompt_overrides_deletes_take_profit_on_explicit_delete():
    """'익절 삭제해줘' → take_profit_pct가 None으로 설정되어야 함"""
    base = make_base_strategy().model_copy(update={"take_profit_pct": 20.0})
    parsed = _apply_prompt_overrides(base, "익절 삭제해줘")

    assert parsed.take_profit_pct is None


def test_apply_prompt_overrides_does_not_extract_stop_loss_from_delete_prompt():
    """삭제 요청에서 값이 잘못 추출되어 stop_loss가 재설정되면 안 됨"""
    base = make_base_strategy().model_copy(update={"stop_loss_pct": 7.0})
    parsed = _apply_prompt_overrides(base, "손절 -7%를 삭제하자")

    # 7.0이 다시 설정되지 않고 None이어야 함
    assert parsed.stop_loss_pct is None, "삭제 요청인데 stop_loss_pct가 7.0으로 재설정됨"


def make_base_strategy() -> ParsedStrategy:
    return ParsedStrategy(
        description="테스트 전략",
        universe=["KOSPI200"],
        fundamental_filters=[],
        entry_signals=[],
        exit_signals=[],
        max_positions=10,
        hold_period_days=None,
        rebalancing_period="none",
        stop_loss_pct=None,
        take_profit_pct=None,
        trailing_stop_pct=None,
        max_mdd_limit_pct=None,
        backtest_period="5y",
        initial_capital=10000000.0,
        execution_timing="next_open",
        fee_rate=0.015,
        slippage_rate=0.05,
    )


def test_apply_prompt_overrides_respects_explicit_kospi_universe():
    parsed = _apply_prompt_overrides(make_base_strategy(), "kospi 종목으로 해줘")

    assert parsed.universe == ["KOSPI"]


def test_large_cap_maps_to_kospi200():
    # "대형주"는 시총 기준 분류 → 표준 대형주 지수 KOSPI200으로 매핑.
    assert _extract_explicit_universe("KOSPI 대형주 중에서 PBR 1배 이하") == ["KOSPI200"]
    assert _extract_explicit_universe("대형주 위주로 담고 싶어") == ["KOSPI200"]


# ─── 명시적 백테스트 연도 범위 ────────────────────────────────────────────────


def test_extract_backtest_dates_full_range():
    from engine.nl_parser import _extract_backtest_dates
    assert _extract_backtest_dates("2002년부터 2005년까지만 테스트 해줘") == ("2002-01-01", "2005-12-31")
    assert _extract_backtest_dates("2002~2005 테스트") == ("2002-01-01", "2005-12-31")
    assert _extract_backtest_dates("2003년만 돌려줘") == ("2003-01-01", "2003-12-31")


def test_extract_backtest_dates_open_ended_and_none():
    from engine.nl_parser import _extract_backtest_dates
    assert _extract_backtest_dates("2010년부터 테스트") == ("2010-01-01", None)
    assert _extract_backtest_dates("2008년까지 보고싶어") == (None, "2008-12-31")
    assert _extract_backtest_dates("PBR 1 이하 5종목") == (None, None)


def test_apply_prompt_overrides_sets_backtest_dates():
    parsed = _apply_prompt_overrides(make_base_strategy(), "2002년부터 2005년까지만 테스트 해줘")
    assert parsed.backtest_start_date == "2002-01-01"
    assert parsed.backtest_end_date == "2005-12-31"


def test_extract_backtest_dates_year_month_range():
    # 2026-07-17 사고: 월이 붙은 명시 범위("2020년 1월 부터 2025년 12월 까지")가 연도 전용
    # 정규식에 안 잡혀 LLM으로 위임됐고, 오늘 날짜를 모르는 모델이 종료일을 누락했다.
    from engine.nl_parser import _extract_backtest_dates
    assert _extract_backtest_dates("백테스트를 2020년 1월 부터 2025년 12월 까지 해줘") == \
        ("2020-01-01", "2025-12-31")
    assert _extract_backtest_dates("2020년 3월부터 백테스트") == ("2020-03-01", None)
    assert _extract_backtest_dates("2025년 6월까지 보고싶어") == (None, "2025-06-30")
    assert _extract_backtest_dates("2020년 3월만 테스트") == ("2020-03-01", "2020-03-31")


def test_extract_backtest_dates_year_month_day():
    from engine.nl_parser import _extract_backtest_dates
    assert _extract_backtest_dates("2020년 1월 15일부터 2025년 12월 31일까지") == \
        ("2020-01-15", "2025-12-31")
    # 달력상 불가능한 날짜는 추측하지 않는다(미인식 → LLM/되묻기 위임)
    assert _extract_backtest_dates("2024년 2월 30일부터") == (None, None)


def test_modify_year_month_backtest_range_resolves_deterministically():
    # 사고 입력 그대로 — 수정 fast-path가 LLM 없이 시작/종료일을 모두 반영하고
    # 기존 필드는 보존한다.
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_dump()
    parsed = _modify_rule_based("백테스트를 2020년 1월 부터 2025년 12월 까지 해줘", prev)
    assert parsed is not None
    assert parsed.backtest_start_date == "2020-01-01"
    assert parsed.backtest_end_date == "2025-12-31"
    assert parsed.max_positions == prev["max_positions"]


def test_non_bucket_backtest_years_resolve_to_relative_dates():
    # 버킷(1y/3y/5y)이 아닌 '백테스트 N년'은 오늘 기준 명시적 날짜 범위로 변환된다.
    # 버그: 2년이 버킷에 없어 침묵 무시되고 기본 5y로 요약되던 문제.
    from datetime import date
    from engine.nl_parser import _extract_backtest_dates, _extract_backtest_period
    today = date.today()
    start, end = _extract_backtest_dates("백테스트는 2년으로 설정하고")
    assert end == today.isoformat()
    assert start == today.replace(year=today.year - 2).isoformat()
    # 버킷 연수(1/3/5)는 여전히 상대 기간 버킷으로 처리되어 날짜로 바뀌지 않는다.
    assert _extract_backtest_period("백테스트 5년") == "5y"
    assert _extract_backtest_dates("백테스트 5년") == (None, None)


def test_modify_two_year_backtest_with_take_profit_resolves_deterministically():
    # 후속 수정 '백테스트는 2년으로 설정하고, 30% 익절을 설정 해줘'가 LLM 폴백 없이
    # 결정론 경로에서 명시 날짜 + 익절을 함께 적용한다(stale 5y 요약 버그 회귀 방지).
    from datetime import date
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_dump()
    parsed = _modify_rule_based("백테스트는 2년으로 설정하고, 30% 익절을 설정 해줘", prev)
    assert parsed is not None
    today = date.today()
    assert parsed.backtest_start_date == today.replace(year=today.year - 2).isoformat()
    assert parsed.backtest_end_date == today.isoformat()
    assert parsed.take_profit_pct == 30.0


def test_modify_increase_positions_resolves_deterministically():
    # '종목을 10개로 늘려줘'는 조정 동사('늘려') 잔여 때문에 LLM으로 새던 단순 수정이다.
    # 조정 동사를 필러로 인정해 결정론 fast-path가 max_positions를 바로 반영해야 한다.
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy()
    prev.max_positions = 8
    parsed = _modify_rule_based("종목을 10개로 늘려줘", prev.model_dump())
    assert parsed is not None
    assert parsed.max_positions == 10


def test_resolve_coach_context_risk_attributes_bare_percentage():
    # 코치가 특정 리스크 필드 설정을 권한 뒤 사용자가 필드 없이 '10%'처럼 답하면, 그 값을
    # 코치가 물은 필드로 귀속한다(프론트 inferPendingRiskChange 이관, FR-STR-019e).
    from engine.nl_parser import resolve_coach_context_risk as resolve

    # 트레일링만 언급한 코치 + 필드 없는 답
    assert resolve(
        "15%로 정해줘", "트레일링 스탑, 최고가에서 몇 % 내려오면 팔지 정할까요?", {"stop_loss_pct": 12},
    ) == ("trailing_stop_pct", 15.0)
    # 손절(설정됨)·익절(미설정)을 함께 언급 → 미설정인 익절로 귀속
    assert resolve(
        "30%로 설정해줘", "손절 12%는 유지, 익절 비율 설정을 추천드립니다.",
        {"stop_loss_pct": 12, "take_profit_pct": None},
    ) == ("take_profit_pct", 30.0)


def test_resolve_coach_context_risk_skips_when_not_applicable():
    from engine.nl_parser import resolve_coach_context_risk as resolve

    # 프롬프트가 리스크 필드를 명시 → 일반 파서가 처리하므로 추론 안 함
    assert resolve("익절 30%로 바꿔줘", "익절 비율을 추천드립니다", {}) is None
    # 코치 문장 없음
    assert resolve("30%로 설정해줘", None, {}) is None
    # 퍼센트 없음
    assert resolve("그렇게 해줘", "익절 추천", {}) is None
    # 코치가 리스크 필드를 특정 못 함(둘 다 미설정) → 귀속 불가
    assert resolve(
        "30%로 설정해줘", "손절이나 익절 설정을 추천드립니다.",
        {"stop_loss_pct": None, "take_profit_pct": None},
    ) is None


def test_modify_dividend_ev_ebitda_filters_resolve_deterministically():
    # 배당수익률/배당성향/배당성장률/EV·EBITDA는 추출은 되는데 잔여 차감 어휘(cue)에서 빠져
    # '배당수익률' 등이 미인식 잔여로 남아 fast-path가 LLM(수십 초)으로 새던 버그. 기존 필터를
    # 보존한 채 결정론 병합돼야 한다(재무 조건 추가 되묻기 칩이 무상태로 완결되는 계약의 근거).
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_copy(update={
        "fundamental_filters": [{"metric": "roe_or_gpa", "operator": ">=", "value": 10.0}],
    }).model_dump()
    for prompt, metric, value in [
        ("배당수익률 5% 이상", "dividend_yield", 5.0),
        ("배당성향 30% 이상", "payout_rate", 30.0),
        ("배당성장률 10% 이상", "dividend_growth", 10.0),
        ("EV/EBITDA 8배 이하", "ev_ebitda", 8.0),
    ]:
        parsed = _modify_rule_based(prompt, prev)
        assert parsed is not None, f"{prompt!r}이 fast-path로 안 풀림(LLM 위임)"
        by_metric = {f.metric: f.value for f in parsed.fundamental_filters}
        assert by_metric.get("roe_or_gpa") == 10.0, "기존 ROE 필터 소실"
        assert by_metric.get(metric) == value


def test_modify_numeric_sector_resolves_deterministically():
    # '2차전지 섹터로 바꿔줘'는 숫자 제거가 어휘 차감보다 먼저라 '차전지' 잔여가 남아
    # LLM 경로(수십 초)로 새던 단순 수정이다. 결정론 fast-path가 바로 반영해야 한다.
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_dump()
    parsed = _modify_rule_based("2차전지 섹터로 바꿔줘", prev)
    assert parsed is not None
    assert parsed.sector == "이차전지"


def test_backtest_months_window_resolves_to_relative_dates():
    # '백테스트 N개월'(N≥12)도 연 단위와 동일하게 오늘 기준 명시 날짜로 변환된다.
    # 연 단위만 처리하고 개월은 침묵 무시되던 비대칭(프론트는 개월 인식) 보완.
    from datetime import date
    from engine.nl_parser import (
        _backtest_period_state,
        _extract_backtest_dates,
        _subtract_months,
    )
    today = date.today()
    for prompt, months in [("백테스트 24개월", 24), ("백테스트 18개월로 해줘", 18), ("36개월 백테스트", 36)]:
        start, end = _extract_backtest_dates(prompt)
        assert end == today.isoformat()
        assert start == _subtract_months(today, months).isoformat()
        assert _backtest_period_state(prompt) == "parsed"


def test_backtest_months_below_one_year_stay_unresolved():
    # 12개월 미만은 백테스트 최소 기간(1년) 미달 → 날짜 변환 않고 unresolved로 남는다.
    from engine.nl_parser import _backtest_period_state, _extract_backtest_dates
    assert _extract_backtest_dates("백테스트 6개월") == (None, None)
    assert _backtest_period_state("백테스트 6개월") == "unresolved"


def test_subtract_months_clamps_month_end():
    # 말일 클램프(3/31 - 1개월 → 2/28) 및 연 경계 처리.
    from datetime import date
    from engine.nl_parser import _subtract_months
    assert _subtract_months(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert _subtract_months(date(2026, 1, 15), 13) == date(2024, 12, 15)


def test_apply_prompt_overrides_preserves_dates_when_unmentioned():
    # 날짜 미언급 후속 수정에서는 기존 명시 기간을 보존한다(수정 모드 보호).
    base = make_base_strategy().model_copy(
        update={"backtest_start_date": "2002-01-01", "backtest_end_date": "2005-12-31"}
    )
    parsed = _apply_prompt_overrides(base, "초기자금 2천만원으로 바꿔줘")
    assert parsed.backtest_start_date == "2002-01-01"
    assert parsed.backtest_end_date == "2005-12-31"


def test_backtest_dates_flow_into_request_and_change_strategy_id():
    from engine.strategy_converter import to_backtest_request, compute_strategy_id
    base = make_base_strategy()
    dated = base.model_copy(update={"backtest_start_date": "2002-01-01", "backtest_end_date": "2005-12-31"})

    req = to_backtest_request(dated, resolve_symbols=False)
    assert req["startDate"] == "2002-01-01"
    assert req["endDate"] == "2005-12-31"

    # 명시 기간이 다르면 strategy_id(캐시 키)도 달라져 과거 결과가 잘못 재사용되지 않는다.
    assert compute_strategy_id(base) != compute_strategy_id(dated)
    # 명시 기간이 없으면 canonical DSL에 키가 없어 기존 전략 해시는 불변.
    assert "startDate" not in to_backtest_request(base, resolve_symbols=False)


def test_large_cap_overrides_plain_kospi():
    # "코스피 대형주"는 코스피 전체가 아니라 대형주(KOSPI200)로 좁혀야 한다.
    parsed = _apply_prompt_overrides(make_base_strategy(), "코스피 대형주로 해줘")

    assert parsed.universe == ["KOSPI200"]


def test_kosdaq_large_cap_does_not_mismap_to_kospi200():
    # 코스닥 단독 맥락의 대형주는 KOSPI200으로 매핑하면 시장이 바뀌는 오매핑이다.
    # 코스닥 대형주 전용 유니버스가 없으므로 KOSDAQ을 유지한다.
    assert _extract_explicit_universe("코스닥 대형주 중에서 골라줘") == ["KOSDAQ"]


def test_apply_prompt_overrides_extracts_take_profit_from_profit_sell_phrase():
    parsed = _apply_prompt_overrides(make_base_strategy(), "수익 10% 이상시 매도")

    assert parsed.take_profit_pct == 10.0
    assert parsed.exit_signals == []


def test_apply_prompt_overrides_extracts_stop_loss_from_drawdown_sell_phrase():
    parsed = _apply_prompt_overrides(make_base_strategy(), "10% 이상 하락 시 매도")

    assert parsed.stop_loss_pct == 10.0
    assert parsed.exit_signals == []


def test_match_risk_pct_picks_closest_when_two_pcts_in_one_clause():
    # "-15%에 손절하고 30%에 익절" — 손절이 더 먼 30%(익절 값)를 끌어오면 안 된다.
    overrides = extract_risk_field_overrides(
        "코스닥에서 최근 1주일동안 가장 많이 오른 10개 종목을 골라서 "
        "-15%에 손절하고 30%에 익절 하는 전략"
    )
    assert overrides["stop_loss_pct"] == 15.0
    assert overrides["take_profit_pct"] == 30.0


@pytest.mark.parametrize(
    "text, sl, tp",
    [
        # [회귀] 손절·익절이 같은 %값들을 두고 다툴 때 오귀속되던 케이스들.
        # 순서(키워드-값 / 값-키워드), 조사(에/로)와 무관하게 각 %가 올바른 필드에 귀속돼야 한다.
        ("10% 손절 20% 익절", 10.0, 20.0),   # 값-키워드(숫자 먼저): 손절이 익절의 20%를 훔치던 버그
        ("손절 10% 익절 20%", 10.0, 20.0),   # 키워드-값
        ("익절 30% 손절 15%", 15.0, 30.0),   # 중간 %(30)를 손절이 훔쳐 익절이 비던 버그
        ("15%에 손절 30%로 익절", 15.0, 30.0),  # 조사(에/로)가 gap을 부풀려 먼 값을 잡던 버그
        ("20% 익절 10% 손절", 10.0, 20.0),
    ],
)
def test_sl_tp_joint_assignment_no_misattribution(text, sl, tp):
    overrides = extract_risk_field_overrides(text)
    assert overrides.get("stop_loss_pct") == sl
    assert overrides.get("take_profit_pct") == tp


def test_apply_prompt_overrides_keeps_technical_exit_when_explicitly_requested():
    base = make_base_strategy().model_copy(
        update={
            "exit_signals": [
                TechnicalSignal(
                    indicator="cci",
                    signal_type="sell",
                    period=14,
                    operator=">=",
                    value=100,
                )
            ]
        }
    )

    parsed = _apply_prompt_overrides(base, "CCI 100 이상이거나 수익 10% 이상시 매도")

    assert parsed.take_profit_pct == 10.0
    assert [signal.indicator for signal in parsed.exit_signals] == ["cci"]


def test_apply_prompt_overrides_restores_fundamental_filter_dropped_by_llm():
    # [회귀] "ROE 10% 이상인 종목 중 골든크로스가 나오면 매수"처럼 재무 조건과 기술 신호가
    # 한 문장에 섞이면 LLM이 명시된 ROE 값을 통째로 빠뜨리고 이미 준 값을 되묻는 사고가
    # 실측됐다(레드팀 QA). fundamental_filters가 비어 있어도, 원문에 명시적 숫자가 있으면
    # 결정적 추출이 되살려야 한다.
    base = make_base_strategy().model_copy(
        update={
            "entry_signals": [
                TechnicalSignal(indicator="ma_crossover", signal_type="buy", short_period=5, long_period=20)
            ],
            "exit_signals": [
                TechnicalSignal(indicator="ma_crossover", signal_type="sell", short_period=5, long_period=20)
            ],
        }
    )

    parsed = _apply_prompt_overrides(
        base,
        "KOSPI에서 ROE 10% 이상인 종목 중 골든크로스가 나오면 매수하고 "
        "데드크로스가 나오면 매도하도록 설정해 주세요.",
    )

    assert parsed.fundamental_filters == [
        FundamentalFilter(metric="roe_or_gpa", operator=">=", value=10.0)
    ]


def test_apply_prompt_overrides_does_not_fabricate_filter_for_vague_metric_mention():
    # 값 없는 정성 표현("ROE 조건을 충족")은 추출되지 않아야 한다 — 임의 임계값을
    # 지어내면 안 되고, 되묻기(다른 경로)에 맡겨져야 한다.
    parsed = _apply_prompt_overrides(
        make_base_strategy(), "KOSPI에서 ROE 조건을 충족하는 종목을 매수해 주세요."
    )

    assert parsed.fundamental_filters == []


def test_validate_signals_drops_exit_signal_without_exit_context_cue():
    # [회귀] "20일 EMA가 60일 EMA 위에 있고 ... 진입"만 말하고 청산은 전혀 언급하지
    # 않았는데도, LLM이 같은 EMA 지표로 청산 신호를 지어내는 환각이 실측됐다
    # (매도/청산 등 방향전환 cue가 원문에 전혀 없는 케이스).
    signals = [
        TechnicalSignal(indicator="ema", signal_type="sell", short_period=20, long_period=60)
    ]

    validated = _validate_signals(
        signals,
        "20일 EMA가 60일 EMA 위에 있고 최근 거래대금이 30일 평균보다 높은 경우만 진입하는 "
        "방식으로 설계해 주세요. 손절 -7%, 익절 +24%.",
        context="exit",
    )

    assert validated == []


def test_validate_signals_keeps_exit_signal_with_explicit_sell_verb():
    signals = [
        TechnicalSignal(indicator="ema", signal_type="sell", short_period=20, long_period=60)
    ]

    validated = _validate_signals(
        signals, "20일 EMA가 60일 EMA 아래로 내려오면 매도해 주세요.", context="exit"
    )

    assert [signal.indicator for signal in validated] == ["ema"]


def test_apply_prompt_overrides_drops_hallucinated_exit_signal_end_to_end():
    # #47 실측 재현: 청산을 전혀 언급하지 않은 프롬프트에 LLM이 EMA 청산 신호를 지어낸
    # 경우, _apply_prompt_overrides가 이를 걸러내야 한다.
    base = make_base_strategy().model_copy(
        update={
            "entry_signals": [
                TechnicalSignal(indicator="ema", signal_type="buy", short_period=20, long_period=60)
            ],
            "exit_signals": [
                TechnicalSignal(indicator="ema", signal_type="sell", short_period=20, long_period=60)
            ],
        }
    )

    parsed = _apply_prompt_overrides(
        base,
        "KOSDAQ 중 시가총액 2000억 원 이상 종목에서 20일 EMA가 60일 EMA 위에 있고 최근 "
        "거래대금이 30일 평균보다 높은 경우만 진입하는 방식으로 설계해 주세요. "
        "주간 리밸런싱, 최대 9종목, 손절 -7%, 익절 +24% 조건으로 부탁드립니다.",
    )

    assert parsed.exit_signals == []


# ─── 기술적 신호 deterministic 추출 테스트 ────────────────────────────────────


def test_extract_golden_cross_entry():
    entry, exit_ = _extract_technical_signals("골든크로스 나오면 매수")
    assert len(entry) == 1
    assert entry[0].indicator == "ma_crossover"
    assert entry[0].signal_type == "buy"
    assert entry[0].short_period == 5
    assert entry[0].long_period == 20
    assert len(exit_) == 0


def test_extract_dead_cross_exit():
    entry, exit_ = _extract_technical_signals("데드크로스 나오면 매도")
    assert len(exit_) == 1
    assert exit_[0].indicator == "ma_crossover"
    assert exit_[0].signal_type == "sell"


def test_extract_golden_and_dead_cross_together():
    prompt = "골든크로스가 나오면 매수하고, 반대로 데드크로스가 나오면 매도"
    entry, exit_ = _extract_technical_signals(prompt)
    assert any(s.indicator == "ma_crossover" and s.signal_type == "buy" for s in entry)
    assert any(s.indicator == "ma_crossover" and s.signal_type == "sell" for s in exit_)


def test_extract_ma_crossover_from_natural_description():
    """'단기 이동평균선이 장기 이동평균선을 위로 뚫을 때' 같은 자연어 표현"""
    prompt = (
        "단기 이동평균선이 장기 이동평균선을 위로 뚫을 때 매수하고, "
        "반대로 매도하는 식으로 만들어 주세요"
    )
    entry, exit_ = _extract_technical_signals(prompt)
    assert any(s.indicator == "ma_crossover" and s.signal_type == "buy" for s in entry)
    assert any(s.indicator == "ma_crossover" and s.signal_type == "sell" for s in exit_)


def test_extract_custom_ma_periods():
    entry, exit_ = _extract_technical_signals("5일/20일 골든크로스 매수, 데드크로스 매도")
    assert entry[0].short_period == 5
    assert entry[0].long_period == 20


def test_extract_ma_periods_with_word_separator():
    # [회귀] "20일 이동평균이 60일 이동평균" — 두 'N일' 사이 분리어('이동평균이', 5자+)가
    # 길어 기간 추출 정규식(gap 4자)이 실패 → 명시한 20/60을 무시하고 기본값 5/20으로
    # 조용히 파싱되던 버그. 사용자가 말한 기간을 그대로 잡아야 한다.
    entry, _ = _extract_technical_signals(
        "20일 이동평균이 60일 이동평균을 상향 돌파하면 매수하는 골든크로스 전략"
    )
    ma = next(s for s in entry if s.indicator == "ma_crossover")
    assert ma.short_period == 20
    assert ma.long_period == 60


def test_extract_rsi_buy_sell():
    entry, exit_ = _extract_technical_signals("RSI 30 이하에서 매수, RSI 70 이상에서 매도")
    assert any(s.indicator == "rsi" and s.signal_type == "buy" for s in entry)
    assert any(s.indicator == "rsi" and s.signal_type == "sell" for s in exit_)


def test_extract_rsi_buy_from_oversold_rebound_phrase():
    """'RSI가 30 아래로 내려갔다가 다시 올라오는 종목만 매수' 같은 구어체 반등 표현에서 RSI 매수 추출

    조사('RSI가')와 '아래로'(이하 대신), 반등 서술('내려갔다가 다시 올라오는')이 섞여도
    LLM/정규식이 놓치던 케이스 — 전략요약에 RSI 진입 신호가 누락되던 버그 재현.
    """
    entry, _ = _extract_technical_signals(
        "RSI가 30 아래로 내려갔다가 다시 올라오는 종목만 매수"
    )
    rsi_buy = [s for s in entry if s.indicator == "rsi" and s.signal_type == "buy"]
    assert len(rsi_buy) == 1
    assert rsi_buy[0].value == 30.0
    assert rsi_buy[0].operator == "<="
    # '다시 올라오는'은 단순 과매도 진입이 아니라 30선 재돌파 반등 → mode='rebound'
    assert rsi_buy[0].mode == "rebound"


def test_extract_rsi_plain_threshold_has_no_rebound_mode():
    """단순 'RSI 30 이하 매수'(과매도 구간 진입)는 반등이 아니므로 mode가 없어야 한다.
    반등 표현과 구분되지 않으면 진입 타이밍(돌파 vs 구간)이 뒤바뀐다."""
    entry, _ = _extract_technical_signals("RSI 30 이하면 매수")
    rsi_buy = [s for s in entry if s.indicator == "rsi" and s.signal_type == "buy"]
    assert len(rsi_buy) == 1
    assert rsi_buy[0].mode is None


def test_extract_rsi_sell_with_particle():
    """'RSI가 70 이상이면 매도' — 조사가 끼어도 RSI 매도 추출"""
    _, exit_ = _extract_technical_signals("RSI가 70 이상이면 매도")
    rsi_sell = [s for s in exit_ if s.indicator == "rsi" and s.signal_type == "sell"]
    assert len(rsi_sell) == 1
    assert rsi_sell[0].value == 70.0


def test_extract_rsi_sell_does_not_bridge_entry_value_across_sentence():
    """진입 RSI(50 이상)와 청산 RSI(45 아래)가 서로 다른 문장(마침표로 분리)에 있을 때,
    청산 임계값 추출이 마침표를 넘어 진입 문장의 숫자(50)를 잘못 끌어오면 안 된다 — 절 경계를
    쉼표([^,])만으로 판정해 마침표를 넘어 '정리'까지 이어붙이던 실사용 버그 재현
    (청산 배지가 진입과 동일한 'RSI 50 이상'으로 표시됨)."""
    _, exit_ = _extract_technical_signals(
        "RSI가 50 이상으로 올라온 경우만 진입하고 싶습니다. "
        "단순 반등보다 추세가 실제로 붙는 종목만 고르려는 의도입니다. "
        "RSI가 다시 45 아래로 밀리면 정리하고, 최대 10종목으로 부탁드립니다."
    )
    rsi_sell = [s for s in exit_ if s.indicator == "rsi" and s.signal_type == "sell"]
    assert len(rsi_sell) == 0


def test_extract_stochastic_buy_sell():
    """스토캐스틱 과매도 매수 / 과매수 매도를 규칙 기반으로 추출(엔진·컨버터는 이미 지원).

    구조적 프롬프트는 LLM 없이 규칙 기반으로만 파싱되는데 스토캐스틱 추출기가 없어
    배지에서 조용히 누락되던 미탐지 버그 재현(qa_parse_badges_1000).
    """
    entry, exit_ = _extract_technical_signals(
        "스토캐스틱 20 이하에서 매수, 스토캐스틱 80 이상에서 매도"
    )
    buy = [s for s in entry if s.indicator == "stochastic" and s.signal_type == "buy"]
    sell = [s for s in exit_ if s.indicator == "stochastic" and s.signal_type == "sell"]
    assert len(buy) == 1 and buy[0].value == 20.0 and buy[0].operator == "<="
    assert len(sell) == 1 and sell[0].value == 80.0 and sell[0].operator == ">="


def test_extract_cci_buy_with_negative_value():
    """'CCI -100 이하에서 매수' — 음수 값을 포함해 CCI 매수 추출."""
    entry, _ = _extract_technical_signals("CCI -100 이하에서 매수")
    cci_buy = [s for s in entry if s.indicator == "cci" and s.signal_type == "buy"]
    assert len(cci_buy) == 1
    assert cci_buy[0].value == -100.0
    assert cci_buy[0].operator == "<="


def test_ranking_keeps_explicit_day_holding_period():
    """모멘텀 랭킹과 '20일 보유 후 매도'를 함께 쓰면 명시적 보유기간을 보존한다.

    랭킹 회전을 리밸런싱으로 구동하며 보유기간을 비우던 로직이, 일 단위로 명시된
    고정 보유기간까지 삭제해 배지에서 사라지던 문제(qa_parse_badges_1000) 회귀 방지.
    """
    parsed = _parse_rule_based_strategy(
        "코스피200에서 최근 60거래일 수익률 상위 종목을 20일 보유 후 매도, 최대 5종목"
    )
    assert parsed is not None
    assert parsed.ranking_metric == "return"
    assert parsed.hold_period_days == 20


def test_ranking_still_drops_momentum_lookback_as_holding_period():
    """반대로 '최근 3개월 오른' 같은 모멘텀 룩백은 보유기간으로 잡지 않는다(기존 동작 유지)."""
    parsed = _parse_rule_based_strategy(
        "최근 3개월 동안 많이 오른 모멘텀 상위 종목을 매수, 분기마다 리밸런싱, 최대 10종목"
    )
    assert parsed is not None
    assert parsed.ranking_metric == "return"
    assert parsed.hold_period_days is None


def test_extract_bollinger_bands():
    entry, exit_ = _extract_technical_signals("볼린저밴드 하단에서 매수, 상단에서 매도")
    assert any(s.indicator == "bollinger_bands" and s.signal_type == "buy" for s in entry)
    assert any(s.indicator == "bollinger_bands" and s.signal_type == "sell" for s in exit_)


def test_merge_signals_no_duplicates():
    existing = [TechnicalSignal(indicator="ma_crossover", signal_type="buy")]
    extracted = [
        TechnicalSignal(indicator="ma_crossover", signal_type="buy"),  # duplicate
        TechnicalSignal(indicator="rsi", signal_type="buy", period=14, operator="<=", value=30),
    ]
    merged = _merge_signals(existing, extracted)
    assert len(merged) == 2
    indicators = [(s.indicator, s.signal_type) for s in merged]
    assert ("ma_crossover", "buy") in indicators
    assert ("rsi", "buy") in indicators


def test_merge_signals_replaces_existing_breakout_with_deterministic_period():
    existing = [TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=52)]
    extracted = [TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=252)]

    merged = _merge_signals(existing, extracted)

    assert len(merged) == 1
    assert merged[0].indicator == "breakout"
    assert merged[0].lookback_period == 252


def test_full_prompt_golden_dead_cross_with_stoploss():
    """스크린샷과 동일한 프롬프트: 골든크로스 매수 + 데드크로스 매도 + 손절 -8%"""
    prompt = (
        "차트를 보니까 단기 이동평균선이 장기 이동평균선을 위로 뚫을 때 많이들 들어간다고 하더라고요. "
        "KOSPI 종목 중 골든크로스가 나오면 매수하고, 반대로 데드크로스가 나오면 매도하는 식으로 "
        "간단하게 만들어 주세요. 종목은 최대 10개, 손절은 -8%로 부탁드립니다."
    )
    # LLM이 데드크로스를 놓친 상황을 시뮬레이션
    base = make_base_strategy().model_copy(
        update={
            "entry_signals": [
                TechnicalSignal(indicator="ma_crossover", signal_type="buy", short_period=5, long_period=20)
            ],
            "exit_signals": [],  # LLM이 데드크로스를 빠뜨림
            "stop_loss_pct": 8.0,
        }
    )
    parsed = _apply_prompt_overrides(base, prompt)

    # 데드크로스가 exit_signals에 추가되어야 함
    exit_indicators = [(s.indicator, s.signal_type) for s in parsed.exit_signals]
    assert ("ma_crossover", "sell") in exit_indicators, (
        f"데드크로스(ma_crossover sell)가 exit_signals에 없음: {exit_indicators}"
    )
    # 골든크로스도 entry에 유지
    entry_indicators = [(s.indicator, s.signal_type) for s in parsed.entry_signals]
    assert ("ma_crossover", "buy") in entry_indicators
    # KOSPI 유니버스
    assert parsed.universe == ["KOSPI"]
    assert parsed.stop_loss_pct == 8.0


def test_full_prompt_extracts_stop_loss_with_korean_particle_from_empty_base():
    prompt = (
        "차트를 보니까 단기 이동평균선이 장기 이동평균선을 위로 뚫을 때 많이들 들어간다고 하더라고요. "
        "KOSPI 종목 중 골든크로스가 나오면 매수하고, 반대로 데드크로스가 나오면 매도하는 식으로 "
        "간단하게 만들어 주세요. 종목은 최대 10개, 손절은 -8%로 부탁드립니다."
    )

    parsed = _apply_prompt_overrides(make_base_strategy(), prompt)

    assert parsed.stop_loss_pct == 8.0
    assert parsed.universe == ["KOSPI"]
    assert ("ma_crossover", "buy") in [(s.indicator, s.signal_type) for s in parsed.entry_signals]
    assert ("ma_crossover", "sell") in [(s.indicator, s.signal_type) for s in parsed.exit_signals]


def test_extract_breakout_uses_252_for_52_week_high_phrase():
    entry, exit_ = _extract_technical_signals("52주 신고가 돌파시 매수")

    assert len(exit_) == 0
    assert len(entry) == 1
    assert entry[0].indicator == "breakout"
    assert entry[0].lookback_period == 252


def test_extract_breakout_keeps_day_period_for_52_day_high_phrase():
    entry, _ = _extract_technical_signals("52일 신고가 돌파시 매수")

    assert len(entry) == 1
    assert entry[0].lookback_period == 52


def test_extract_breakout_keeps_day_period_for_60_day_high_phrase():
    entry, _ = _extract_technical_signals("60일 신고가 돌파시 매수")

    assert len(entry) == 1
    assert entry[0].lookback_period == 60


def test_extract_breakout_recognizes_box_breakout_entry():
    """'박스권을 위로 돌파' 표현을 신고가 키워드 없이도 breakout 매수로 인식한다."""
    entry, _ = _extract_technical_signals(
        "최근 한 달 박스권을 위로 돌파하는 종목만 매수하고 싶어요"
    )

    assert len(entry) == 1
    assert entry[0].indicator == "breakout"
    assert entry[0].signal_type == "buy"
    assert entry[0].lookback_period == 20


def test_extract_breakout_recognizes_n_day_high_breakout_entry():
    """'20일 고점을 넘기는 날 매수' → breakout 매수, lookback 20."""
    entry, _ = _extract_technical_signals("20일 고점을 넘기는 날 매수")

    assert len(entry) == 1
    assert entry[0].indicator == "breakout"
    assert entry[0].lookback_period == 20


def test_extract_breakout_recognizes_box_breakdown_exit():
    """'다시 박스 안으로 내려오면 매도' → breakout 매도(박스 하단 이탈)."""
    _, exit_ = _extract_technical_signals("다시 박스 안으로 내려오면 매도해 주세요")

    assert len(exit_) == 1
    assert exit_[0].indicator == "breakout"
    assert exit_[0].signal_type == "sell"


def test_rule_based_parses_box_breakout_full_prompt():
    """스크린샷 프롬프트: 박스권 돌파 매수 + 박스 이탈 매도가 진입/청산 신호로 잡힌다."""
    prompt = (
        "복잡한 지표는 아직 어려워서 최근 한 달 동안 가격이 갇혀 있던 박스권을 위로 "
        "돌파하는 종목만 사고 싶어요. KOSPI 종목 중 20일 고점을 넘기는 날 매수하고 "
        "다시 박스 안으로 내려오면 매도해 주세요. 최대 8종목, 손절은 -7%로 부탁드립니다."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert ("breakout", "buy") in [(s.indicator, s.signal_type) for s in parsed.entry_signals]
    assert ("breakout", "sell") in [(s.indicator, s.signal_type) for s in parsed.exit_signals]
    assert parsed.universe == ["KOSPI"]
    assert parsed.max_positions == 8
    assert parsed.stop_loss_pct == 7.0


def test_apply_prompt_overrides_replaces_wrong_breakout_period_from_existing_signal():
    base = make_base_strategy().model_copy(
        update={
            "entry_signals": [
                TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=52)
            ]
        }
    )

    parsed = _apply_prompt_overrides(base, "52주 신고가 돌파시 매수")

    assert len(parsed.entry_signals) == 1
    assert parsed.entry_signals[0].indicator == "breakout"
    assert parsed.entry_signals[0].lookback_period == 252


# ─── take_profit / stop_loss 자연어 패턴 테스트 ─────────────────────────────


def test_take_profit_korean_natural_phrase():
    """'수익이 10% 이상 날때도 매도 해줘' 같은 자연어에서 익절 추출"""
    parsed = _apply_prompt_overrides(make_base_strategy(), "수익이 10% 이상 날때도 매도 해줘")

    assert parsed.take_profit_pct == 10.0


def test_take_profit_with_particle():
    """'수익 15% 이상이면 매도' — 조사 변형"""
    parsed = _apply_prompt_overrides(make_base_strategy(), "수익 15% 이상이면 매도해줘")

    assert parsed.take_profit_pct == 15.0


def test_stop_loss_negative_percent():
    """'-10% 매도' 같은 마이너스 표기에서 손절 추출"""
    parsed = _apply_prompt_overrides(make_base_strategy(), "-10% 되면 매도해줘")

    assert parsed.stop_loss_pct == 10.0


def test_stop_loss_korean_shorthand():
    """'손절 8%' 축약형에서 손절 추출"""
    parsed = _apply_prompt_overrides(make_base_strategy(), "손절 8%로 설정해줘")

    assert parsed.stop_loss_pct == 8.0


def test_take_profit_korean_shorthand():
    """'익절 20%' 축약형에서 익절 추출"""
    parsed = _apply_prompt_overrides(make_base_strategy(), "익절 20%로 해줘")

    assert parsed.take_profit_pct == 20.0


def test_take_profit_from_colloquial_sell_verb():
    """'수익이 15% 나면 팔고' — '매도/청산' 대신 구어체 '팔고'에서 익절 추출

    전략요약에서 익절이 누락되던 버그 재현 — '팔고/팔아/팔면' 등 구어체 매도 동사 미인식.
    """
    parsed = _apply_prompt_overrides(make_base_strategy(), "수익이 15% 나면 팔고 싶어")

    assert parsed.take_profit_pct == 15.0


def test_nl_strategy_parser_defaults_point_to_qwen35_4b(monkeypatch):
    # 환경변수(NL_MLX_MODEL)가 없을 때의 코드 기본값을 검증한다.
    monkeypatch.delenv("NL_MLX_MODEL", raising=False)
    monkeypatch.delenv("NL_OLLAMA_MODEL", raising=False)
    parser = NLStrategyParser()

    assert parser.mlx_model == "mlx-community/Qwen3.5-4B-4bit"
    assert parser.model_32b == "mlx-community/Qwen3.5-4B-4bit"
    # Ollama 기본값은 레지스트리에 존재하는 9B급 모델 qwen3:8b
    assert parser.ollama_model == "qwen3:8b"
    assert parser.ollama_model_32b == "qwen3:8b"


def test_nl_strategy_parser_env_overrides_mlx_model(monkeypatch):
    # 환경변수로 모델을 교체할 수 있어야 한다(코드 수정 없이 9B 등으로 A/B).
    monkeypatch.setenv("NL_MLX_MODEL", "mlx-community/Qwen3.5-9B-OptiQ-4bit")
    assert NLStrategyParser().mlx_model == "mlx-community/Qwen3.5-9B-OptiQ-4bit"


def test_nl_strategy_parser_model_log_label_uses_actual_model_name(monkeypatch):
    monkeypatch.delenv("NL_MLX_MODEL", raising=False)
    parser = NLStrategyParser()

    assert parser._model_log_label(parser.mlx_model) == "Qwen3.5-4B"
    assert parser._model_log_label("mlx-community/Qwen2.5-7B-Instruct-4bit") == "Qwen2.5-7B"


def test_rule_based_strategy_parses_explicit_value_hold_prompt_without_llm():
    parsed = _parse_rule_based_strategy("pbr 1이하 per 7이하 종목을 10개 사서 1년간 보유하는 전략")

    assert parsed is not None
    assert [(f.metric, f.operator, f.value) for f in parsed.fundamental_filters] == [
        ("pbr", "<=", 1.0),
        ("per", "<=", 7.0),
    ]
    assert parsed.max_positions == 10
    assert parsed.hold_period_days == 252
    assert parsed.rebalancing_period == "yearly"


def test_rule_based_strategy_parses_pbr_particle_unit_prompt_without_llm():
    prompt = (
        "주식은 아직 초보라서 너무 복잡한 조건 말고 이해하기 쉬운 전략으로 하고 싶어요. "
        "KOSPI 대형주 중에서 PBR이 1배 이하인 종목만 골라서 8종목 정도 나눠 사고, "
        "한 번 사면 최소 6개월은 들고 가고 싶습니다. "
        "큰 손실은 무서우니 -12% 손절만 넣어 주세요."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    # "KOSPI 대형주"는 코스피 전체가 아니라 대형주(표준 대형주 지수 KOSPI200)로 좁혀야 한다.
    assert parsed.universe == ["KOSPI200"]
    assert [(f.metric, f.operator, f.value) for f in parsed.fundamental_filters] == [
        ("pbr", "<=", 1.0),
    ]
    assert parsed.max_positions == 8
    assert parsed.hold_period_days == 126
    assert parsed.stop_loss_pct == 12.0


def test_rule_based_strategy_parses_trading_value_particle_prompt_without_llm():
    # '거래대금이 100억 원 이상' 처럼 조사(이/가)가 붙은 표현도 trading_value 필터로 인식해야 한다.
    prompt = (
        "KOSPI에서 PBR이 1배 이하면서 하루 거래대금이 100억 원 이상으로 활발한 종목만 골라 "
        "6종목 정도 나눠 사고 싶습니다. 한 번 사면 3개월은 들고 가고, 손절은 -8%로 부탁드립니다."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert [(f.metric, f.operator, f.value) for f in parsed.fundamental_filters] == [
        ("pbr", "<=", 1.0),
        ("trading_value", ">=", 100.0),
    ]
    assert parsed.max_positions == 6
    assert parsed.hold_period_days == 63
    assert parsed.stop_loss_pct == 8.0


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("roe를 5% 이상으로 해줘", ("roe_or_gpa", ">=", 5.0)),
        ("pbr을 1.2 이하로 바꿔줘", ("pbr", "<=", 1.2)),
        ("per를 10 이하로", ("per", "<=", 10.0)),
        ("부채비율을 50% 미만으로", ("debt_ratio", "<", 50.0)),
        ("시가총액을 1조 이상으로", ("market_cap", ">=", 10000.0)),
        ("거래대금을 30억 이상으로", ("trading_value", ">=", 30.0)),
    ],
)
def test_extract_fundamental_filters_allows_object_particle(prompt, expected):
    # 회귀: 'roe를 5%'처럼 지표와 숫자 사이 목적격 조사(을/를)가 끼면 필터를 통째로 놓쳐
    # 수정이 무시되고(빈 추출) 분류가 OFF_TOPIC으로 새던 버그.
    filters = _extract_fundamental_filters(prompt)
    assert [(f.metric, f.operator, f.value) for f in filters] == [expected]


def test_extract_fundamental_filters_keeps_operator_after_won_suffix():
    # '억원'의 '원'이 끼어들어도 뒤따르는 연산자(이하/이상)를 놓치지 않아야 한다.
    # 기존 (억|억원) 교대는 '억'을 먼저 잡아 '원'이 남고 연산자 매칭이 깨졌다.
    filters = _extract_fundamental_filters(
        "거래대금 100억원 이하, 시가총액 5000억원 이상 종목"
    )

    assert [(f.metric, f.operator, f.value) for f in filters] == [
        ("market_cap", ">=", 5000.0),
        ("trading_value", "<=", 100.0),
    ]


def test_extract_fundamental_filters_converts_jo_unit_to_eok():
    # '조' 단위는 억원 단위로 환산해야 한다(1조 = 10000억). 소수 '조'도 지원.
    filters = _extract_fundamental_filters(
        "시가총액이 1조 이상, 거래대금 1.5조 이상 종목"
    )

    assert [(f.metric, f.operator, f.value) for f in filters] == [
        ("market_cap", ">=", 10000.0),
        ("trading_value", ">=", 15000.0),
    ]


def test_extract_fundamental_filters_sums_jo_eok_combo():
    # '2조5000억'처럼 조+억 콤보는 (조×10000)+억으로 합산해야 한다.
    filters = _extract_fundamental_filters(
        "시가총액 2조5000억 이상, 거래대금 1조2000억 이하 종목"
    )

    assert [(f.metric, f.operator, f.value) for f in filters] == [
        ("market_cap", ">=", 25000.0),
        ("trading_value", "<=", 12000.0),
    ]


def test_extract_initial_capital_ignores_trading_value_filter_amount():
    # '거래대금 50억' 같은 펀더멘털 필터 수치를 초기자금으로 오인하면 안 된다(기본값 유지).
    assert (
        _extract_initial_capital("일평균 거래대금 50억 원 이상 종목만 편입")
        == 10_000_000.0
    )


def test_extract_initial_capital_ignores_market_cap_filter_amount():
    # '시가총액 1000억'도 초기자금으로 오인하면 안 된다.
    assert (
        _extract_initial_capital("시가총액 1000억 이상, 거래대금 50억 이상")
        == 10_000_000.0
    )


def test_extract_initial_capital_still_reads_explicit_capital():
    # 실제 초기자금 표현은 그대로 추출해야 한다(필터 제거가 자본금까지 지우면 안 됨).
    assert (
        _extract_initial_capital("거래대금 50억 이상 종목, 초기자금 1억으로 백테스트")
        == 100_000_000.0
    )


def test_rule_based_strategy_multifactor_prompt_keeps_default_capital():
    # 사용자 멀티팩터 프롬프트에는 초기자금 언급이 없으므로 기본값이어야 한다.
    prompt = (
        "KOSPI/KOSDAQ 공통 유니버스에서 ROE 12% 이상, PBR 1.5배 이하, "
        "최근 60거래일 상대강도 상위 30%, 일평균 거래대금 50억 원 이상 조건을 "
        "동시에 만족하는 종목만 편입해 주세요. 매주 점수를 재산출해 상위 12종목 "
        "동일 비중 포트폴리오를 유지하고, 20일선 이탈 또는 손절 -8% 도달 시 청산하도록 구성해 주세요."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert parsed.initial_capital == 10_000_000.0


def test_extract_technical_signals_catches_ema_crossover_entry():
    # "20일 EMA가 60일 EMA 위에 있고" → ema 골든(단기 20 / 장기 60) 진입 신호.
    entry, exit_ = _extract_technical_signals(
        "20일 EMA가 60일 EMA 위에 있고 진입"
    )
    ema = [s for s in entry if s.indicator == "ema"]
    assert len(ema) == 1
    assert (ema[0].signal_type, ema[0].short_period, ema[0].long_period) == ("buy", 20, 60)


def test_extract_technical_signals_catches_ema_cross_below_exit():
    # "20일 EMA가 60일 EMA 아래로" → ema 데드(청산) 신호.
    entry, exit_ = _extract_technical_signals(
        "20일 EMA가 60일 EMA 아래로 내려오면 매도"
    )
    ema = [s for s in exit_ if s.indicator == "ema"]
    assert len(ema) == 1
    assert (ema[0].signal_type, ema[0].short_period, ema[0].long_period) == ("sell", 20, 60)


def test_extract_technical_signals_catches_trading_value_above_average():
    # "거래대금이 30일 평균보다 높은" → volume_spike(period=30) 진입 신호.
    entry, exit_ = _extract_technical_signals(
        "최근 거래대금이 30일 평균보다 높은 경우만 진입"
    )
    vol = [s for s in entry if s.indicator == "volume_spike"]
    assert len(vol) == 1
    assert (vol[0].signal_type, vol[0].period) == ("buy", 30)


def test_extract_fundamental_filters_ignores_moving_average_window():
    # '거래대금이 30일 평균보다' 의 '30일'을 '30억' 정적 필터로 오인하면 안 된다.
    filters = _extract_fundamental_filters(
        "거래대금이 30일 평균보다 높은 종목"
    )
    assert [(f.metric, f.operator, f.value) for f in filters] == []


def test_rule_based_strategy_multifactor_ema_prompt_catches_entry_signals():
    # 사용자 멀티팩터 프롬프트: EMA 크로스 + 거래대금 평균 상회 진입 신호를 모두 잡아야 한다.
    prompt = (
        "KOSDAQ 중 시가총액 2000억 원 이상 종목에서 매출 성장률이 양호하고 PBR이 과도하게 "
        "높지 않은 기업만 먼저 고르고 싶습니다. 이후 20일 EMA가 60일 EMA 위에 있고 최근 "
        "거래대금이 30일 평균보다 높은 경우만 진입하는 방식으로 설계해 주세요. "
        "주간 리밸런싱, 최대 9종목, 손절 -7%, 익절 +24% 조건으로 부탁드립니다."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    entry_indicators = {s.indicator for s in parsed.entry_signals}
    assert "ema" in entry_indicators
    assert "volume_spike" in entry_indicators
    # '거래대금 30일'이 거래대금 >= 30억 정적 필터로 새지 않아야 한다.
    assert [(f.metric, f.operator, f.value) for f in parsed.fundamental_filters] == [
        ("market_cap", ">=", 2000.0),
    ]


def test_rule_based_strategy_parses_technical_prompt_with_risk_without_llm():
    parsed = _parse_rule_based_strategy("KOSPI 종목 중 골든크로스 매수, 데드크로스 매도, 손절 8%")

    assert parsed is not None
    assert parsed.universe == ["KOSPI"]
    assert [(s.indicator, s.signal_type) for s in parsed.entry_signals] == [("ma_crossover", "buy")]
    assert [(s.indicator, s.signal_type) for s in parsed.exit_signals] == [("ma_crossover", "sell")]
    assert parsed.stop_loss_pct == 8.0


def test_rule_based_strategy_parses_52_week_high_volume_spike_prompt_without_llm():
    prompt = (
        "뉴스에 자주 나오는 강한 종목을 짧게 타보는 전략을 써보고 싶어요. "
        "KOSDAQ에서 52주 신고가를 새로 만들고 거래량도 평소보다 확 늘어난 종목이 나오면 들어가고, "
        "너무 오래 끌지는 말고 20일 정도 지나면 정리해 주세요. "
        "최대 6종목, 손절은 -10%로 해주세요."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert parsed.universe == ["KOSDAQ"]
    assert [(s.indicator, s.signal_type) for s in parsed.entry_signals] == [
        ("breakout", "buy"),
        ("volume_spike", "buy"),
    ]
    assert parsed.entry_signals[0].lookback_period == 252
    assert parsed.entry_signals[1].period == 20
    assert parsed.hold_period_days == 20
    assert parsed.max_positions == 6
    assert parsed.stop_loss_pct == 10.0


def test_rule_based_strategy_parses_price_above_ma_with_volume_prompt_without_llm():
    # '종가가 20일선 위 + 거래량 평균보다 증가'를 진입 신호로, '20일선 아래로'를 청산으로 잡아야 한다.
    # 가격 vs MA는 ma_crossover(short=1, long=N)로 표현된다(close_1_sma=close).
    prompt = (
        "추세가 살아 있는 종목만 안전하게 사고 싶어요. "
        "KOSDAQ에서 종가가 20일 이동평균선 위에 있고 거래량이 최근 평균보다 늘어난 종목만 "
        "5개 정도 매수해 주세요. 20일선 아래로 내려오면 정리하고, 손절은 -7%로 설정해 주세요."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert parsed.universe == ["KOSDAQ"]
    assert [(s.indicator, s.signal_type, s.short_period, s.long_period) for s in parsed.entry_signals] == [
        ("ma_crossover", "buy", 1, 20),
        ("volume_spike", "buy", None, None),
    ]
    assert [(s.indicator, s.signal_type, s.short_period, s.long_period) for s in parsed.exit_signals] == [
        ("ma_crossover", "sell", 1, 20),
    ]
    assert parsed.max_positions == 5
    assert parsed.stop_loss_pct == 7.0


def test_extract_technical_signals_volume_rising_phrasings():
    # 거래량 증가 표현은 문구가 다양해도(급증/폭발/터짐/평균보다 늘…) 모두 volume_spike로 잡아야 한다.
    for phrase in ["거래량 급증", "거래량이 터진", "거래량이 평소보다 늘어난", "거래량이 최근 평균보다 증가한"]:
        entry, _ = _extract_technical_signals(f"{phrase} 종목 매수")
        assert [s.indicator for s in entry] == ["volume_spike"], phrase


def test_extract_technical_signals_golden_cross_keeps_default_periods():
    # 가격 vs MA(short=1) 추가가 골든/데드 크로스 기본 기간(5/20)을 침범하지 않아야 한다.
    entry, exit_ = _extract_technical_signals("골든크로스 매수, 데드크로스 매도")
    assert [(s.indicator, s.short_period, s.long_period) for s in entry] == [("ma_crossover", 5, 20)]
    assert [(s.indicator, s.short_period, s.long_period) for s in exit_] == [("ma_crossover", 5, 20)]


def test_rule_based_strategy_falls_back_for_ambiguous_prompt():
    assert _parse_rule_based_strategy("좋은 저평가 전략 만들어줘") is None


def _base_strategy() -> ParsedStrategy:
    return ParsedStrategy(
        description="x",
        universe=["KOSPI"],
        fundamental_filters=[],
        entry_signals=[],
        exit_signals=[],
        max_positions=10,
        hold_period_days=None,
        rebalancing_period="none",
        stop_loss_pct=12.0,
        take_profit_pct=None,
        trailing_stop_pct=None,
        max_mdd_limit_pct=None,
        backtest_period="5y",
        initial_capital=10000000.0,
    )


def test_apply_overrides_extracts_take_profit_from_profit_realization_phrasing():
    # "수익 실현"은 매도 동사가 없어도 익절로 인식되어야 한다 (사용자 후속 수정 시나리오)
    result = _apply_prompt_overrides(_base_strategy(), "30% 상승시 수익 실현 하게 설정해")
    assert result.take_profit_pct == 30.0
    assert result.stop_loss_pct == 12.0  # 기존 손절은 유지


def test_apply_overrides_extracts_take_profit_from_target_profit_phrasing():
    result = _apply_prompt_overrides(_base_strategy(), "목표 수익 25%로 설정")
    assert result.take_profit_pct == 25.0


def test_apply_overrides_extracts_take_profit_with_ratio_word_between():
    # "익절 비율 30%"처럼 '익절'과 숫자 사이에 '비율'이 끼어도 추출되어야 한다(추천 칩 문구)
    result = _apply_prompt_overrides(_base_strategy(), "익절 비율 30% 설정")
    assert result.take_profit_pct == 30.0


def test_apply_overrides_extracts_take_profit_with_ratio_and_josa():
    result = _apply_prompt_overrides(_base_strategy(), "익절 비율을 20%로 설정해줘")
    assert result.take_profit_pct == 20.0


@pytest.mark.parametrize(
    "prompt",
    [
        "익절 30%",
        "익절 비율 30%",
        "익절률 30%",
        "익절 비율을 30%로 설정해줘",
        "익절 기준 30%",
        "수익 실현 30%로 설정",
        "30% 상승시 수익 실현 하게 설정해",
        "목표 수익 30%",
        "목표 수익률 30%",
        "30% 수익시 매도",
        "30% 수익 나면 팔아",
    ],
)
def test_take_profit_phrasings_all_extract_30(prompt):
    # 표현이 달라도 '익절류 키워드 + 30%'면 한 규칙으로 전부 추출되어야 한다
    assert _apply_prompt_overrides(_base_strategy(), prompt).take_profit_pct == 30.0


@pytest.mark.parametrize(
    "prompt",
    [
        "손절 8%",
        "손절 비율 8%",
        "손절률 8%",
        "손절을 8%로 설정해줘",
        "손절 기준 8%",
        "-8% 손절",
        "8% 하락시 매도",
        "8% 하락하면 청산",
    ],
)
def test_stop_loss_phrasings_all_extract_8(prompt):
    base = _base_strategy()
    base = base.model_copy(update={"stop_loss_pct": None})
    assert _apply_prompt_overrides(base, prompt).stop_loss_pct == 8.0


@pytest.mark.parametrize(
    "prompt",
    [
        "트레일링 스탑 15%",
        "트레일링 15%",
        "트레일링 비율 15%",
        "트레일링을 15%로 설정해줘",
        "최고가 대비 15% 하락",
    ],
)
def test_trailing_stop_phrasings_all_extract_15(prompt):
    assert _apply_prompt_overrides(_base_strategy(), prompt).trailing_stop_pct == 15.0


def test_multi_field_prompt_associates_each_pct_to_correct_field():
    base = _base_strategy().model_copy(update={"stop_loss_pct": None})
    result = _apply_prompt_overrides(base, "손절 10% 익절 20%")
    assert result.stop_loss_pct == 10.0
    assert result.take_profit_pct == 20.0


def test_blocker_prevents_cross_field_false_match():
    # "손절 없이 익절 10%"에서 손절에 10%가 잘못 붙으면 안 된다(블로커로 차단)
    base = _base_strategy().model_copy(update={"stop_loss_pct": None})
    result = _apply_prompt_overrides(base, "손절 없이 익절 10%")
    assert result.take_profit_pct == 10.0
    assert result.stop_loss_pct is None


def test_extract_risk_field_overrides_is_single_source_of_truth():
    # API가 프론트에 넘겨줄 '결정적으로 바뀐 리스크 필드' 단일 진실 소스.
    assert extract_risk_field_overrides("익절 비율 30% 설정") == {"take_profit_pct": 30.0}
    assert extract_risk_field_overrides("30% 수익시 매도") == {"take_profit_pct": 30.0}
    assert extract_risk_field_overrides("10% 하락시 매도") == {"stop_loss_pct": 10.0}
    assert extract_risk_field_overrides("트레일링 비율 15%") == {"trailing_stop_pct": 15.0}
    assert extract_risk_field_overrides("손절 8% 익절 20%") == {
        "stop_loss_pct": 8.0,
        "take_profit_pct": 20.0,
    }
    # 삭제 의도는 None으로 표현
    assert extract_risk_field_overrides("익절 빼줘") == {"take_profit_pct": None}
    # 리스크 변경이 없으면 빈 dict
    assert extract_risk_field_overrides("보유 기간 20일로 바꿔줘") == {}


def test_synthesize_risk_overrides_supplements_parser_when_regex_misses():
    # "10% 이익 나면 팔아줘"는 결정적 추출이 놓치지만(구어체 "이익"), 파서(LLM)가
    # take_profit_pct=10으로 해석했다면 그 결과를 override로 surface 해야 한다.
    # 그렇지 않으면 프론트의 결정적 게이트에 막혀 익절이 화면에서 사라진다.
    previous = {"stop_loss_pct": 10.0, "take_profit_pct": None, "trailing_stop_pct": None}
    parsed = ParsedStrategy(description="x", stop_loss_pct=10.0, take_profit_pct=10.0)
    assert extract_risk_field_overrides("10% 이익 나면 팔아줘") == {}  # 결정적은 못 잡음
    assert synthesize_risk_overrides("10% 이익 나면 팔아줘", parsed, previous) == {
        "take_profit_pct": 10.0
    }


def test_synthesize_risk_overrides_keeps_deterministic_and_ignores_unchanged():
    # 결정적 추출이 잡은 값은 그대로 우선, 안 바뀐 필드는 override에 넣지 않는다.
    previous = {"stop_loss_pct": 10.0, "take_profit_pct": None, "trailing_stop_pct": None}
    # 비-리스크 수정: 파서가 previous risk를 보존 → override 없음
    parsed_no_change = ParsedStrategy(description="x", stop_loss_pct=10.0)
    assert synthesize_risk_overrides("종목 5개로 바꿔줘", parsed_no_change, previous) is None
    # 결정적으로 잡히는 명시 표현은 그대로
    parsed_tp = ParsedStrategy(description="x", stop_loss_pct=10.0, take_profit_pct=30.0)
    assert synthesize_risk_overrides("익절 30%", parsed_tp, previous) == {"take_profit_pct": 30.0}


def test_match_risk_pct_keyword_and_number_not_adjacent():
    assert _match_risk_pct("익절비율을30%로", _TAKE_PROFIT_CUE, _TAKE_PROFIT_BLOCK) == 30.0
    assert _match_risk_pct("30%수익실현", _TAKE_PROFIT_CUE, _TAKE_PROFIT_BLOCK) == 30.0
    assert _match_risk_pct("손절비율8%", _STOP_LOSS_CUE, _STOP_LOSS_BLOCK) == 8.0
    assert _match_risk_pct("트레일링비율15%", _TRAILING_CUE, _TRAILING_BLOCK) == 15.0
    assert _match_risk_pct("손절없이익절10%", _STOP_LOSS_CUE, _STOP_LOSS_BLOCK) is None


def test_parse_rule_based_returns_strategy_without_touching_model(monkeypatch):
    parser = NLStrategyParser()

    def fail_if_model_called(_prompt):
        raise AssertionError("parse_rule_based must never invoke the LLM")

    monkeypatch.setattr(parser, "_parse_mlx", fail_if_model_called)

    parsed = parser.parse_rule_based(
        "KOSPI 종목 중 골든크로스 매수, 데드크로스 매도, 손절 8%"
    )

    assert parsed is not None
    assert parsed.stop_loss_pct == 8.0


def test_parse_rule_based_returns_none_for_ambiguous_prompt():
    parser = NLStrategyParser()
    assert parser.parse_rule_based("좋은 저평가 전략 만들어줘") is None


def test_parse_mlx_uses_injected_inference_gate(monkeypatch):
    """[드리프트 방지] main이 주입한 MLX 추론 게이트가 LLM 구조화 생성(_parse_mlx)을
    감싼다 — parse()의 단일 하이브리드 경로를 공유하면서도 MLX 단일 추론 직렬화가 유지된다."""
    import json as _json

    parser = NLStrategyParser(backend="mlx")
    events: list[str] = []

    class _Gate:
        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, *_args):
            events.append("exit")
            return False

    parser.inference_gate = _Gate
    monkeypatch.setattr(parser, "_init_mlx", lambda: None)
    parser._generator = lambda prompt, max_tokens: (
        events.append("generate") or _json.dumps({"description": "x"})
    )

    parsed = parser._parse_mlx("아무 입력")

    assert parsed.description == "x"
    assert events == ["enter", "generate", "exit"]  # 생성이 게이트 안에서 실행됨


def test_parse_mlx_without_gate_is_noop(monkeypatch):
    """게이트 미주입(테스트·ollama)이면 게이트 없이 그대로 동작한다."""
    import json as _json

    parser = NLStrategyParser(backend="mlx")
    monkeypatch.setattr(parser, "_init_mlx", lambda: None)
    parser._generator = lambda prompt, max_tokens: _json.dumps({"description": "y"})

    assert parser._parse_mlx("입력").description == "y"


def test_parse_uses_rule_based_fast_path_before_model(monkeypatch):
    parser = NLStrategyParser()

    def fail_if_model_called(_prompt):
        raise AssertionError("LLM path should not be called for explicit fast-path prompts")

    monkeypatch.setattr(parser, "_parse_mlx", fail_if_model_called)

    parsed = parser.parse("RSI 30 이하에서 매수, RSI 70 이상에서 매도, 최대 5종목")

    assert [(s.indicator, s.signal_type) for s in parsed.entry_signals] == [("rsi", "buy")]
    assert [(s.indicator, s.signal_type) for s in parsed.exit_signals] == [("rsi", "sell")]
    assert parsed.max_positions == 5


def test_parse_model_json_response_ignores_trailing_im_end_tokens():
    raw = """{
  "description": "우리 AI 모델 전략",
  "universe": ["KOSDAQ"],
  "fundamental_filters": [],
  "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 70}],
  "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell", "threshold": 70}],
  "max_positions": 8,
  "hold_period_days": 10,
  "rebalancing_period": "none",
  "stop_loss_pct": 9.0,
  "take_profit_pct": null,
  "trailing_stop_pct": null,
  "max_mdd_limit_pct": null,
  "backtest_period": "5y",
  "initial_capital": 10000000.0,
  "execution_timing": "next_open",
  "fee_rate": 0.015,
  "slippage_rate": 0.05
}<|im_end|><|im_end|>"""

    parsed = _parse_model_json_response(raw, ParsedStrategy)

    assert parsed.universe == ["KOSDAQ"]
    assert parsed.max_positions == 8
    assert parsed.stop_loss_pct == 9.0


def test_parse_model_json_response_extracts_diff_object_from_prefixed_text():
    raw = """assistant
{"description": null, "universe": ["KOSDAQ"], "fundamental_filters": null, "entry_signals": null, "exit_signals": null, "max_positions": 8, "hold_period_days": 10, "rebalancing_period": null, "stop_loss_pct": 9.0, "take_profit_pct": null, "trailing_stop_pct": null, "max_mdd_limit_pct": null, "backtest_period": null, "initial_capital": null, "execution_timing": null, "fee_rate": null, "slippage_rate": null}</s>"""

    parsed = _parse_model_json_response(raw, ParsedStrategyDiff)

    assert parsed.universe == ["KOSDAQ"]
    assert parsed.max_positions == 8
    assert parsed.hold_period_days == 10


def test_parse_model_json_response_repairs_tail_truncated_object():
    raw = """{
  "description": "PBR 전략",
  "universe": ["KOSPI200"],
  "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
  "entry_signals": [],
  "exit_signals": [],
  "max_positions": 10,
  "hold_period_days": 20,
  "rebalancing_period": "none",
  "stop_loss_pct": 8.0,
  "take_profit_pct": null,
  "trailing_stop_pct": null,
  "max_mdd_limit_pct": null,
  "backtest_period": "5y",
  "initial_capital": 10000000.0,
  "execution_timing": "next_open",
  "fee_rate": 0.015,
  "slippage_rate": 0.05"""

    parsed = _parse_model_json_response(raw, ParsedStrategy)

    assert parsed.fundamental_filters[0].metric == "pbr"
    assert parsed.hold_period_days == 20
    assert parsed.stop_loss_pct == 8.0


def test_parse_falls_back_when_model_returns_incomplete_json(monkeypatch):
    parser = NLStrategyParser(backend="mlx")

    def incomplete_model_output(_user_input):
        raise ValueError("Incomplete JSON object in model output")

    monkeypatch.setattr(parser, "_parse_mlx", incomplete_model_output)

    parsed = parser.parse("KOSPI200에서 ROE 10 이상 종목을 최대 7개 매수하고 손절 8%")

    assert parsed.universe == ["KOSPI200"]
    assert parsed.max_positions == 7
    assert parsed.fundamental_filters[0].metric == "roe_or_gpa"
    assert parsed.stop_loss_pct == 8.0


def test_parse_modification_trusts_llm_universe_diff_without_keyword_gate(monkeypatch):
    parser = NLStrategyParser(backend="mlx")
    previous = {
        "description": "KOSPI PBR strategy",
        "universe": ["KOSPI"],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        "entry_signals": [],
        "exit_signals": [],
        "max_positions": 8,
        "hold_period_days": 126,
        "rebalancing_period": "none",
        "stop_loss_pct": 12,
        "take_profit_pct": None,
        "trailing_stop_pct": None,
        "max_mdd_limit_pct": None,
        "backtest_period": "5y",
        "initial_capital": 10_000_000,
        "execution_timing": "next_open",
        "fee_rate": 0.015,
        "slippage_rate": 0.05,
    }

    def hallucinated_diff(_user_input, _previous):
        return ParsedStrategyDiff(
            universe=["KOSPI200"],
            trailing_stop_pct=15,
        )

    monkeypatch.setattr(parser, "_modify_mlx", hallucinated_diff)

    parsed = parser.parse_modification(
        "트레일링 15% 추가하고 전체 구성을 자연스럽게 조정해줘", previous
    )

    assert parsed.universe == ["KOSPI200"]
    assert parsed.trailing_stop_pct == 15
    assert parsed.stop_loss_pct == 12


def test_parse_modification_changes_universe_when_prompt_explicitly_requests_it(monkeypatch):
    parser = NLStrategyParser(backend="mlx")
    previous = {
        "description": "KOSPI PBR strategy",
        "universe": ["KOSPI"],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
        "entry_signals": [],
        "exit_signals": [],
        "max_positions": 8,
        "hold_period_days": 126,
        "rebalancing_period": "none",
        "stop_loss_pct": 12,
        "take_profit_pct": None,
        "trailing_stop_pct": None,
        "max_mdd_limit_pct": None,
        "backtest_period": "5y",
        "initial_capital": 10_000_000,
        "execution_timing": "next_open",
        "fee_rate": 0.015,
        "slippage_rate": 0.05,
    }

    def universe_diff(_user_input, _previous):
        return ParsedStrategyDiff(universe=["KOSPI200"])

    monkeypatch.setattr(parser, "_modify_mlx", universe_diff)

    parsed = parser.parse_modification("KOSPI200으로 바꿔줘", previous)

    assert parsed.universe == ["KOSPI200"]


_MODIFY_PREVIOUS = {
    "description": "KOSPI200 PBR strategy",
    "universe": ["KOSPI200"],
    "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
    "entry_signals": [],
    "exit_signals": [],
    "max_positions": 8,
    "hold_period_days": 126,
    "rebalancing_period": "none",
    "stop_loss_pct": 12,
    "take_profit_pct": None,
    "trailing_stop_pct": None,
    "max_mdd_limit_pct": None,
    "backtest_period": "5y",
    "initial_capital": 10_000_000,
    "execution_timing": "next_open",
    "fee_rate": 0.015,
    "slippage_rate": 0.05,
}


def test_parse_modification_simple_field_uses_rule_based_not_llm(monkeypatch):
    """단순 필드 수정('30% 익절 설정')은 LLM 호출 없이 결정론 fast-path로 처리된다.

    회귀: 이 입력이 LLM/RAG 경로로 가서 num_ctx 초과·의존성 누락으로 죽던 버그.
    """
    parser = NLStrategyParser(backend="ollama")

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("단순 수정은 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)

    parsed = parser.parse_modification("30% 익절 설정", dict(_MODIFY_PREVIOUS))

    assert parsed.take_profit_pct == 30
    assert parsed.stop_loss_pct == 12  # 기존 값 보존
    assert parsed.universe == ["KOSPI200"]


@pytest.mark.parametrize(
    "mod, field, expected",
    [
        ("종목 20개로 바꿔줘", "max_positions", 20),
        ("손절 5%로 바꿔줘", "stop_loss_pct", 5.0),
        ("분기 리밸런싱으로 바꿔줘", "rebalancing_period", "quarterly"),
        ("백테스트 3년으로", "backtest_period", "3y"),
    ],
)
def test_rule_based_modification_preserves_technical_signals(mod, field, expected):
    # [회귀] 규칙 기반 fast-path 수정이 신호 재검증을 돌려, 언급 안 된 기존 RSI 진입/청산
    # 신호를 통째로 떨구던 버그("종목 20개로" 한 번에 전략의 매매 조건이 사라짐).
    prev = dict(_MODIFY_PREVIOUS)
    prev["entry_signals"] = [{"indicator": "rsi", "signal_type": "buy", "period": 14, "operator": "<=", "value": 30.0}]
    prev["exit_signals"] = [{"indicator": "rsi", "signal_type": "sell", "period": 14, "operator": ">=", "value": 70.0}]
    parser = NLStrategyParser(backend="ollama")
    parser._modify_ollama = lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM 호출 금지"))
    parsed = parser.parse_modification(mod, prev)
    # 기존 진입/청산 신호가 보존돼야 한다.
    assert [(s.indicator, s.value) for s in parsed.entry_signals] == [("rsi", 30.0)]
    assert [(s.indicator, s.value) for s in parsed.exit_signals] == [("rsi", 70.0)]
    # 요청한 필드는 바뀌어야 한다.
    assert getattr(parsed, field) == expected


def test_parse_modification_delete_uses_rule_based(monkeypatch):
    """리스크 필드 삭제('손절 빼줘')도 fast-path가 LLM 없이 처리한다."""
    parser = NLStrategyParser(backend="ollama")

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("삭제 수정은 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)

    parsed = parser.parse_modification("손절 빼줘", dict(_MODIFY_PREVIOUS))

    assert parsed.stop_loss_pct is None


def test_parse_modification_removes_rebalancing_with_delete_verb(monkeypatch):
    """회귀: '리밸런싱 빼줘'가 제거 의도로 인식돼 rebalancing_period가 none이 된다.

    삭제 감지 정규식이 '없/안하/끄/중단'만 보고 '빼/제거/삭제/지워'를 놓쳐, 기존
    monthly 리밸런싱이 그대로 남던 버그.
    """
    parser = NLStrategyParser(backend="ollama")

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("리밸런싱 삭제 수정은 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)

    previous = {**_MODIFY_PREVIOUS, "rebalancing_period": "monthly"}
    parsed = parser.parse_modification("리밸런싱 빼줘", previous)

    assert parsed.rebalancing_period == "none"


def test_parse_modification_removes_rebalancing_on_llm_path_when_diff_is_null(monkeypatch):
    """회귀: rule-based가 못 잡아 LLM 경로로 빠지고 LLM이 rebalancing_period=null('변경없음')을
    내도, 삭제 의도가 있으면 none으로 보정한다.

    diff 병합은 null을 '변경없음'으로 무시하는데, 리밸런싱의 '끔'은 null이 아니라 enum 'none'
    이라 삭제 보정 블록이 손절/익절/트레일링만 보고 리밸런싱을 빠뜨려 monthly가 남던 버그.
    """
    parser = NLStrategyParser(backend="ollama")

    def _llm_returns_null_rebalance(_user_input, _previous):
        # LLM은 제거 의도를 변경없음(null)으로 오인 — 가장 흔한 실패 모드.
        return ParsedStrategyDiff(rebalancing_period=None)

    monkeypatch.setattr(parser, "_modify_ollama", _llm_returns_null_rebalance)

    previous = {**_MODIFY_PREVIOUS, "rebalancing_period": "monthly"}
    # '변동성 큰 종목'이라는 미인식 잔여가 있어 rule-based는 None → LLM 경로로 위임된다.
    parsed = parser.parse_modification("변동성 큰 종목은 리밸런싱에서 제거", previous)

    assert parsed.rebalancing_period == "none"


@pytest.mark.parametrize("prompt", ["보유기간 빼줘", "보유기간 없애줘"])
def test_parse_modification_removes_hold_period_with_delete_verb(monkeypatch, prompt):
    """회귀: '보유기간 빼줘'가 해제로 인식돼 hold_period_days가 null이 된다.

    해제 상태가 null인데 LLM diff 병합이 null을 '변경없음'으로 무시하던 클래스 버그
    (리밸런싱과 동형). rule-based 결정론으로 처리해 LLM도 거치지 않는다."""
    parser = NLStrategyParser(backend="ollama")

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("보유기간 해제는 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)

    previous = {**_MODIFY_PREVIOUS, "hold_period_days": 252}
    parsed = parser.parse_modification(prompt, previous)

    assert parsed.hold_period_days is None


@pytest.mark.parametrize("prompt", ["MDD 제한 빼줘", "최대낙폭 한도 없애줘"])
def test_parse_modification_removes_mdd_limit_with_delete_verb(monkeypatch, prompt):
    """회귀: 'MDD 제한 빼줘'가 해제로 인식돼 max_mdd_limit_pct가 null이 된다(보유기간과 동형)."""
    parser = NLStrategyParser(backend="ollama")

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("MDD 한도 해제는 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)

    previous = {**_MODIFY_PREVIOUS, "max_mdd_limit_pct": 20.0}
    parsed = parser.parse_modification(prompt, previous)

    assert parsed.max_mdd_limit_pct is None


def test_parse_modification_does_not_clear_hold_from_unrelated_delete(monkeypatch):
    """오탐 가드: '보유'가 보유기간이 아닌 맥락(보유 중)에서 다른 필드 삭제 시 hold가 유지된다."""
    parser = NLStrategyParser(backend="ollama")

    def _llm_diff(_user_input, _previous):
        return ParsedStrategyDiff()  # 변경없음

    monkeypatch.setattr(parser, "_modify_ollama", _llm_diff)

    previous = {**_MODIFY_PREVIOUS, "hold_period_days": 252}
    parsed = parser.parse_modification("20종목 보유 중인데 손절만 빼줘", previous)

    assert parsed.hold_period_days == 252  # 보유기간은 건드리지 않음
    assert parsed.stop_loss_pct is None  # 손절만 해제


def test_parse_modification_complex_request_defers_to_llm(monkeypatch):
    """인식 못 한 복합·모호한 수정은 LLM 경로로 위임된다."""
    parser = NLStrategyParser(backend="ollama")
    called = {"llm": False}

    def _llm_diff(_user_input, _previous):
        called["llm"] = True
        return ParsedStrategyDiff(max_positions=3)

    monkeypatch.setattr(parser, "_modify_ollama", _llm_diff)

    parsed = parser.parse_modification("변동성 낮은 종목 3개로 바꿔줘", dict(_MODIFY_PREVIOUS))

    assert called["llm"] is True
    assert parsed.max_positions == 3


def test_llm_modification_diff_is_authoritative_for_risk_fields(monkeypatch):
    """Keyword gates must not revert structured risk decisions from the fallback LLM."""
    parser = NLStrategyParser(backend="ollama")

    def _llm_diff(_user_input, _previous):
        return ParsedStrategyDiff(take_profit_pct=30, trailing_stop_pct=30)

    monkeypatch.setattr(parser, "_modify_ollama", _llm_diff)
    prev = dict(_MODIFY_PREVIOUS)
    prev["trailing_stop_pct"] = None

    parsed = parser.parse_modification("익절 비율을 30%로 설정해줘", prev)
    assert parsed.take_profit_pct == 30
    assert parsed.trailing_stop_pct == 30


def test_extract_risk_overrides_colloquial_sell_conjugation():
    # [회귀] "50% 이상 수익이 나면 주식을 파는 걸로 하자" — 매도 동사의 ㄹ탈락 관형형
    # '파는'이 _SELL_V에 없어 결정적 추출이 침묵하던 버그. '돌파는'은 오매칭하지 않는다.
    from engine.nl_parser import extract_risk_field_overrides
    assert extract_risk_field_overrides(
        "50% 이상 수익이 나면 주식을 파는 걸로 하자"
    ) == {"take_profit_pct": 50.0}
    assert extract_risk_field_overrides("20일 신고가 돌파는 유지해줘") == {}


def test_llm_modification_preserves_unknown_stop_loss_typo(monkeypatch):
    """Preserve the LLM's stop-loss interpretation for the previously unknown typo '선절'."""
    parser = NLStrategyParser(backend="ollama")
    called = {"llm": False}

    def _llm_diff(_user_input, _previous):
        called["llm"] = True
        return ParsedStrategyDiff(stop_loss_pct=15, take_profit_pct=30)

    monkeypatch.setattr(parser, "_modify_ollama", _llm_diff)
    monkeypatch.setattr("engine.modify_rag.record_example", lambda *_args, **_kwargs: False)
    prev = dict(_MODIFY_PREVIOUS)
    prev["stop_loss_pct"] = None

    parsed = parser.parse_modification("15% 선절 30% 익절", prev)

    assert called["llm"] is True
    assert parsed.stop_loss_pct == 15
    assert parsed.take_profit_pct == 30


def test_ollama_modification_prompt_assigns_final_semantic_judgment(monkeypatch):
    """The dynamic Ollama prompt must include typo tolerance and final-decision responsibility."""
    parser = NLStrategyParser(backend="ollama")
    captured = {}

    monkeypatch.setattr(
        "engine.modify_rag.build_dynamic_modify_prompt",
        lambda *_args, **_kwargs: "base prompt",
    )

    def _capture(system_prompt, _user_message, _model_cls):
        captured["system_prompt"] = system_prompt
        return ParsedStrategyDiff()

    monkeypatch.setattr(parser, "_structured_ollama", _capture)

    parser._modify_ollama("15% 선절 30% 익절", dict(_MODIFY_PREVIOUS))

    assert "오타" in captured["system_prompt"]
    assert "최종 의미 판단" in captured["system_prompt"]


def test_llm_all_null_diff_is_not_reinterpreted_by_postprocessing(monkeypatch):
    """Do not inject deterministic meaning after the LLM returns an all-null diff."""
    parser = NLStrategyParser(backend="ollama")

    def _llm_diff(_user_input, _previous):
        return ParsedStrategyDiff()  # LLM이 완전히 놓친 최악 케이스

    monkeypatch.setattr(parser, "_modify_ollama", _llm_diff)
    prev = dict(_MODIFY_PREVIOUS)
    prev["stop_loss_pct"] = 10.0
    prev["take_profit_pct"] = None

    parsed = parser.parse_modification("50% 이상 수익이 나면 주식을 파는 걸로 하자", prev)
    assert parsed.take_profit_pct is None
    assert parsed.stop_loss_pct == 10.0


def test_llm_modification_diff_is_authoritative_across_domains(monkeypatch):
    """Apply structured fallback LLM fields without a source-keyword allowlist."""
    parser = NLStrategyParser(backend="ollama")

    def _llm_diff(_user_input, _previous):
        return ParsedStrategyDiff(stop_loss_pct=10, max_positions=99)

    monkeypatch.setattr(parser, "_modify_ollama", _llm_diff)
    prev = dict(_MODIFY_PREVIOUS)
    prev["max_positions"] = 8

    parsed = parser.parse_modification("손절 기준과 전체 구성을 자연스럽게 바꿔줘", prev)
    assert parsed.stop_loss_pct == 10
    assert parsed.max_positions == 99


def test_rule_based_modification_keeps_seed_capital_change(monkeypatch):
    """The deterministic fast path still handles explicit seed-capital changes."""
    parser = NLStrategyParser(backend="ollama")

    def _llm_diff(_user_input, _previous):
        return ParsedStrategyDiff(initial_capital=5_000_000)

    monkeypatch.setattr(parser, "_modify_ollama", _llm_diff)
    parsed = parser.parse_modification("시드 500으로 바꿔줘", dict(_MODIFY_PREVIOUS))
    assert parsed.initial_capital == 5_000_000


def test_parse_modification_adds_explicit_fundamental_filters_without_llm(monkeypatch):
    """매수 기준이 없던 전략에 '숫자가 명시된 펀더멘털 조건'을 추가하는 수정은 LLM 없이 처리한다.

    회귀: 'PBR 1 이하, PER 10 이하 저평가 종목'처럼 명확한 숫자를 줬는데도 수정 fast-path가
    펀더멘털 추출을 안 해 LLM으로 위임 → LLM이 빈 diff를 내 필터가 안 잡히고 '숫자로 구체화해
    주세요'를 다시 묻던 버그.
    """
    parser = NLStrategyParser(backend="ollama")

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("명시적 펀더멘털 조건 추가는 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)

    previous = {**_MODIFY_PREVIOUS, "fundamental_filters": []}
    parsed = parser.parse_modification("PBR 1 이하, PER 10 이하 저평가 종목", previous)

    filters = {(f.metric, f.operator, f.value) for f in parsed.fundamental_filters}
    assert filters == {("pbr", "<=", 1.0), ("per", "<=", 10.0)}
    assert parsed.universe == ["KOSPI200"]  # 기존 유니버스 보존


def test_parse_modification_fundamental_filter_replaces_same_metric(monkeypatch):
    """같은 지표 조건을 다시 주면 값을 교체하고, 다른 지표 조건은 보존한다."""
    parser = NLStrategyParser(backend="ollama")
    monkeypatch.setattr(
        parser, "_modify_ollama",
        lambda *_: (_ for _ in ()).throw(AssertionError("LLM 호출 금지")),
    )

    previous = {
        **_MODIFY_PREVIOUS,
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 2.0}],
    }
    parsed = parser.parse_modification("PBR 1 이하", previous)

    filters = {(f.metric, f.operator, f.value) for f in parsed.fundamental_filters}
    assert filters == {("pbr", "<=", 1.0)}


def test_parse_falls_back_when_llm_output_fails_validation(monkeypatch):
    """LLM이 스키마 위반 JSON을 내면 500 대신 결정론 폴백으로 전환한다.

    회귀: 복잡한 서술형 전략에서 LLM이 description 누락·잘못된 enum(biweekly/2y)·
    null 배열을 내 ValidationError가 parse()에서 재발생 → 프로덕션 500.
    """
    parser = NLStrategyParser(backend="ollama")
    # 룰베이스가 처리하지 못하게 강제 → LLM 경로로 진입
    monkeypatch.setattr("engine.nl_parser._parse_rule_based_strategy", lambda _u: None)

    def _bad_llm(_user_input):
        ParsedStrategy.model_validate({})  # 필수 필드(description 등) 누락 → ValidationError

    monkeypatch.setattr(parser, "_parse_ollama", _bad_llm)

    parsed = parser.parse("코스피200에서 분위기 좋은 종목 알아서 담는 전략, 최대 8종목, 초기자금 2억원")

    # 결정론 폴백이 구체 파라미터를 정확히 복구
    assert parsed.universe == ["KOSPI200"]
    assert parsed.max_positions == 8
    assert parsed.initial_capital == 200_000_000.0


def test_parse_modification_falls_back_when_llm_diff_fails_validation(monkeypatch):
    """Keep the previous strategy without reinterpretation when the LLM diff is invalid."""
    parser = NLStrategyParser(backend="ollama")

    def _bad_diff(_user_input, _previous):
        ParsedStrategyDiff.model_validate({"rebalancing_period": "biweekly"})  # 잘못된 enum

    monkeypatch.setattr(parser, "_modify_ollama", _bad_diff)

    # _modify_rule_based가 None을 반환하는 복합 입력 → LLM 경로
    parsed = parser.parse_modification("변동성 낮은 종목으로 바꿔줘", dict(_MODIFY_PREVIOUS))

    assert parsed.max_positions == 8  # 이전 값 보존
    assert parsed.universe == ["KOSPI200"]
    assert parsed.stop_loss_pct == 12


# ─── 수정 경로 섹터/업종 처리 테스트 ─────────────────────────────────────────
# [회귀] 완성된 전략에 "반도체 섹터 종목만 테스트 해줘" 후속 요청이 조용히 무시되고
# 동일한 전략 요약이 재출력되던 버그 — 수정 경로(rule-based·LLM 병합 모두)에 섹터
# 처리가 통째로 빠져 있었다(FR-STR-066의 modify 확장).


def test_modify_sector_only_request_resolves_deterministically(monkeypatch):
    """스크린샷 원문 재현: 섹터 제한 후속 요청은 LLM 없이 fast-path가 sector를 반영한다."""
    parser = NLStrategyParser(backend="ollama")

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("섹터 단순 수정은 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)

    parsed = parser.parse_modification("반도체 섹터 종목만 테스트 해줘", dict(_MODIFY_PREVIOUS))

    assert parsed.sector == "반도체"
    # 수정 경로는 기존 universe를 보존한다(파스 경로의 양시장 기본 확장은 미적용).
    assert parsed.universe == ["KOSPI200"]
    assert parsed.max_positions == 8  # 언급 없는 필드 보존
    assert parsed.stop_loss_pct == 12


def test_modify_sector_combined_with_risk_field_deterministically():
    from engine.nl_parser import _modify_rule_based

    parsed = _modify_rule_based("바이오 업종만으로 하고 손절은 10%로 바꿔줘", dict(_MODIFY_PREVIOUS))

    assert parsed is not None
    assert parsed.sector == "바이오/제약"  # 동의어가 정본 섹터명으로 정규화
    assert parsed.stop_loss_pct == 10.0
    assert parsed.universe == ["KOSPI200"]


def test_modify_without_sector_mention_preserves_previous_sector():
    from engine.nl_parser import _modify_rule_based

    prev = {**_MODIFY_PREVIOUS, "sector": "반도체"}
    parsed = _modify_rule_based("종목을 10개로 늘려줘", prev)

    assert parsed is not None
    assert parsed.sector == "반도체"  # 언급 없으면 기존 섹터 유지
    assert parsed.max_positions == 10


def test_modify_adds_operating_margin_filter_deterministically(monkeypatch):
    """[회귀] '영업이익률 …' 필터 추가 수정이 조용히 누락되던 버그 — 값이 명시되면
    fast-path가 기존 필터를 유지한 채 병합하고 LLM을 호출하지 않는다."""
    parser = NLStrategyParser(backend="ollama")

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("값이 명시된 펀더멘털 필터 수정은 LLM을 호출하면 안 된다")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)

    parsed = parser.parse_modification("영업이익률 15% 이상 조건 추가해줘", dict(_MODIFY_PREVIOUS))

    by_metric = {f.metric: f for f in parsed.fundamental_filters}
    assert "operating_margin" in by_metric
    assert by_metric["operating_margin"].operator == ">="
    assert by_metric["operating_margin"].value == 15.0
    assert "pbr" in by_metric  # 기존 필터 보존(병합, 교체 아님)
    assert parsed.max_positions == 8  # 언급 없는 필드 보존


def test_parse_modification_llm_filter_diff_merges_with_existing(monkeypatch):
    """[회귀] LLM diff가 새 필터만 출력해도(few-shot 경향) 제거 의도가 없는 발화에서는
    기존 필터를 보존·병합한다 — '영업이익률 추가' 후 기존 ROE/PBR 증발 방지."""
    from engine.nl_parser import ParsedStrategyDiff

    parser = NLStrategyParser(backend="ollama")
    diff = ParsedStrategyDiff(
        fundamental_filters=[FundamentalFilter(metric="operating_margin", operator=">=", value=10.0)]
    )
    monkeypatch.setattr(parser, "_modify_ollama", lambda _u, _p: diff)

    parsed = parser.parse_modification("영업이익률을 추가해 볼까?", dict(_MODIFY_PREVIOUS))

    by_metric = {f.metric: f for f in parsed.fundamental_filters}
    assert "operating_margin" in by_metric
    assert "pbr" in by_metric  # 기존 필터 보존
    assert by_metric["pbr"].value == 1.0


def test_parse_modification_llm_filter_diff_respects_removal(monkeypatch):
    """제거 발화에서는 LLM이 낸 전체 목록(빠진 항목=삭제)을 병합으로 되살리지 않는다."""
    from engine.nl_parser import ParsedStrategyDiff

    parser = NLStrategyParser(backend="ollama")
    prev = {
        **_MODIFY_PREVIOUS,
        "fundamental_filters": [
            {"metric": "pbr", "operator": "<=", "value": 1},
            {"metric": "roe_or_gpa", "operator": ">=", "value": 10},
        ],
    }
    diff = ParsedStrategyDiff(
        fundamental_filters=[FundamentalFilter(metric="roe_or_gpa", operator=">=", value=10.0)]
    )
    monkeypatch.setattr(parser, "_modify_ollama", lambda _u, _p: diff)

    parsed = parser.parse_modification("PBR 조건은 빼줘", prev)

    metrics = {f.metric for f in parsed.fundamental_filters}
    assert metrics == {"roe_or_gpa"}  # pbr이 병합으로 부활하면 안 된다


def test_modify_unsupported_factor_delegates_to_llm_with_notice():
    """미지원 팩터(ROIC 등) 수정 요청은 fast-path가 처리한 척하지 않고 LLM에
    위임하며, notices 채널용 안내문이 생성된다(수정 경로도 _build_parse_result 공유)."""
    from engine.nl_parser import _modify_rule_based, build_unsupported_concept_notice

    prompt = "ROIC 15% 이상 조건 추가해줘"
    assert _modify_rule_based(prompt, dict(_MODIFY_PREVIOUS)) is None
    notice = build_unsupported_concept_notice(prompt)
    assert notice is not None and "ROIC" in notice


def test_parse_modification_llm_diff_missing_sector_recovered_deterministically(monkeypatch):
    """LLM 경로로 간 복합 수정에서 diff가 sector를 놓쳐도 결정적 추출이 보정한다."""
    parser = NLStrategyParser(backend="ollama")

    def _diff_without_sector(_user_input, _previous):
        return ParsedStrategyDiff()  # 전 필드 null = 변경 없음

    monkeypatch.setattr(parser, "_modify_ollama", _diff_without_sector)

    # '변동성' 잔여 때문에 rule-based가 None을 반환하는 복합 입력 → LLM 경로
    parsed = parser.parse_modification(
        "변동성 낮은 반도체 관련주로 바꿔줘", dict(_MODIFY_PREVIOUS)
    )

    assert parsed.sector == "반도체"
    assert parsed.universe == ["KOSPI200"]  # 수정 경로는 universe 보존


def test_parse_modification_sector_removal_clears_sector(monkeypatch):
    """'업종 제한 빼줘'는 diff null 병합이 무시하므로 별도 보정으로 sector를 해제한다."""
    parser = NLStrategyParser(backend="ollama")
    monkeypatch.setattr(
        parser, "_modify_ollama", lambda _user_input, _previous: ParsedStrategyDiff()
    )

    prev = {**_MODIFY_PREVIOUS, "sector": "반도체"}
    parsed = parser.parse_modification("업종 제한은 빼줘", prev)

    assert parsed.sector is None
    assert parsed.universe == ["KOSPI200"]


def test_sector_removal_regex_ignores_symbol_exclusion_requests():
    """'업종에서 삼성전자 빼줘'(종목 제외 요청)는 섹터 해제로 오발동하면 안 된다."""
    from engine.nl_parser import _SECTOR_REMOVE_RE, _compact

    assert not _SECTOR_REMOVE_RE.search(_compact("반도체 업종에서 삼성전자는 빼줘"))
    assert _SECTOR_REMOVE_RE.search(_compact("업종 제한 빼줘"))
    assert _SECTOR_REMOVE_RE.search(_compact("섹터 필터 지워줘"))


def test_build_fallback_strategy_handles_vague_prompt_without_crashing():
    parsed = _build_fallback_strategy("좋은 저평가 전략 만들어줘")

    assert parsed.description == "좋은 저평가 전략 만들어줘"
    assert parsed.universe == ["KOSPI200"]
    assert parsed.max_positions == 10


# ─── 상대강도(수익률 순위) 랭킹 파싱 테스트 ─────────────────────────────────


def test_rule_based_parses_relative_strength_ranking_full_prompt():
    """스크린샷 프롬프트: 수익률 상위 랭킹이 ranking_metric으로 잡히고 진입 누락이 아님."""
    prompt = (
        "최근 3개월 동안 꾸준히 오른 종목을 따라가는 전략을 써보고 싶어요. "
        "KOSDAQ에서 최근 60거래일 수익률이 높은 종목 상위권만 골라서 6종목 정도 나눠 사고, "
        "한 달에 한 번씩 다시 순위를 확인해 주세요. 손절은 -9%로 해주세요."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert parsed.ranking_metric == "return"
    assert parsed.ranking_lookback_days == 60
    assert parsed.universe == ["KOSDAQ"]
    assert parsed.max_positions == 6  # '3개월'의 '3개'를 종목 수로 오인하지 않음
    assert parsed.rebalancing_period == "monthly"
    # 모멘텀 설명의 '3개월'이 보유기간으로 잡히면 안 됨(회전은 리밸런싱이 구동).
    assert parsed.hold_period_days is None
    assert parsed.stop_loss_pct == 9.0


def test_rebalancing_bimonthly_phrasings():
    """'두 달에 한 번/격월/2개월마다'는 bimonthly. monthly의 '달에한번'에 삼켜지지 않는다."""
    assert _extract_rebalancing_period("두 달에 한 번 점검", None) == "bimonthly"
    assert _extract_rebalancing_period("격월 리밸런싱", None) == "bimonthly"
    assert _extract_rebalancing_period("2개월마다 다시 본다", None) == "bimonthly"
    # 한 달에 한 번은 그대로 monthly
    assert _extract_rebalancing_period("한 달에 한 번 점검", None) == "monthly"


def test_parse_rule_based_bimonthly_inspection():
    """스크린샷 프롬프트: '점검은 두 달에 한 번' → bimonthly 리밸런싱으로 잡힌다."""
    prompt = (
        "KOSPI 종목 중 PBR 1 이하 PER 10 이하 종목을 8개 사고, "
        "점검은 두 달에 한 번이면 좋겠습니다. 손절은 -10%."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert parsed.rebalancing_period == "bimonthly"


def test_extract_max_positions_ignores_months_phrase():
    """'3개월'의 '3개'를 종목 수로 오인하지 않는다."""
    from engine.nl_parser import _extract_max_positions

    assert _extract_max_positions("최근 3개월 동안 6종목 매수") == 6


def test_ranking_lookback_from_trading_day_phrase():
    from engine.nl_parser import _extract_ranking

    assert _extract_ranking("최근 60거래일 수익률 상위 종목") == ("return", 60)


def test_ranking_none_when_no_ranking_intent():
    from engine.nl_parser import _extract_ranking

    assert _extract_ranking("골든크로스 매수, 데드크로스 매도") == (None, None)


def test_ranking_lookback_from_korean_month_phrase():
    """'최근 한 달 수익률'은 60 기본값이 아니라 ~21거래일로 환산해야 한다."""
    from engine.nl_parser import _extract_ranking

    assert _extract_ranking("최근 한 달 수익률이 높은 상위 5개") == ("return", 21)
    assert _extract_ranking("최근 세 달 수익률 상위 종목") == ("return", 63)


def test_ranking_lookback_from_week_phrase():
    from engine.nl_parser import _extract_ranking

    assert _extract_ranking("최근 2주 수익률 상위 종목") == ("return", 10)
    assert _extract_ranking("일주일 수익률 상위 종목") == ("return", 5)


def test_rebalancing_period_detects_weekly():
    from engine.nl_parser import _extract_rebalancing_period

    assert _extract_rebalancing_period("매주 한 번씩 순위를 다시 확인해서 교체", None) == "weekly"
    assert _extract_rebalancing_period("주간 리밸런싱으로 운용", None) == "weekly"
    # 기존 주기는 그대로 유지(회귀 방지)
    assert _extract_rebalancing_period("매월 리밸런싱", None) == "monthly"


def test_rule_based_strategy_parses_weekly_momentum_ranking_prompt_without_llm():
    """'최근 한 달 수익률 상위 5종목 + 매주 교체 + 손절 -6%' 전체 결정적 파싱."""
    prompt = (
        "KOSPI에서 최근 한 달 수익률이 높은 종목 상위 5개만 사고, "
        "매주 한 번씩 순위를 다시 확인해서 밀린 종목은 교체해 주세요. 손절은 -6%로 부탁드립니다."
    )
    parsed = _parse_rule_based_strategy(prompt)
    assert parsed is not None
    assert parsed.universe == ["KOSPI"]
    assert parsed.ranking_metric == "return"
    assert parsed.ranking_lookback_days == 21
    assert parsed.max_positions == 5
    assert parsed.rebalancing_period == "weekly"
    assert parsed.stop_loss_pct == 6.0
    # 랭킹 전략은 리밸런싱이 회전을 구동하므로 보유기간은 비운다.
    assert parsed.hold_period_days is None


def test_ranking_metric_counts_as_entry_for_clarification():
    """ranking_metric만 있어도 진입 누락으로 되묻지 않는다."""
    base = make_base_strategy().model_copy(update={"ranking_metric": "return", "ranking_lookback_days": 60})

    assert detect_missing_entry_clarification(base, "수익률 상위 종목") == (None, None)


# ─── 진입 누락 되묻기(미지원 전략 유형 포함) 테스트 ──────────────────────────


def test_missing_entry_clarification_none_when_entry_present():
    """진입 규칙(재무 필터/기술 신호)이 있으면 되묻지 않는다."""
    base = make_base_strategy().model_copy(
        update={"entry_signals": [TechnicalSignal(indicator="ma_crossover", signal_type="buy")]}
    )

    question, suggestions = detect_missing_entry_clarification(base, "골든크로스 매수")

    assert question is None
    assert suggestions is None


def test_missing_entry_clarification_generic_when_no_entry_and_no_ranking():
    """진입이 전혀 없고 랭킹 의도도 아니면 일반 진입 조건 안내를 한다."""
    base = make_base_strategy().model_copy(update={"stop_loss_pct": 9.0})

    question, suggestions = detect_missing_entry_clarification(base, "손절 9%로 해줘")

    assert question is not None
    assert "진입 조건" in question
    assert suggestions and len(suggestions) > 0


def test_missing_entry_clarification_skipped_for_single_asset():
    """[FR-STR-068] 지정 종목(단일 종목)은 '종목 선택'이 끝났으므로, 진입 규칙이 없어도
    '어떤 조건으로 종목을 선택할까요?' 유니버스형 질문을 던지지 않는다(매수 후 보유 실행)."""
    base = make_base_strategy().model_copy(update={"target_symbols": ["005930"]})
    assert detect_missing_entry_clarification(base, "삼성전자 투자 하는 전략") == (None, None)


def test_incomplete_backtest_conditions_gate():
    """[정책] 백테스트 최소 조건(유니버스·진입·청산·손절·익절)이 하나라도 없으면 채우도록
    되묻는다. 진입은 랭킹/지정 종목도 인정한다(Q2)."""
    from engine.nl_parser import detect_incomplete_backtest_conditions, ParsedStrategy

    # 단일 종목(진입=지정종목 인정, 유니버스=지정종목 인정) → 청산·손절·익절만 요구
    single = ParsedStrategy(description="삼성전자", target_symbols=["005930"])
    q, chips = detect_incomplete_backtest_conditions(single, "삼성전자 투자 하는 전략")
    assert q is not None and "청산" in q and "손절" in q and "익절" in q
    assert chips == ["20일 보유 후 청산", "손절 10%", "익절 20%"]


def test_incomplete_backtest_conditions_complete_strategy_runs():
    """다섯 조건이 모두 있으면 (None, None) — 실행 가능."""
    from engine.nl_parser import detect_incomplete_backtest_conditions, ParsedStrategy, TechnicalSignal

    complete = ParsedStrategy(
        description="x", universe=["KOSPI200"],
        entry_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="buy",
                                       short_period=5, long_period=20)],
        exit_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="sell",
                                      short_period=5, long_period=20)],
        rebalancing_period="monthly",
        stop_loss_pct=10.0, take_profit_pct=20.0,
    )
    assert detect_incomplete_backtest_conditions(complete, "") == (None, None)


def test_incomplete_backtest_conditions_rebalancing_required_for_universe():
    """[정책] 단독 종목이 아니면 리밸런싱도 필수. 단독 종목은 교체가 없어 제외."""
    from engine.nl_parser import detect_incomplete_backtest_conditions, ParsedStrategy, TechnicalSignal

    def _sig(st):
        return TechnicalSignal(indicator="ma_crossover", signal_type=st, short_period=5, long_period=20)

    # 유니버스 전략: 청산신호로 has_exit는 충족되지만 리밸런싱이 없으면 여전히 요구된다.
    universe = ParsedStrategy(
        description="x", universe=["KOSPI200"], entry_signals=[_sig("buy")],
        exit_signals=[_sig("sell")], stop_loss_pct=10.0, take_profit_pct=20.0,
    )
    q, chips = detect_incomplete_backtest_conditions(universe, "")
    assert q is not None and "리밸런싱" in q
    assert chips == ["매월 리밸런싱", "분기마다 리밸런싱"]

    # 단독 종목은 리밸런싱을 요구하지 않는다 — 청산·손절·익절만.
    single = ParsedStrategy(description="x", target_symbols=["005930"])
    q2, _ = detect_incomplete_backtest_conditions(single, "")
    assert "리밸런싱" not in (q2 or "")


def test_incomplete_backtest_conditions_momentum_entry_recognized():
    """모멘텀 랭킹·정기 리밸런싱은 진입(랭킹)·청산(리밸런싱)으로 인정 → 손절·익절만 요구(Q2)."""
    from engine.nl_parser import detect_incomplete_backtest_conditions, ParsedStrategy

    momentum = ParsedStrategy(
        description="x", universe=["KOSPI200"], ranking_metric="return",
        rebalancing_period="monthly",
    )
    q, chips = detect_incomplete_backtest_conditions(momentum, "")
    assert q is not None
    assert chips == ["손절 10%", "익절 20%"]  # 진입·청산·리밸런싱은 충족


def test_missing_entry_clarification_asks_numbers_for_qualitative_metrics():
    """스크린샷 프롬프트: 'PER이 낮고 부채비율이 낮은' — 지표만 말하고 숫자가 없으면
    그 지표별로 구체적 숫자를 예시와 함께 되묻는다."""
    prompt = (
        "KOSPI 종목 중 PER이 낮고 부채비율이 낮은 기업만 남긴 뒤 8종목 정도 동일하게 "
        "투자해 주세요. 손절은 -10%."
    )
    base = make_base_strategy().model_copy(
        update={"universe": ["KOSPI"], "max_positions": 8, "stop_loss_pct": 10.0}
    )

    question, suggestions = detect_missing_entry_clarification(base, prompt)

    assert question is not None
    # 언급한 두 지표를 숫자로 되묻는다.
    assert "PER은 몇 이하" in question
    assert "부채비율은 몇 % 이하" in question
    # 언급 안 한 지표는 묻지 않는다.
    assert "ROE" not in question
    # 클릭 시 바로 완성되는 숫자 예시 칩을 제공한다.
    assert suggestions is not None
    assert any("PER 10 이하" in s and "부채비율 100% 이하" in s for s in suggestions)


def test_operating_margin_without_threshold_removes_substitute_and_asks_percentage():
    """A qualitative operating-margin request must not become an unrelated PBR filter."""
    prompt = "영업이익률이 높은 주식을 사는 전략"
    hallucinated = make_base_strategy().model_copy(
        update={
            "fundamental_filters": [
                FundamentalFilter(metric="pbr", operator="<=", value=1.0)
            ]
        }
    )

    parsed = _apply_prompt_overrides(hallucinated, prompt)
    question, suggestions = detect_missing_entry_clarification(parsed, prompt)

    assert parsed.fundamental_filters == []
    assert question is not None
    assert "영업이익률 몇 % 이상으로 설정할까요?" in question
    assert suggestions == ["영업이익률 10% 이상", "영업이익률 15% 이상"]


def test_operating_margin_with_threshold_becomes_entry_without_clarification():
    prompt = "영업이익률 15% 이상인 주식을 사는 전략"
    parsed = _build_fallback_strategy(prompt)

    question, suggestions = detect_missing_entry_clarification(parsed, prompt)

    assert len(parsed.fundamental_filters) == 1
    assert parsed.fundamental_filters[0].metric == "operating_margin"
    assert parsed.fundamental_filters[0].operator == ">="
    assert parsed.fundamental_filters[0].value == 15.0
    assert question is None
    assert suggestions is None


def test_missing_entry_clarification_etf_suggests_price_based_rules():
    """스크린샷 프롬프트: 'etf를 사는 전략은 어때?' — ETF엔 PER·PBR 같은 기업 재무지표가
    없으므로 일반 예시(재무 필터 칩) 대신 가격·추세 기반 방식으로 안내한다."""
    base = make_base_strategy()

    question, suggestions = detect_missing_entry_clarification(base, "etf를 사는 전략은 어때?")

    assert question is not None
    assert "ETF" in question
    # 재무 필터 예시 칩이 나오면 안 된다(ETF엔 해당 지표가 없음).
    assert suggestions is not None
    joined = " ".join(suggestions)
    assert "PBR" not in joined and "PER" not in joined and "ROE" not in joined
    # 가격·추세 기반 대안을 제시한다.
    assert any("돌파" in s or "이동평균" in s or "선" in s or "RSI" in s for s in suggestions)


def test_missing_entry_clarification_named_etf_product_confirms_instead_of_reasking():
    """'kodex 반도체 etf를 매수' — 이미 특정 상품(KODEX 반도체)이 지정됐으므로, 여러 ETF
    중 고르는 것처럼 읽히는 일반 테마 문구('정기 리밸런싱' 등) 대신 상품명을 확정해
    보여주는 문구로 되물어야 한다(사용자가 "또 어떤 ETF 살건지 물어본다"고 오인하는
    버그 재현)."""
    base = make_base_strategy().model_copy(
        update={"universe": ["ETF"], "etf_theme": "KODEX 반도체"}
    )

    question, suggestions = detect_missing_entry_clarification(base, "kodex 반도체 etf를 매수")

    assert question is not None
    assert "KODEX 반도체" in question and "091160" in question
    assert "정기 리밸런싱" not in question
    assert suggestions is not None
    joined = " ".join(suggestions)
    assert "PBR" not in joined and "PER" not in joined and "ROE" not in joined


def test_missing_entry_clarification_etf_theme_keyword_keeps_generic_question():
    """반대로 열린 테마("반도체")는 여러 ETF에 매칭되므로 일반 문구를 유지한다 —
    단일 상품 확정 문구로 바뀌면 안 된다."""
    base = make_base_strategy().model_copy(
        update={"universe": ["ETF"], "etf_theme": "반도체"}
    )

    question, _ = detect_missing_entry_clarification(base, "반도체 ETF 사는 전략")

    assert question is not None
    assert "KODEX" not in question
    assert "091160" not in question


def test_missing_entry_clarification_etf_qualitative_metric_gets_product_guidance():
    """'PER 낮은 ETF' — ETF엔 PER이 없으니 'PER은 몇 이하로 할까요?' 임계값 되묻기 대신
    상품 안내가 먼저다."""
    base = make_base_strategy()

    question, _ = detect_missing_entry_clarification(base, "PER 낮은 ETF 전략 만들어줘")

    assert question is not None
    assert "ETF" in question
    assert "PER은 몇 이하" not in question


def test_missing_entry_clarification_etf_with_entry_signal_does_not_ask():
    """ETF 언급이라도 기술 신호가 이미 있으면 되묻지 않는다 — ETF는 정식 유니버스라
    그대로 실행 가능하다."""
    base = make_base_strategy().model_copy(
        update={"entry_signals": [TechnicalSignal(indicator="ma_crossover", signal_type="buy")]}
    )

    question, suggestions = detect_missing_entry_clarification(
        base, "ETF 골든크로스 매수 전략"
    )

    assert question is None
    assert suggestions is None


def test_etf_supported_universe_rule_parse_and_no_notice():
    """ETF는 정식 유니버스(2026-07-19 승격) — 미지원 안내 없이 룰 파서가 universe=["ETF"]로
    파싱한다(개념 구현 시 미지원 목록 제거 원칙의 적용 사례)."""
    from engine.nl_parser import build_unsupported_concept_notice

    prompt = "ETF 골든크로스 매수, 데드크로스 매도, 손절 10%"
    assert build_unsupported_concept_notice(prompt) is None
    assert _mentions_unsupported_concept(prompt) is None

    parsed = _parse_rule_based_strategy(prompt)
    assert parsed is not None
    assert parsed.universe == ["ETF"]
    assert parsed.sector is None


def test_etf_universe_extraction_and_theme():
    """ETF 언급은 시장 언급보다 우선하며(코스피 ETF도 ETF), 테마/상품명은 ETF 마스터
    이름과의 자기검증 매칭으로 추출된다."""
    from engine.nl_parser import _extract_explicit_universe
    from engine.universe_pit import extract_etf_theme

    assert _extract_explicit_universe("etf를 사는 전략") == ["ETF"]
    assert _extract_explicit_universe("코스피 ETF 위주로") == ["ETF"]
    assert extract_etf_theme("반도체 ETF 모멘텀 전략") == "반도체"
    assert extract_etf_theme("etf를 사는 전략은 어때?") is None


def test_etf_universe_exclusive_and_sector_cleared():
    """ETF 유니버스는 주식 시장과 혼합하지 않으며(단독), 종목 섹터 분류는 비운다."""
    parsed = ParsedStrategy(
        description="x", universe=["KOSPI", "ETF"], sector="반도체",
    )
    assert parsed.universe == ["ETF"]
    assert parsed.sector is None


def test_etf_factor_conflict_explains_and_suggests_alternatives():
    """ETF 유니버스 × 기업 재무지표: 조용히 무시하지 않고 이유 설명 + 기술 지표 대안을
    제안한다. 주식 유니버스나 거래대금(가격 파생)은 충돌이 아니다."""
    from engine.nl_parser import detect_etf_factor_conflict

    etf_with_per = ParsedStrategy(
        description="PER 10 이하 ETF", universe=["ETF"],
        fundamental_filters=[FundamentalFilter(metric="per", operator="<=", value=10.0)],
    )
    question, suggestions = detect_etf_factor_conflict(etf_with_per, "PER 10 이하 ETF")
    assert question is not None
    assert "PER" in question and "재무지표" in question
    assert "변경할까요" in question
    assert suggestions and any("RSI" in s or "돌파" in s for s in suggestions)

    # 주식 유니버스는 충돌 없음.
    stock = make_base_strategy().model_copy(
        update={"fundamental_filters": [FundamentalFilter(metric="per", operator="<=", value=10.0)]}
    )
    assert detect_etf_factor_conflict(stock, "PER 10 이하") == (None, None)

    # 거래대금은 가격·거래량 파생이라 ETF에서도 허용.
    etf_tv = ParsedStrategy(
        description="거래대금 100억 이상 ETF", universe=["ETF"],
        fundamental_filters=[FundamentalFilter(metric="trading_value", operator=">=", value=100.0)],
    )
    assert detect_etf_factor_conflict(etf_tv, "거래대금 100억 이상 ETF") == (None, None)


def test_etf_theme_flows_to_backtest_request_and_canonical_dsl():
    """etf_theme가 백테스트 요청과 canonical DSL(해시)에 포함되고, 비-ETF 전략의
    canonical DSL에는 키 자체가 없다(기존 해시 불변)."""
    from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl

    etf = _parse_rule_based_strategy("반도체 ETF 골든크로스 매수, 데드크로스 매도, 손절 10%")
    assert etf is not None and etf.universe == ["ETF"] and etf.etf_theme == "반도체"
    req = to_backtest_request(etf, resolve_symbols=False)
    assert req["universe_id"] == "etf"
    assert req["etf_theme"] == "반도체"
    assert to_canonical_strategy_dsl(etf)["etf_theme"] == "반도체"

    stock = _parse_rule_based_strategy("골든크로스 매수, 데드크로스 매도, 손절 10%")
    assert "etf_theme" not in to_canonical_strategy_dsl(stock)


def test_missing_entry_clarification_flags_relative_strength_ranking():
    """스크린샷 프롬프트: 수익률 상위 랭킹은 미지원 → 추세추종 전환을 안내한다."""
    prompt = (
        "최근 3개월 동안 꾸준히 오른 종목을 따라가는 전략을 써보고 싶어요. "
        "KOSDAQ에서 최근 60거래일 수익률이 높은 종목 상위권만 골라서 6종목 정도 나눠 사고, "
        "한 달에 한 번씩 다시 순위를 확인해 주세요. 손절은 -9%로 해주세요."
    )
    base = make_base_strategy().model_copy(
        update={"universe": ["KOSDAQ"], "max_positions": 6, "stop_loss_pct": 9.0}
    )

    question, suggestions = detect_missing_entry_clarification(base, prompt)

    assert question is not None
    assert "상대강도" in question
    # 가까운 추세추종 대안을 제시한다.
    assert suggestions is not None
    assert any("골든크로스" in s or "신고가" in s or "돌파" in s for s in suggestions)


# ─── LLM 환각 신호 검증 테스트 ──────────────────────────────────────────────


def test_validate_signals_removes_unmentioned_indicator():
    """프롬프트에 CCI 언급이 없으면 CCI 신호를 제거한다"""
    signals = [
        TechnicalSignal(indicator="cci", signal_type="sell", period=14, operator=">=", value=100),
    ]

    validated = _validate_signals(signals, "수익이 10% 이상 날때도 매도 해줘")

    assert len(validated) == 0


def test_validate_signals_keeps_mentioned_indicator():
    """프롬프트에 CCI가 언급되면 CCI 신호를 유지한다"""
    signals = [
        TechnicalSignal(indicator="cci", signal_type="sell", period=14, operator=">=", value=100),
    ]

    validated = _validate_signals(signals, "CCI 100 이상이면 매도")

    assert len(validated) == 1
    assert validated[0].indicator == "cci"


def test_validate_signals_trusts_descriptive_breakout_without_keyword():
    """서술형 신호(breakout)는 '돌파/신고가' 키워드가 없어도(예: '위로 뚫으면') 유지한다.

    하이브리드: 표현이 무한히 다양한 패턴 신호는 키워드로 거르지 않고 모델을 신뢰한다.
    """
    signals = [TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=20)]

    validated = _validate_signals(signals, "최근 한 달 박스권을 위로 뚫으면 매수")

    assert len(validated) == 1
    assert validated[0].indicator == "breakout"


def test_validate_signals_still_strips_named_indicator_hallucination():
    """이름이 고정된 지표(adx)는 프롬프트에 미언급 시 여전히 환각으로 제거한다."""
    signals = [
        TechnicalSignal(indicator="adx", signal_type="sell", period=14, operator=">=", value=25),
    ]

    validated = _validate_signals(signals, "박스권 돌파하면 매수")

    assert len(validated) == 0


def test_validate_signals_mixed_valid_and_invalid():
    """유효한 신호는 유지하고 환각 신호만 제거한다"""
    signals = [
        TechnicalSignal(indicator="ma_crossover", signal_type="sell"),
        TechnicalSignal(indicator="cci", signal_type="sell"),  # 환각
        TechnicalSignal(indicator="adx", signal_type="sell"),  # 환각
    ]

    validated = _validate_signals(signals, "데드크로스가 나오면 매도")

    assert len(validated) == 1
    assert validated[0].indicator == "ma_crossover"


def test_full_prompt_profit_sell_without_hallucinated_cci():
    """스크린샷 재현: '수익이 10% 이상 날때도 매도' → CCI 제거 + 익절 10% 설정"""
    base = make_base_strategy().model_copy(
        update={
            "entry_signals": [
                TechnicalSignal(indicator="ma_crossover", signal_type="buy", short_period=5, long_period=20)
            ],
            "exit_signals": [
                TechnicalSignal(indicator="ma_crossover", signal_type="sell"),
                TechnicalSignal(indicator="cci", signal_type="sell", period=14, operator=">=", value=100),
            ],
            "stop_loss_pct": 8.0,
        }
    )

    parsed = _apply_prompt_overrides(base, "수익이 10% 이상 날때도 매도 해줘")

    # CCI는 프롬프트에 없으므로 제거
    exit_indicators = [s.indicator for s in parsed.exit_signals]
    assert "cci" not in exit_indicators
    # 데드크로스(ma_crossover sell)는 유지되지 않음 (프롬프트에 데드크로스 미언급)
    # 익절 10% 설정
    assert parsed.take_profit_pct == 10.0
    # 기존 손절 유지
    assert parsed.stop_loss_pct == 8.0


# ─── Ollama chat: thinking 비활성화 회귀 ──────────────────────────────────────


def _capture_ollama_chat_body(monkeypatch, *, streaming: bool) -> dict:
    """_chat_ollama / _stream_chat_ollama가 실제로 보낸 요청 body를 가로채 반환한다."""
    import json as _json
    from contextlib import contextmanager

    captured: dict = {}

    class _FakeResp:
        def read(self):
            return b'{"message": {"content": "{\\"message\\": \\"ok\\"}"}}'

        def __iter__(self):
            return iter([b'{"message": {"content": "ok"}, "done": true}'])

    @contextmanager
    def _fake_urlopen(req, timeout=120):
        # _chat_ollama/_stream_chat_ollama는 POST 전에 본문 없는 GET /api/tags로 컨테이너를
        # 깨운다(_ollama_ensure_warm). 그 warmup GET(req.data is None)은 건너뛰고, 본문이 있는
        # /api/chat POST만 캡처한다.
        if req.data is not None:
            captured["body"] = _json.loads(req.data.decode())
        yield _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    parser = NLStrategyParser(backend="ollama")
    if streaming:
        list(parser.stream_chat("sys", "user", max_tokens=400, temperature=0.3, top_p=0.9))
    else:
        parser.chat("sys", "user", max_tokens=400, temperature=0.3, top_p=0.9)
    return captured["body"]


def test_chat_ollama_disables_thinking(monkeypatch):
    """Qwen3 thinking 모델 thinking 우회는 `think: false`로 한다.

    회귀: 과거엔 assistant prefill `<think>\n\n</think>\n`을 마지막 메시지로 넣었으나, 현행
    Modal ollama의 Qwen3.5 chat template이 마지막 메시지가 assistant면 "No user query found in
    messages" Jinja 예외로 HTTP 400을 던진다(프로덕션 실측). prefill 폐기 + think:false 사용.
    """
    body = _capture_ollama_chat_body(monkeypatch, streaming=False)
    assert body.get("think") is False, "thinking 우회는 think:false로 해야 함"
    # 코치 prompt(~5.8K토큰)가 기본 num_ctx(4096)를 넘어 400 나는 것을 막아야 한다.
    assert body["options"]["num_ctx"] >= 8192, "코치 prompt를 담을 num_ctx가 설정돼야 함"
    messages = body["messages"]
    # 마지막 메시지는 user여야 한다 — assistant prefill은 template 400을 유발하므로 금지.
    assert messages[-1]["role"] == "user"
    assert all(m["role"] != "assistant" for m in messages)


def test_stream_chat_ollama_disables_thinking(monkeypatch):
    """스트리밍 경로도 동일하게 think:false로 thinking을 우회한다(assistant prefill 금지)."""
    body = _capture_ollama_chat_body(monkeypatch, streaming=True)
    assert body.get("think") is False
    messages = body["messages"]
    assert messages[-1]["role"] == "user"
    assert all(m["role"] != "assistant" for m in messages)


# ─── 펀더멘털 스크리닝 fast-path 테스트 ──────────────────────────────────────
# 회귀: 'PBR<1 종목에 투자'처럼 청산 규칙을 안 적은 가치주 스크리닝이 rule-based에서
# None을 반환해 LLM 폴백(Modal 콜드스타트 시 수십 초~120s timeout)으로 새던 버그.
# 펀더멘털 필터만 있어도 정기 리밸런싱 전략으로 완결 처리해 즉시(수 ms) 파싱돼야 한다.


@pytest.mark.parametrize(
    "prompt",
    [
        "pbr 1이라 종목에 투자 하고 싶어",
        "PBR 0.8 이하 종목 투자",
        "roe 15% 이상 종목 사고싶어",
        "per 10 이하이고 roe 15 이상인 종목",
    ],
)
def test_fundamental_screen_parses_without_llm(prompt):
    """펀더멘털 필터만 있는 스크리닝 전략은 LLM 없이 rule-based로 파싱돼야 한다."""
    parsed = _parse_rule_based_strategy(prompt)
    assert parsed is not None, f"prompt={prompt!r}가 None을 반환해 LLM 폴백으로 샘"
    assert len(parsed.fundamental_filters) >= 1
    # 청산 언급이 없으면 정기 리밸런싱(월간)으로 회전을 완결한다.
    assert parsed.rebalancing_period == "monthly"


@pytest.mark.parametrize(
    "prompt",
    [
        "리밸런싱 없이 PBR 1 이하 종목 계속 보유",
        "PBR 0.8 이하 종목 투자, 리밸런싱은 하지 않고 그대로 보유",
    ],
)
def test_explicit_no_rebalancing_screen_is_not_forced_monthly(prompt):
    """[회귀] 사용자가 '리밸런싱 없이'를 명시한 스크리닝 전략에 기본 월간 리밸런싱을
    강제 주입해 명시 의도를 덮어쓰던 버그 — 매수 후 계속 보유(none)로 보존해야 한다."""
    parsed = _parse_rule_based_strategy(prompt)
    assert parsed is not None
    assert parsed.rebalancing_period == "none"


def test_ranking_keeps_rebalancing_even_when_negated():
    """랭킹(모멘텀) 전략의 회전은 달력 리밸런싱으로만 동작하므로, 거부 표현이 있어도
    회전 주기는 유지한다(엔진 제약)."""
    parsed = _parse_rule_based_strategy("리밸런싱 없이 최근 3개월 수익률 상위 5종목 매수")
    assert parsed is not None
    assert parsed.ranking_metric == "return"
    assert parsed.rebalancing_period == "monthly"


def test_value_screen_with_hold_period_does_not_inject_rebalancing():
    """회귀: 보유기간·손절을 명시한 가치주 스크리닝에 월간 리밸런싱을 임의 주입하면 안 된다.

    스크린샷 프롬프트: 'PBR<=1, 8종목, 6개월 보유, -12% 손절'은 보유기간이 회전/청산
    수단이므로 요청하지 않은 '매월 리밸런싱'이 들어가서는 안 된다.
    """
    prompt = (
        "KOSPI 대형주 중에서 PBR이 1배 이하인 종목만 골라서 8종목 정도 나눠 사고, "
        "한 번 사면 최소 6개월은 들고 가고 싶습니다. 큰 손실은 무서우니 -12% 손절만 넣어 주세요."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert parsed.hold_period_days == 126
    assert parsed.rebalancing_period == "none"


def test_value_screen_with_take_profit_does_not_inject_rebalancing():
    """회귀: 익절(리스크 청산)만 명시한 가치주 스크리닝에 월간 리밸런싱을 임의 주입하면 안 된다.

    스크린샷 프롬프트: 'PBR<=1, 10종목, 30% 익절'은 익절이 회전/청산 수단이므로
    사용자가 요청하지 않은 '매월 리밸런싱'이 들어가서는 안 된다.
    """
    prompt = "pbr 1이하의 종목을 10개만 매수하고 30% 수익이 나면 익절하는 전략이야. 백테스트 기간은 3년만 하자."

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert len(parsed.fundamental_filters) >= 1
    assert parsed.take_profit_pct == 30.0
    assert parsed.rebalancing_period == "none"
    # '백테스트 기간은 3년만 하자' → 3y (기본값 5y로 떨어지면 안 된다).
    assert parsed.backtest_period == "3y"


def test_extract_backtest_period_phrasings():
    """'백테스트 기간은 N년' 같은 서술형 기간 표현을 인접 'N년'에서 추출한다."""
    from engine.nl_parser import _extract_backtest_period

    assert _extract_backtest_period("백테스트 기간은 3년만 하자") == "3y"
    assert _extract_backtest_period("최근 5년 백테스트 해줘") == "5y"
    assert _extract_backtest_period("3년간 백테스트") == "3y"
    assert _extract_backtest_period("1y 백테스트") == "1y"
    assert _extract_backtest_period("전체기간으로 돌려줘") == "full"
    # 언급 없으면 None(호출부에서 기본값 5y 결정).
    assert _extract_backtest_period("PBR 1 이하 종목 매수") is None
    # 보유기간 '1년 보유'를 백테스트 기간으로 오인하지 않는다.
    assert _extract_backtest_period("PBR 1 이하, 1년 보유") is None


def test_inspection_cycle_n_months_maps_to_rebalancing_not_hold():
    """'점검 주기는 N개월'·'N개월 주기'는 보유기간이 아니라 정기 리밸런싱 주기다."""
    from engine.nl_parser import _extract_hold_period_days, _extract_rebalancing_period

    # 보유기간으로 오인하지 않는다.
    assert _extract_hold_period_days("점검 주기는 3개월") is None
    assert _extract_hold_period_days("3개월 주기로 재선정") is None
    # 주기로 인식한다.
    assert _extract_rebalancing_period("점검 주기는 3개월", None) == "quarterly"
    assert _extract_rebalancing_period("점검 주기는 1개월", None) == "monthly"
    assert _extract_rebalancing_period("2개월 주기", None) == "bimonthly"
    # 한글 수사 주기('두 달'=격월)도 인식한다.
    assert _extract_hold_period_days("점검 주기는 두 달") is None
    assert _extract_rebalancing_period("점검 주기는 두 달", None) == "bimonthly"
    assert _extract_rebalancing_period("세 달 주기로 점검", None) == "quarterly"


def test_value_screen_inspection_cycle_parses_quarterly_rebalancing():
    """회귀: 'ROE·부채비율, 점검 주기는 3개월'은 분기 리밸런싱으로 잡히고
    '3개월'이 보유기간(63일)으로 오인되지 않는다."""
    prompt = (
        "KOSPI에서 ROE 10% 이상이고 부채비율이 100% 이하인 종목을 대상으로 설정해 주세요. "
        "최대 보유 종목은 10개, 점검 주기는 3개월, 손절 예시값은 -10%로 설정해 주세요."
    )

    parsed = _parse_rule_based_strategy(prompt)

    assert parsed is not None
    assert parsed.rebalancing_period == "quarterly"
    assert parsed.hold_period_days is None


def test_technical_entry_without_exit_still_falls_back():
    """기술적 진입 신호만 있고 청산이 없으면 모호한 입력이라 rule-based가 None을 반환한다."""
    assert _parse_rule_based_strategy("골든크로스 매수") is None


def test_modify_ollama_uses_native_endpoint_with_num_ctx(monkeypatch):
    """회귀: 수정 모드 LLM 호출은 OpenAI 호환(/v1)이 아니라 네이티브 /api/chat을
    써야 한다. /v1은 num_ctx를 무시해, 긴 수정 프롬프트(MODIFY_PROMPT + 현재 전략
    JSON)가 기본 4096토큰을 넘으면 'exceeds context size' 400을 던졌다(프로덕션 장애).
    네이티브 엔드포인트 + options.num_ctx=16384로 컨텍스트 한도를 올려 해결한다."""
    import json as _json

    import engine.nl_parser as nlp

    captured: dict = {}

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return _json.dumps(
                {"message": {"content": _json.dumps({"take_profit_pct": 30.0})}}
            ).encode()

    def _fake_open(req, timeout):
        captured["url"] = req.full_url
        captured["body"] = _json.loads(req.data.decode())
        return _FakeResp()

    monkeypatch.setattr(nlp, "_ollama_ensure_warm", lambda: None)
    monkeypatch.setattr(nlp, "_ollama_open_with_retry", _fake_open)

    parser = NLStrategyParser(backend="ollama")
    diff = parser._modify_ollama("30% 익절 설정", {"description": "테스트", "stop_loss_pct": 12})

    assert diff.take_profit_pct == 30.0
    # 네이티브 엔드포인트여야 num_ctx가 적용된다.
    assert captured["url"].endswith("/api/chat")
    assert captured["body"]["options"]["num_ctx"] == nlp._OLLAMA_NUM_CTX
    assert nlp._OLLAMA_NUM_CTX > 4096


# ─── 복잡 전략 LLM 파싱 QA에서 발견한 결정적 추출 회귀 ──────────────────────────
# (scripts/qa_complex_llm_parse.py 의 100개 복잡 전략 검증에서 드러난 누락/오인식 수정)


def _sig_tuples(signals):
    return [(s.indicator, s.signal_type) for s in signals]


def _find(signals, indicator, signal_type):
    return next((s for s in signals if s.indicator == indicator and s.signal_type == signal_type), None)


def test_ai_model_buy_and_drop_sell_with_thresholds():
    """AI 상승/하락 예측은 결정적으로 추출되고, 임계값(%)은 키워드 근처에서 잡힌다."""
    entry, exit_ = _extract_technical_signals(
        "AI가 상승 확률 75% 이상으로 본 종목 중 거래대금 150억 넘는 것만 매수, AI 하락 예측 65% 이상이면 매도"
    )
    buy = _find(entry, "ai_model", "buy")
    sell = _find(exit_, "ai_drop_model", "sell")
    assert buy is not None and buy.threshold == 75.0
    assert sell is not None and sell.threshold == 65.0


def test_ai_model_buy_defaults_threshold_70():
    entry, exit_ = _extract_technical_signals(
        "AI 모델이 상승을 예측한 종목을 매수하고 AI가 하락을 예측하면 매도"
    )
    assert _find(entry, "ai_model", "buy").threshold == 70.0
    assert _find(exit_, "ai_drop_model", "sell").threshold == 70.0


def test_ai_drop_model_from_risk_signal_phrase():
    """'AI 하락 예측 모델이 위험 신호를 주면 청산' → ai_drop_model sell."""
    _, exit_ = _extract_technical_signals(
        "골든크로스로 매수하되 AI 하락 예측 모델이 위험 신호를 주면 즉시 청산하는 방어적 전략"
    )
    assert _find(exit_, "ai_drop_model", "sell") is not None


def test_ema_cross_handles_ema_before_number():
    """'EMA 10이 EMA 30 위에 있고' 처럼 EMA가 숫자 앞에 오는 어순도 인식한다."""
    entry, _ = _extract_technical_signals("EMA 10이 EMA 30 위에 있으면 매수")
    buy = _find(entry, "ema", "buy")
    assert buy is not None and buy.short_period == 10 and buy.long_period == 30


def test_ema_cross_mirror_sell_when_periods_omitted():
    """진입만 기간이 적히고 청산은 '다시 아래로 내려오면 매도'처럼 기간 생략 시 미러링한다."""
    entry, exit_ = _extract_technical_signals(
        "20일 EMA가 60일 EMA 위로 올라서면 매수, 다시 아래로 내려오면 매도"
    )
    assert _find(entry, "ema", "buy").long_period == 60
    sell = _find(exit_, "ema", "sell")
    assert sell is not None and sell.short_period == 20 and sell.long_period == 60


def test_ema_dead_cross_maps_to_ema_not_ma():
    """'EMA 데드크로스에 매도'는 ema sell이지 ma_crossover sell이 아니다."""
    entry, exit_ = _extract_technical_signals(
        "EMA 12가 EMA 26 위로 올라오면 매수, EMA 데드크로스에 매도"
    )
    assert _find(exit_, "ema", "sell") is not None
    assert _find(exit_, "ma_crossover", "sell") is None


def test_macd_golden_cross_is_macd_not_ma():
    """'MACD 골든크로스'는 macd buy이며 ma_crossover를 만들지 않는다."""
    entry, exit_ = _extract_technical_signals(
        "MACD 골든크로스에 매수하고 MACD 데드크로스에 매도"
    )
    assert _find(entry, "macd", "buy") is not None
    assert _find(exit_, "macd", "sell") is not None
    assert _find(entry, "ma_crossover", "buy") is None
    assert _find(exit_, "ma_crossover", "sell") is None


def test_macd_signal_line_crossover_phrasing():
    """'MACD가 시그널선을 상향 돌파'는 macd buy(crossover)."""
    entry, _ = _extract_technical_signals("MACD가 시그널선을 상향 돌파할 때 매수")
    buy = _find(entry, "macd", "buy")
    assert buy is not None and buy.mode == "crossover"


def test_macd_zero_line_breakout_phrasing():
    """'MACD가 0선을 상향 돌파'는 macd buy(zero)."""
    entry, _ = _extract_technical_signals("MACD가 0선을 상향 돌파하면 진입")
    buy = _find(entry, "macd", "buy")
    assert buy is not None and buy.mode == "zero"


def test_ma_periods_from_seonkwa_phrasing():
    """'20일선과 60일선의 골든크로스'에서 20/60 기간을 뽑는다(인접하지 않은 N일)."""
    entry, _ = _extract_technical_signals("20일선과 60일선의 골든크로스로 진입")
    buy = _find(entry, "ma_crossover", "buy")
    assert buy.short_period == 20 and buy.long_period == 60


def test_bare_opposite_threshold_stochastic_sell():
    """'스토캐스틱 20 아래 매수, 80 위로 매도'에서 80을 stochastic 청산으로 귀속한다."""
    entry, exit_ = _extract_technical_signals(
        "스토캐스틱이 20 아래로 떨어졌다가 다시 올라오면 매수, 80 위로 올라가면 매도"
    )
    sell = _find(exit_, "stochastic", "sell")
    assert sell is not None and sell.value == 80.0


def test_bare_opposite_threshold_cci_sell_with_particle():
    """'CCI -100 밑 진입, +100을 넘어서면 청산' — 숫자와 연산자 사이 조사(을)도 허용."""
    entry, exit_ = _extract_technical_signals(
        "CCI가 -100 밑으로 내려가면 진입하고 +100을 넘어서면 청산"
    )
    assert _find(exit_, "cci", "sell").value == 100.0


def test_rsi_sell_reverse_order_cheongsan_first():
    """'청산은 RSI 70 이상에서'처럼 청산 동사가 먼저 와도 rsi sell을 잡는다."""
    _, exit_ = _extract_technical_signals(
        "골든크로스 매수, 청산은 RSI 70 이상에서"
    )
    sell = _find(exit_, "rsi", "sell")
    assert sell is not None and sell.value == 70.0


def test_rsi_colloquial_bottom_rebound_and_overheat():
    """'RSI 바닥 찍고 반등 매수 / 과열되면 매도' 구어체를 rsi buy/sell로 처리한다."""
    entry, exit_ = _extract_technical_signals(
        "RSI가 바닥을 찍고 반등하는 종목을 사고, 충분히 올라 과열되면 팔래"
    )
    assert _find(entry, "rsi", "buy") is not None
    assert _find(exit_, "rsi", "sell") is not None


def test_no_spurious_rsi_sell_across_clause():
    """'RSI 50 위에 있으면 매수, 데드크로스 매도'에서 50을 rsi 청산으로 오인하지 않는다."""
    entry, exit_ = _extract_technical_signals(
        "골든크로스가 나오고 RSI가 50 위에 있으면 매수하고, 데드크로스가 발생하면 매도"
    )
    assert _find(exit_, "rsi", "sell") is None
    assert _find(exit_, "ma_crossover", "sell") is not None


def test_volume_spike_from_separated_teojim_phrase():
    """'거래량이 평소보다 크게 터지면서'처럼 급증 동사가 떨어져 있어도 volume_spike."""
    entry, _ = _extract_technical_signals(
        "거래량이 평소보다 크게 터지면서 박스권을 위로 돌파하면 매수"
    )
    assert _find(entry, "volume_spike", "buy") is not None
    assert _find(entry, "breakout", "buy") is not None


def test_ma_line_with_adverb_and_break_verb():
    """'60일 이동평균선을 강하게 상향 돌파' / '20일선 깨면 매도' 부사·구어체 동사 허용."""
    entry, exit_ = _extract_technical_signals(
        "주가가 60일 이동평균선을 강하게 상향 돌파하면 진입하고, 60일선을 하향 이탈하면 청산"
    )
    assert _find(entry, "ma_crossover", "buy").long_period == 60
    assert _find(exit_, "ma_crossover", "sell").long_period == 60
    _, exit2 = _extract_technical_signals("20일선 위에 있으면 매수, 20일선 깨면 매도")
    assert _find(exit2, "ma_crossover", "sell") is not None


def test_fundamental_operator_colloquial_synonyms():
    """'100% 아래'→<, '15%보다 높은'→> 구어체 연산자 동의어를 매핑한다."""
    filters = _extract_fundamental_filters("부채비율 100% 아래에 ROE는 15%보다 높은 곳")
    by_metric = {f.metric: (f.operator, f.value) for f in filters}
    assert by_metric["debt_ratio"] == ("<", 100.0)
    assert by_metric["roe_or_gpa"] == (">", 15.0)


def test_max_mdd_limit_neommyeon_and_hando():
    """'MDD 30% 넘으면'·'MDD 30% 한도'·'낙폭 20% 이상이면 중단' 모두 추출한다."""
    from engine.nl_parser import _extract_max_mdd_limit_pct
    assert _extract_max_mdd_limit_pct("MDD가 30% 넘으면 전량 청산") == 30.0
    assert _extract_max_mdd_limit_pct("MDD 30% 한도") == 30.0
    assert _extract_max_mdd_limit_pct("낙폭이 20% 이상이면 전체 중단") == 20.0


def test_hold_period_days_passed_phrase_with_particle():
    """'35일이 지나면 무조건 정리' → 35 거래일 보유."""
    from engine.nl_parser import _extract_hold_period_days
    assert _extract_hold_period_days("35일이 지나면 무조건 정리하는 전략") == 35


def test_apply_overrides_corrects_portfolio_fields_on_llm_path():
    """LLM이 종목수/MDD/체결시점을 틀려도 결정적 오버레이가 보정한다(명시값만)."""
    # LLM이 잘못 채운 베이스(종목수 10, MDD 없음, next_open)를 가정.
    base = make_base_strategy()
    out = _apply_prompt_overrides(
        base,
        "골든크로스 매수, 최대 7종목, MDD 30% 넘으면 전량 청산, 당일 종가 체결",
    )
    assert out.max_positions == 7
    assert out.max_mdd_limit_pct == 30.0
    assert out.execution_timing == "current_close"


def test_apply_overrides_does_not_clobber_capital_without_mention():
    """자금 언급 없는 수정 프롬프트는 initial_capital을 건드리지 않는다."""
    base = make_base_strategy().model_copy(update={"initial_capital": 50000000.0})
    out = _apply_prompt_overrides(base, "손절 10%로 바꿔줘")
    assert out.initial_capital == 50000000.0


def test_bollinger_sell_not_created_for_unrelated_exit_clause():
    """'볼린저 상단 돌파 매수, 데드크로스 청산'에서 볼린저 청산을 잘못 만들지 않는다."""
    entry, exit_ = _extract_technical_signals(
        "볼린저밴드 상단을 돌파하면 추세 매수, 데드크로스 청산"
    )
    assert _find(entry, "bollinger_bands", "buy") is not None
    assert _find(exit_, "bollinger_bands", "sell") is None
    assert _find(exit_, "ma_crossover", "sell") is not None


def test_adx_with_do_particle_and_neom_operator():
    """'ADX도 25를 넘어' — 조사 '도'와 동사 '넘어'에도 adx buy(>=25)를 잡는다."""
    entry, _ = _extract_technical_signals("MACD가 0선 위로 올라오고 ADX도 25를 넘어 추세가 살아있을 때 진입")
    adx = _find(entry, "adx", "buy")
    assert adx is not None and adx.value == 25.0 and adx.operator == ">="


def test_cci_buy_with_do_particle_and_jinip_verb():
    """'CCI도 -100 아래일 때만 진입' — 조사 '도' + '진입' 동사."""
    entry, _ = _extract_technical_signals("스토캐스틱 과매도 매수에 CCI도 -100 아래일 때만 진입")
    assert _find(entry, "cci", "buy").value == -100.0
    assert _find(entry, "stochastic", "buy") is not None


def test_stochastic_oversold_entry_with_jinip_verb():
    """'스토캐스틱 과매도 동시 충족 시 진입' — '진입' 동사로도 stochastic buy."""
    entry, _ = _extract_technical_signals("볼린저밴드 하단 매수 + 스토캐스틱 과매도 동시 충족 시 진입")
    assert _find(entry, "stochastic", "buy") is not None


def test_bare_overbought_word_sell_without_number():
    """'스토캐스틱 과매도 매수, 과매수에서 매도' — 숫자 없는 '과매수' 청산도 귀속(기본 80)."""
    entry, exit_ = _extract_technical_signals(
        "스토캐스틱 과매도에서 매수, 과매수에서 매도, 최대 6종목"
    )
    sell = _find(exit_, "stochastic", "sell")
    assert sell is not None and sell.value == 80.0


def test_rsi_numeric_threshold_preferred_over_colloquial():
    """'RSI 다이버전스 바닥 ... RSI 28 이하 진입' — 구어체보다 명시 숫자 28을 우선."""
    entry, _ = _extract_technical_signals(
        "RSI 다이버전스로 바닥 신호가 나오면 매수, RSI 28 이하 과매도에서 진입"
    )
    buy = _find(entry, "rsi", "buy")
    assert buy is not None and buy.value == 28.0


def test_macd_golden_does_not_create_spurious_macd_sell_from_far_deadcross():
    """'MACD 골든크로스 진입 ... 데드크로스 청산'에서 데드크로스는 ma_crossover sell이며,
    멀리 떨어진 데드크로스가 macd sell을 만들지 않는다."""
    entry, exit_ = _extract_technical_signals(
        "MACD 골든크로스로 진입, RSI가 75를 넘으면 익절하고 데드크로스에서 청산"
    )
    assert _find(entry, "macd", "buy") is not None
    assert _find(exit_, "macd", "sell") is None
    assert _find(exit_, "ma_crossover", "sell") is not None
    assert _find(exit_, "rsi", "sell").value == 75.0


# ─── 미지원 개념 감지 → LLM 폴백 위임 (침묵 누락 방지) ──────────────────────────


@pytest.mark.parametrize(
    "prompt,concept",
    [
        ("KOSDAQ에서 최근 20일 변동성이 낮은 종목을 매수, 손절 -8%", "volatility"),
        ("PBR 1.3 이하이면서 영업활동현금흐름이 흑자인 기업만 매수, 손절 -10%", "cash_flow"),
        ("KOSPI에서 배당수익률이 높은 종목을 8개 매수, 손절 -8%", "dividend"),
        ("KOSPI200을 섹터별로 나눠 섹터당 최대 2종목만 편입, 손절 -8%", "sector"),
        ("5일/20일/60일 EMA가 정배열된 종목만 매수, 20일선 이탈 시 청산", "ema_alignment"),
        ("골든크로스 매수, 상단 도달 시 절반 익절하고 나머지는 데드크로스에서 청산", "partial_exit"),
        ("ROE 12% 이상 종목 중 포트폴리오 현금 비중 10% 유지, 손절 -8%", "cash_weight"),
        ("PBR 1 이하 종목 매수, 밸류에이션 정상화 시점에 청산", "valuation_exit"),
        ("최근 60일 수익률이 시장보다 약한 종목은 제외하고 매수, 손절 -9%", "relative_to_market"),
        ("최근 4분기 연속 적자인 기업은 제외하고 ROE 10% 이상 매수, 손절 -10%", "profitability_sign"),
        # 흔한 퀀트 팩터지만 데이터 파이프라인이 없는 것들 — 침묵 누락 대신 안내 대상.
        # (EV/EBITDA는 KIS other-major-ratios 배선 후 지원 지표로 승격 — 아래 미포함.)
        ("ROIC 10% 이상 기업만 편입해줘", "roic"),
        ("베타 낮은 종목 위주로 10개 매수", "beta"),
        ("이자보상배율 3배 이상 기업만 매수, 손절 -10%", "interest_coverage"),
        ("피오트로스키 점수 7점 이상 종목 매수", "quality_score"),
        ("재고자산회전율 높은 기업 위주로 편입", "turnover_ratio"),
        ("자사주 매입 중인 기업을 매수, 손절 -8%", "buyback"),
        ("PCF 5 이하 저평가 종목 매수", "cash_flow"),
    ],
)
def test_unsupported_concept_routes_to_llm(prompt, concept):
    """스키마가 표현할 수 없는 개념이 섞이면 규칙 기반은 부분 파싱을 내놓지 않고 None을
    반환해 LLM 폴백에 위임한다(침묵 누락 방지)."""
    assert _mentions_unsupported_concept(prompt) == concept
    assert _parse_rule_based_strategy(prompt) is None


@pytest.mark.parametrize(
    "prompt",
    [
        "pbr 1이하 per 7이하 종목을 10개 사서 1년간 보유하는 전략",
        "KOSPI 종목 중 골든크로스 매수, 데드크로스 매도, 손절 8%",
        "골든크로스가 나오면 매수하고, 반대로 데드크로스가 나오면 매도",
        "코스피200에서 최근 60거래일 수익률 상위 종목을 20일 보유 후 매도, 최대 5종목",
        "스토캐스틱 20 이하에서 매수, 스토캐스틱 80 이상에서 매도",
        # 마진류·성장률은 지원 지표 — 미지원 팩터 확장이 이들을 오탐하면 안 된다.
        "영업이익률 15% 이상 종목을 10개 매수, 손절 -8%",
        "순이익률 10% 이상 매출총이익률 30% 이상 종목 매수, 손절 8%",
        "영업이익증가율 20% 이상 종목을 매수, 손절 -10%",
    ],
)
def test_supported_prompt_not_flagged_as_unsupported(prompt):
    """지원되는 개념만 담긴 프롬프트(상대강도 랭킹 포함)는 미지원으로 오탐되지 않는다."""
    assert _mentions_unsupported_concept(prompt) is None
    assert _parse_rule_based_strategy(prompt) is not None


STRATEGY_UI_SIGNAL_SUGGESTIONS = [
    ("진입 신호를 5일·20일 이동평균 골든크로스로 변경", "entry", "ma_crossover"),
    ("진입 신호를 RSI 30 이하 반등으로 변경", "entry", "rsi"),
    ("진입 신호를 20일 신고가 돌파로 변경", "entry", "breakout"),
    ("진입 신호를 MACD 골든크로스로 변경", "entry", "macd"),
    ("청산 신호를 5일·20일 이동평균 데드크로스로 변경", "exit", "ma_crossover"),
    ("청산 신호를 RSI 70 이상으로 변경", "exit", "rsi"),
    ("청산 신호를 20일 저점 이탈 시 매도로 변경", "exit", "breakout"),
]


@pytest.mark.parametrize("prompt,side,indicator", STRATEGY_UI_SIGNAL_SUGGESTIONS)
def test_strategy_ui_signal_suggestions_map_to_executable_conditions(
    prompt, side, indicator
):
    """Every signal suggestion exposed by Strategy UI must map to an engine condition."""
    from engine.nl_parser import build_unsupported_concept_notice
    from engine.strategy_converter import to_backtest_request

    assert build_unsupported_concept_notice(prompt) is None
    entry, exit_ = _extract_technical_signals(prompt)
    selected = entry if side == "entry" else exit_
    assert any(signal.indicator == indicator for signal in selected)

    parsed = ParsedStrategy(
        description=prompt,
        entry_signals=entry,
        exit_signals=exit_,
    )
    request = to_backtest_request(parsed, resolve_symbols=False)
    assert any(condition["id"] == indicator for condition in request[side]["conditions"])


@pytest.mark.parametrize(
    "prompt,_side,_indicator",
    [case for case in STRATEGY_UI_SIGNAL_SUGGESTIONS if case[1] == "entry"],
)
def test_strategy_ui_entry_suggestion_replaces_ranking_without_llm(
    monkeypatch, prompt, _side, _indicator
):
    """An exposed entry replacement must replace ranking and preserve unrelated fields."""
    parser = NLStrategyParser(backend="ollama")
    previous = make_base_strategy().model_copy(update={
        "fundamental_filters": [
            FundamentalFilter(metric="pbr", operator="<=", value=1.0),
        ],
        "entry_signals": [
            TechnicalSignal(indicator="ema", signal_type="buy", period=20),
        ],
        "exit_signals": [
            TechnicalSignal(
                indicator="rsi", signal_type="sell", period=14,
                operator=">=", value=70,
            ),
        ],
        "ranking_metric": "return",
        "ranking_lookback_days": 21,
        "max_positions": 5,
        "stop_loss_pct": 10.0,
    })

    def _must_not_call_llm(_user_input, _previous):
        raise AssertionError("An exposed entry replacement must not call the LLM")

    monkeypatch.setattr(parser, "_modify_ollama", _must_not_call_llm)
    parsed = parser.parse_modification(prompt, previous.model_dump())
    expected_entry, _ = _extract_technical_signals(prompt)

    assert parsed.entry_signals == expected_entry
    assert parsed.ranking_metric is None
    assert parsed.ranking_lookback_days is None
    assert parsed.exit_signals == previous.exit_signals
    assert parsed.fundamental_filters == previous.fundamental_filters
    assert parsed.max_positions == 5
    assert parsed.stop_loss_pct == 10.0


STRATEGY_UI_SETTING_SUGGESTIONS = [
    ("유니버스를 KOSPI200으로 변경", "universe", ["KOSPI200"]),
    ("유니버스를 KOSPI로 변경", "universe", ["KOSPI"]),
    ("유니버스를 KOSDAQ으로 변경", "universe", ["KOSDAQ"]),
    ("유니버스를 KOSPI와 KOSDAQ 전체 시장으로 변경", "universe", ["KOSPI", "KOSDAQ"]),
    ("20일 보유로 변경", "hold_period_days", 20),
    ("최대 5종목으로 변경", "max_positions", 5),
    ("분기 리밸런싱으로 변경", "rebalancing_period", "quarterly"),
    ("초기자금 1000만원으로 변경", "initial_capital", 10_000_000.0),
    ("손절을 10%로 변경", "stop_loss_pct", 10.0),
    ("익절을 20%로 변경", "take_profit_pct", 20.0),
    ("트레일링 스탑을 10%로 변경", "trailing_stop_pct", 10.0),
    ("MDD 20% 한도로 변경", "max_mdd_limit_pct", 20.0),
]


@pytest.mark.parametrize("prompt,field,expected", STRATEGY_UI_SETTING_SUGGESTIONS)
def test_strategy_ui_setting_suggestions_use_deterministic_modification_path(
    prompt, field, expected
):
    """Every non-signal suggestion must be applied without relying on an LLM guess."""
    from engine.nl_parser import _modify_rule_based, build_unsupported_concept_notice

    assert build_unsupported_concept_notice(prompt) is None
    modified = _modify_rule_based(prompt, make_base_strategy().model_dump())
    assert modified is not None
    assert getattr(modified, field) == expected


def test_strategy_ui_exposes_only_suggestions_covered_by_backend_contract():
    """A new UI suggestion must add an executable backend contract in this test module."""
    # CWD가 아니라 리포 루트 기준으로 읽는다 — pytest는 backend/에서 실행된다(CI 포함).
    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "app/analytics/new/conversationDecision.ts").read_text(encoding="utf-8")
    clarification_block = source.split(
        "const MODIFICATION_CLARIFICATIONS", 1
    )[1].split("export function getModificationClarification", 1)[0]
    exposed = {
        suggestion
        for payload in re.findall(r"suggestions:\s*\[([^\]]+)]", clarification_block)
        for suggestion in re.findall(r'"([^"]+)"', payload)
        if suggestion != "직접 입력"
    }
    covered = {
        prompt for prompt, *_rest in (
            STRATEGY_UI_SIGNAL_SUGGESTIONS + STRATEGY_UI_SETTING_SUGGESTIONS
        )
    }
    assert exposed == covered


def test_unsupported_concept_notice_names_all_concepts():
    """[침묵 왜곡 방지] 미지원 개념이 언급되면 사용자 안내 문구가 만들어지고,
    여러 개념이 섞이면 모두 라벨로 나열된다(LLM 폴백조차 스키마가 표현 불가하므로)."""
    from engine.nl_parser import build_unsupported_concept_notice

    # 배당수익률/배당성향(수치)은 지원 지표로 승격됨 — '배당 성장' 등 미지원 배당 개념만 안내.
    notice = build_unsupported_concept_notice("배당 성장주 위주로 매수")
    assert notice is not None
    assert "배당 조건" in notice
    assert "전략 요약" in notice  # 확인 유도 문구

    multi = build_unsupported_concept_notice("변동성 낮고 배당 잘 늘리는 종목 매수")
    assert multi is not None
    assert "변동성 조건" in multi and "배당 조건" in multi


def test_unsupported_concept_notice_none_for_supported_prompt():
    from engine.nl_parser import build_unsupported_concept_notice

    assert build_unsupported_concept_notice(
        "KOSPI 종목 중 골든크로스 매수, 데드크로스 매도, 손절 8%"
    ) is None


def test_volume_multiple_threshold_flagged_as_unsupported():
    """[침묵 왜곡 방지] '거래량 평소 대비 N배'의 배수 임계값은 volume_spike(OBV 크로스오버)가
    표현할 수 없다 — 조용히 버리는 대신 미지원 개념으로 안내하고 LLM 폴백에 위임한다."""
    from engine.nl_parser import build_unsupported_concept_notice

    prompt = "거래량이 평소보다 3배 이상 늘면 매수, 손절 8%"
    assert _mentions_unsupported_concept(prompt) == "volume_multiple"
    assert _parse_rule_based_strategy(prompt) is None  # 룰 파스가 부분 해석을 내놓지 않는다
    notice = build_unsupported_concept_notice(prompt)
    assert notice is not None and "거래량 배수" in notice

    # 역순 표현("평소 대비 2배 거래량")도 잡는다.
    assert _mentions_unsupported_concept("평소 대비 2배 거래량이면 매수") == "volume_multiple"
    # 배수 없는 '거래량 급증'은 지원 개념 — 오폴백하지 않는다.
    assert _mentions_unsupported_concept("거래량 급증하면 매수, 손절 8%") is None
    # 절 경계를 넘는 오탐 금지 — '3배'가 거래량이 아니라 수익 목표를 수식하는 경우.
    assert _mentions_unsupported_concept("거래량 급증 매수, 3배 수익 목표") is None


def test_news_condition_flagged_as_unsupported():
    """[침묵 왜곡 방지] 뉴스/공시 재료 조건은 스키마가 표현할 수 없다 — 지원 지표와 섞인
    혼합 요청은 룰 파스가 부분 해석을 내놓지 않고 LLM에 위임하며 notice로 알린다.
    (요청 전체가 뉴스 기반이면 intent.classifier가 UNSUPPORTED_FEATURE로 먼저 안내한다.)"""
    from engine.nl_parser import build_unsupported_concept_notice

    prompt = "RSI 30 이하에서 매수하고 호재 뉴스 있으면 익절, 손절 8%"
    assert _mentions_unsupported_concept(prompt) == "news"
    assert _parse_rule_based_strategy(prompt) is None
    notice = build_unsupported_concept_notice(prompt)
    assert notice is not None and "뉴스/공시 등 재료 조건" in notice


# ─── Rule Parse Guard: red-flag 결정론 선차단 ────────────────────────────────


@pytest.mark.parametrize(
    "prompt,category",
    [
        ("골든크로스 매수 데드크로스 매도, 손절 8% 가능해?", "question"),
        ("PBR 1 이하 종목 매수, 손절 -8% 어때요", "question"),
        ("골든크로스 전략이랑 RSI 전략 뭐가 더 나아", "comparison"),
        ("가치주 전략과 모멘텀 전략 비교해줘", "comparison"),
        ("아니 그게 아니라 손절을 -8%로 해줘", "correction"),
        ("저평가 우량주 좀 추천해줘", "recommendation"),
    ],
)
def test_rule_parse_red_flag_routes_to_llm(prompt, category):
    """질문·비교·정정·추천은 슬롯이 일부 매칭돼도 룰 파싱이 None을 반환해 위임한다."""
    assert _rule_parse_red_flag(prompt) == category
    assert _parse_rule_based_strategy(prompt) is None


@pytest.mark.parametrize(
    "prompt",
    [
        # 구어체 부정 '말고'는 정상 전략 서술 — red-flag로 오탐하면 안 된다.
        "너무 복잡한 조건 말고 PBR 1 이하 종목 8개 사서 6개월 보유, 손절 -12%",
        "너무 오래 끌지는 말고 52주 신고가 돌파 매수 20일 보유, 손절 -10%",
        # '대비'는 트레일링 스탑 — red-flag 아님.
        "골든크로스 매수, 최고가 대비 15% 하락 시 청산",
        "pbr 1이하 per 7이하 종목을 10개 사서 1년간 보유하는 전략",
    ],
)
def test_rule_parse_red_flag_not_triggered_on_valid_strategy(prompt):
    """정상 전략(구어체 부정 '말고'·트레일링 '대비' 포함)은 red-flag로 오탐되지 않는다."""
    assert _rule_parse_red_flag(prompt) is None
    assert _parse_rule_based_strategy(prompt) is not None


# ─── Rule Parse Guard: 잔여 커버리지 게이트 + LLM judge(opt-in) ──────────────


def test_rule_parse_unexplained_empty_for_clean_explicit_prompt():
    """알려진 어휘만으로 구성된 명시적 전략은 잔여가 거의 없다(애매하지 않음)."""
    residual = _rule_parse_unexplained("골든크로스 매수, 데드크로스 매도, 손절 8%")
    assert len(residual) < 6


def test_rule_parse_unexplained_keeps_unknown_content():
    """알려진 어휘로 설명 안 되는 문구는 잔여로 남는다(애매 → judge 위임 신호)."""
    residual = _rule_parse_unexplained(
        "골든크로스 매수, 데드크로스 매도, 손절 8%, 어쩌고저쩌고특별한무언가"
    )
    assert len(residual) >= 6


def test_rule_parse_unexplained_consumes_numeric_sector_synonym():
    """숫자를 품은 섹터 동의어('2차전지')가 숫자 제거로 조각나('차전지') 잔여로 남으면
    안 된다 — 어휘 차감이 숫자 제거보다 먼저여야 룰 파스 즉답이 불필요한 LLM 검증을 피한다."""
    assert _rule_parse_unexplained("2차전지 관련주 골든크로스 매수, 손절 5%") == ""


def test_rule_parse_unexplained_consumes_generic_target_words():
    """필드 의미가 없는 일반어('대상', '중')는 잔여로 치지 않는다."""
    assert _rule_parse_unexplained("반도체 관련주 대상으로 골든크로스 전략, 손절 5%") == ""


def test_consult_guard_accepts_without_llm_when_flag_disabled(monkeypatch):
    """opt-in 플래그가 꺼져 있으면 LLM을 호출하지 않고 즉시 수락한다."""
    monkeypatch.delenv("NL_RULE_GUARD_LLM", raising=False)
    parser = NLStrategyParser(backend="ollama")

    def _boom(*_a, **_k):
        raise AssertionError("LLM should not be called when guard is disabled")

    monkeypatch.setattr(parser, "chat", _boom)
    parsed = _parse_rule_based_strategy("골든크로스 매수, 데드크로스 매도, 손절 8%")
    assert parser._consult_rule_parse_guard("골든크로스 매수, 데드크로스 매도, 손절 8%", parsed) is True


def test_consult_guard_skips_llm_for_clean_prompt_even_when_enabled(monkeypatch):
    """플래그가 켜져도 잔여가 없는 명시적 전략은 judge를 호출하지 않는다(애매한 경우에만)."""
    monkeypatch.setenv("NL_RULE_GUARD_LLM", "1")
    parser = NLStrategyParser(backend="ollama")
    monkeypatch.setattr(parser, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    prompt = "골든크로스 매수, 데드크로스 매도, 손절 8%"
    parsed = _parse_rule_based_strategy(prompt)
    assert parser._consult_rule_parse_guard(prompt, parsed) is True


def test_consult_guard_falls_back_when_judge_says_so(monkeypatch):
    """플래그 ON + 잔여 있음 + judge가 fallback → False(LLM 폴백)."""
    monkeypatch.setenv("NL_RULE_GUARD_LLM", "1")
    parser = NLStrategyParser(backend="ollama")
    monkeypatch.setattr(
        parser, "chat",
        lambda *a, **k: '{"decision": "fallback_llm_parse", "confidence": 0.4, "reason": "부분 매칭"}',
    )
    prompt = "골든크로스 매수, 데드크로스 매도, 손절 8%, 어쩌고저쩌고특별한무언가"
    parsed = _parse_rule_based_strategy(prompt)
    assert parser._consult_rule_parse_guard(prompt, parsed) is False


def test_consult_guard_accepts_when_judge_approves(monkeypatch):
    """플래그 ON + 잔여 있음 + judge가 accept → True(룰 파스 유지)."""
    monkeypatch.setenv("NL_RULE_GUARD_LLM", "1")
    parser = NLStrategyParser(backend="ollama")
    monkeypatch.setattr(
        parser, "chat",
        lambda *a, **k: '{"decision": "accept_rule", "confidence": 0.95, "reason": "완전"}',
    )
    prompt = "골든크로스 매수, 데드크로스 매도, 손절 8%, 어쩌고저쩌고특별한무언가"
    parsed = _parse_rule_based_strategy(prompt)
    assert parser._consult_rule_parse_guard(prompt, parsed) is True


def test_consult_guard_accepts_on_llm_error(monkeypatch):
    """judge 호출이 예외를 던져도 보수적으로 수락(True)해 빠른 경로를 깨지 않는다."""
    monkeypatch.setenv("NL_RULE_GUARD_LLM", "1")
    parser = NLStrategyParser(backend="ollama")
    monkeypatch.setattr(parser, "chat", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    prompt = "골든크로스 매수, 데드크로스 매도, 손절 8%, 어쩌고저쩌고특별한무언가"
    parsed = _parse_rule_based_strategy(prompt)
    assert parser._consult_rule_parse_guard(prompt, parsed) is True


def test_parse_routes_to_llm_when_guard_rejects(monkeypatch):
    """통합: judge가 fallback이면 parse()가 룰 파스 대신 LLM 경로로 빠진다."""
    monkeypatch.setenv("NL_RULE_GUARD_LLM", "1")
    parser = NLStrategyParser(backend="ollama")
    monkeypatch.setattr(
        parser, "chat",
        lambda *a, **k: '{"decision": "fallback_llm_parse", "confidence": 0.3, "reason": "x"}',
    )
    sentinel = _build_fallback_strategy("LLM 경로 결과")
    monkeypatch.setattr(parser, "_parse_ollama", lambda _ui: sentinel)
    result = parser.parse("골든크로스 매수, 데드크로스 매도, 손절 8%, 어쩌고저쩌고특별한무언가")
    # 룰 파스였다면 description=원문 프롬프트. LLM 경로 sentinel의 description이 보존되면 폴백됨.
    assert result.description == "LLM 경로 결과"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"decision": "accept_rule"}', "accept_rule"),
        ('{"decision": "fallback_llm_parse"}', "fallback_llm_parse"),
        ('쓰레기 출력 no json', "accept_rule"),  # 파싱 실패 → 보수적 수락
        ('{"decision": "ask_clarification"}', "accept_rule"),  # 폴백 전용: 그 외는 수락
    ],
)
def test_extract_guard_decision(raw, expected):
    assert _extract_guard_decision(raw) == expected


# ─── 백테스트 기간 3-state: cue 봤는데 못 풀면 LLM/되묻기 위임 ──────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "백테스트 1주일로 해줘",
        "백테스트 6개월로 해줘",
        "백테스트를 일주일로 돌려줘",
        "백테스트 기간을 10일로 해줘",
        "백테스트 며칠로만 해줘",
    ],
)
def test_backtest_period_unresolved_when_cue_seen_but_unmappable(prompt):
    """백테스트 기간 의도는 있는데 유효 버킷으로 못 풀면 'unresolved' → 룰이 None 반환."""
    from engine.nl_parser import _backtest_period_state

    assert _backtest_period_state(prompt) == "unresolved"


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("백테스트 1년으로 해줘", "parsed"),
        ("백테스트 3년으로 해줘", "parsed"),
        ("백테스트 2년으로 해줘", "parsed"),  # 버킷은 아니지만 오늘 기준 명시 날짜로 해석
        ("백테스트 4년으로 해줘", "parsed"),
        ("백테스트 24개월로 해줘", "parsed"),  # 개월(≥12)도 명시 날짜로 해석
        ("백테스트 전체 기간으로 해줘", "parsed"),
        ("2002년부터 2005년까지 백테스트", "parsed"),
        ("pbr 1 이하 종목 10개 보유", "not_mentioned"),
        ("한 번 사면 20일 보유 후 매도", "not_mentioned"),  # 보유기간은 백테스트 기간 아님
    ],
)
def test_backtest_period_state_valid_or_absent(prompt, expected):
    """유효 기간(1/3/5y·전체·연도범위)은 parsed, 백테스트 기간 언급이 없으면 not_mentioned."""
    from engine.nl_parser import _backtest_period_state

    assert _backtest_period_state(prompt) == expected


def test_unresolved_backtest_period_defers_full_strategy_to_llm():
    """완성된 전략 + 1년 미만 백테스트 기간이면 부분 파싱하지 않고 None(→LLM)."""
    assert (
        _parse_rule_based_strategy("pbr 1 이하 종목 10개 매수, 백테스트 1주일로 해줘")
        is None
    )


# ─── 리밸런싱 주기 3-state (3-state 패턴을 다른 필드로 확장) ─────────────────────


@pytest.mark.parametrize(
    "prompt",
    [
        "10일마다 리밸런싱 해줘",
        "2주마다 리밸런싱으로 바꿔줘",
        "리밸런싱은 5일에 한번씩",
        "PBR 1 이하 종목, 7일마다 재조정",
    ],
)
def test_rebalancing_period_unresolved_when_cadence_unmappable(prompt):
    """리밸런싱 의도는 있는데 주기가 enum으로 안 풀리면(일/주 케이던스) 'unresolved'."""
    from engine.nl_parser import _rebalancing_period_state

    assert _rebalancing_period_state(prompt) == "unresolved"


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("매월 리밸런싱", "parsed"),
        ("분기마다 리밸런싱", "parsed"),
        ("매주 순위를 다시 산정", "parsed"),
        ("리밸런싱 해줘", "not_mentioned"),  # 주기 미지정은 실패 아님(기본값 적용)
        ("pbr 1 이하 10종목 보유", "not_mentioned"),
        ("한 번 사면 20일 보유 후 매도", "not_mentioned"),
    ],
)
def test_rebalancing_period_state_valid_or_absent(prompt, expected):
    from engine.nl_parser import _rebalancing_period_state

    assert _rebalancing_period_state(prompt) == expected


def test_unmappable_rebalancing_defers_full_strategy_to_llm():
    """완성된 전략 + 매핑 불가 리밸런싱 주기면 부분 파싱하지 않고 None(→LLM)."""
    assert (
        _parse_rule_based_strategy("pbr 1 이하 종목 10개 매수, 10일마다 리밸런싱")
        is None
    )


# ─── 표현 확장 회귀(synonym coverage) ────────────────────────────────────────
# 룰베이스 파서에 비슷한 상황/표현을 결정적으로 추가한 것에 대한 회귀 테스트.


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("유가증권시장에서 per 10 이하", ["KOSPI"]),
        ("거래소시장 종목 중 roe 15 이상", ["KOSPI"]),
        ("양시장 전체에서 pbr 1 이하", ["KOSPI", "KOSDAQ"]),
        ("코스피코스닥 전부 대상으로", ["KOSPI", "KOSDAQ"]),
        ("국내전체 종목", ["KOSPI", "KOSDAQ"]),
        ("전종목 대상으로 pbr 1 이하", ["KOSPI", "KOSDAQ"]),
        ("블루칩 중에서 roe 15 이상", ["KOSPI200"]),
        ("대형우량주 위주로", ["KOSPI200"]),
    ],
)
def test_universe_synonyms(prompt, expected):
    assert _extract_explicit_universe(prompt) == expected


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("per 10 넘으면", ("per", ">", 10.0)),
        ("per 10 넘기면", ("per", ">", 10.0)),
        ("roe가 15 보다 큰 종목", ("roe_or_gpa", ">", 15.0)),
        ("pbr 1 보다 작은", ("pbr", "<", 1.0)),
    ],
)
def test_operator_synonyms(prompt, expected):
    filters = _extract_fundamental_filters(prompt)
    assert (filters[0].metric, filters[0].operator, filters[0].value) == expected


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("주가수익비율 10 이하", ("per", "<=", 10.0)),
        ("주가순자산비율 1 이하", ("pbr", "<=", 1.0)),
        ("자기자본이익률 15 이상", ("roe_or_gpa", ">=", 15.0)),
        ("주가매출비율 2 이하", ("psr", "<=", 2.0)),
        ("총자산이익률 5 이상", ("roa", ">=", 5.0)),
        ("시총 5000억 이상", ("market_cap", ">=", 5000.0)),
    ],
)
def test_fundamental_korean_full_names(prompt, expected):
    filters = _extract_fundamental_filters(prompt)
    assert (filters[0].metric, filters[0].operator, filters[0].value) == expected


@pytest.mark.parametrize(
    "prompt",
    ["종가체결로 매매", "당일 종가 체결", "종가에 매수", "종가매매"],
)
def test_execution_timing_close_synonyms(prompt):
    from engine.nl_parser import _extract_execution_timing

    assert _extract_execution_timing(prompt) == "current_close"


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("고점대비 12% 하락하면 청산", 12.0),
        ("최고점 대비 8% 떨어지면 매도", 8.0),
        ("고가 대비 10% 밀리면 손절", 10.0),
    ],
)
def test_trailing_stop_synonyms(prompt, expected):
    assert extract_risk_field_overrides(prompt).get("trailing_stop_pct") == expected


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("드로우다운 25% 도달하면 중단", 25.0),
        ("드로다운 20% 넘으면 청산", 20.0),
        ("최대낙폭 30% 찍으면 전량청산", 30.0),
    ],
)
def test_mdd_synonyms(prompt, expected):
    from engine.nl_parser import _extract_max_mdd_limit_pct

    assert _extract_max_mdd_limit_pct(prompt) == expected


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("2년 보유", 504),
        ("3주 보유", 15),
        ("분기보유", 63),
        ("반기보유", 126),
    ],
)
def test_hold_period_synonyms(prompt, expected):
    from engine.nl_parser import _extract_hold_period_days

    assert _extract_hold_period_days(prompt) == expected


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("해마다 리밸런싱", "yearly"),
        ("1년마다 재선정", "yearly"),
        ("데일리 리밸런싱", "daily"),
        ("위클리 리밸런싱", "weekly"),
        ("다달이 재조정", "monthly"),
        ("쿼터마다 리밸런싱", "quarterly"),
    ],
)
def test_rebalancing_synonyms(prompt, expected):
    assert _extract_rebalancing_period(prompt, None) == expected


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("5천만으로 시작", 50_000_000.0),
        ("초기자금 500백만원", 500_000_000.0),
        ("3천만원 투자", 30_000_000.0),
    ],
)
def test_initial_capital_synonyms(prompt, expected):
    assert _extract_initial_capital(prompt) == expected


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("초기 자금은 300으로", 3_000_000.0),   # 단위 없는 맨숫자 → 만원
        ("초기자금 300만으로", 3_000_000.0),     # '원' 생략
        ("초기자금 5000으로", 50_000_000.0),
    ],
)
def test_extract_capital_amount_reads_bare_number_as_manwon(prompt, expected):
    # [회귀] 자본금 cue 옆 단위 없는 숫자를 만원으로 해석한다(allow_bare). cue 맥락에서만.
    from engine.nl_parser import _extract_capital_amount
    assert _extract_capital_amount(prompt, allow_bare=True) == expected


def test_extract_capital_amount_bare_disabled_without_allow_bare():
    # allow_bare=False(일반 파싱)에서는 단위 없는 숫자를 자본금으로 잡지 않는다(None).
    from engine.nl_parser import _extract_capital_amount
    assert _extract_capital_amount("초기 자금은 300으로") is None
    # RSI 임계값 등 다른 수치도 자본금으로 오인하지 않는다.
    assert _extract_capital_amount("RSI 30 이하로 떨어지면 매수", allow_bare=True) is None


def test_modify_bare_capital_amount_updates_summary():
    # [회귀] '초기 자금은 300으로'가 기본값(10M)으로 침묵 폴백돼 요약이 안 바뀌던 버그.
    # 자본금을 300만원으로 결정론 반영한다(LLM 검증 레이어 도달 전 잘못된 확정 방지).
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_copy(update={"initial_capital": 10_000_000.0})
    parsed = _modify_rule_based("초기 자금은 300으로", prev.model_dump())
    assert parsed is not None
    assert parsed.initial_capital == 3_000_000.0


def test_modify_capital_cue_without_amount_delegates_to_llm():
    # 금액 없는 자본금 수정('초기자금 늘려줘')은 기본값으로 조용히 확정하지 말고 LLM에 위임한다.
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_copy(update={"initial_capital": 50_000_000.0})
    assert _modify_rule_based("초기자금 늘려줘", prev.model_dump()) is None


def test_modify_stop_loss_number_not_misread_as_capital():
    # 자본금 cue가 없으면 손절 수치(10)를 자본금으로 오인하지 않는다(맨숫자는 cue 인접만 인정).
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_copy(update={"initial_capital": 50_000_000.0})
    parsed = _modify_rule_based("손절 10%로 바꿔줘", prev.model_dump())
    assert parsed is not None
    assert parsed.stop_loss_pct == 10.0
    assert parsed.initial_capital == 50_000_000.0


def test_enforce_initial_capital_minimum_clamps_and_notifies():
    # [회귀] 300원 같은 하한 미만 입력은 100만원으로 보정하고 안내 문구를 반환한다.
    from engine.nl_parser import enforce_initial_capital_minimum, MIN_INITIAL_CAPITAL
    parsed = make_base_strategy().model_copy(update={"initial_capital": 300.0})
    notice = enforce_initial_capital_minimum(parsed)
    assert parsed.initial_capital == MIN_INITIAL_CAPITAL == 1_000_000.0
    assert notice is not None and "100만원" in notice


def test_enforce_initial_capital_minimum_leaves_valid_amount():
    # 하한 이상이면 보정하지 않고 안내도 없다(None).
    from engine.nl_parser import enforce_initial_capital_minimum
    parsed = make_base_strategy().model_copy(update={"initial_capital": 3_000_000.0})
    assert enforce_initial_capital_minimum(parsed) is None
    assert parsed.initial_capital == 3_000_000.0


def test_enforce_strategy_minimums_clamps_hold_and_lookback():
    # [회귀] 보유기간 0일→1일, 모멘텀/랭킹 기준 기간 3일→10일로 보정하고 안내한다.
    from engine.nl_parser import enforce_strategy_minimums
    parsed = make_base_strategy().model_copy(update={
        "hold_period_days": 0,
        "ranking_metric": "return",
        "ranking_lookback_days": 3,
    })
    notices = enforce_strategy_minimums(parsed)
    assert parsed.hold_period_days == 1
    assert parsed.ranking_lookback_days == 10
    assert any("보유기간" in n for n in notices)
    assert any("기준 기간" in n for n in notices)


def test_enforce_strategy_minimums_drops_nonpositive_ratios():
    # 0% 리스크 비율은 적용하지 않고(None) 안내한다. 음수는 모델 검증이 절댓값으로
    # 정규화하므로 여기 오지 않는다(test_parsed_strategy_normalizes_negative_ratio_sign).
    from engine.nl_parser import enforce_strategy_minimums
    parsed = make_base_strategy().model_copy(update={
        "stop_loss_pct": 0.0,
        "take_profit_pct": 0.0,
        "trailing_stop_pct": 10.0,  # 유효 → 유지
    })
    notices = enforce_strategy_minimums(parsed)
    assert parsed.stop_loss_pct is None
    assert parsed.take_profit_pct is None
    assert parsed.trailing_stop_pct == 10.0
    assert sum("0%보다 커야" in n for n in notices) == 2


def test_parsed_strategy_normalizes_negative_ratio_sign():
    # [회귀] "손절은 -8%"를 LLM이 부호 그대로 -8.0으로 옮기면, 하한선 보정이
    # "0%보다 커야 해서 적용하지 않았어요" 오탐 notice와 함께 값을 드롭했다
    # (배지는 결정적 risk_overrides의 +8과 함께 표시돼 안내와 모순).
    # 리스크 비율은 방향이 필드 의미에 내장돼 있어 음수=하락 폭 크기 → 절댓값 정규화.
    from engine.nl_parser import ParsedStrategy, ParsedStrategyDiff, enforce_strategy_minimums
    parsed = ParsedStrategy(
        description="손절은 -8%",
        stop_loss_pct=-8.0,
        take_profit_pct=-15.0,
        trailing_stop_pct=-10.0,
        max_mdd_limit_pct=-20.0,
    )
    assert parsed.stop_loss_pct == 8.0
    assert parsed.take_profit_pct == 15.0
    assert parsed.trailing_stop_pct == 10.0
    assert parsed.max_mdd_limit_pct == 20.0
    assert enforce_strategy_minimums(parsed) == []
    # 수정 모드(diff) 경로도 동일하게 정규화된다
    assert ParsedStrategyDiff(stop_loss_pct=-8.0).stop_loss_pct == 8.0


def test_enforce_strategy_minimums_leaves_valid_strategy_untouched():
    # 모든 값이 하한 이상이면 보정도 안내도 없다(빈 리스트).
    from engine.nl_parser import enforce_strategy_minimums
    parsed = make_base_strategy().model_copy(update={
        "initial_capital": 5_000_000.0,
        "hold_period_days": 20,
        "ranking_metric": "return",
        "ranking_lookback_days": 60,
        "stop_loss_pct": 10.0,
    })
    assert enforce_strategy_minimums(parsed) == []


@pytest.mark.parametrize(
    "prompt",
    [
        "최근 60일 수익률 랭킹 상위 10종목",
        "모멘텀 강한 상위 5종목",
        "등락률 순으로 상위 종목",
    ],
)
def test_ranking_synonyms(prompt):
    from engine.nl_parser import _extract_ranking

    metric, _ = _extract_ranking(prompt)
    assert metric == "return"


# ─── 품사(동사 활용형·조사) 확장 회귀 ────────────────────────────────────────
# 매수/매도 동사의 활용형·유의어(정리/처분/매각/매입/편입/담다)와 보조사 '도'를
# 결정적으로 인식하는지 검증.


@pytest.mark.parametrize(
    "prompt,exp_entry,exp_exit",
    [
        ("rsi 70 이상이면 처분", [], [("rsi", "sell", 70.0)]),
        ("rsi 30 이하면 매입, 70 이상 정리", [("rsi", "buy", 30.0)], [("rsi", "sell", 70.0)]),
        ("스토캐스틱 20 이하 편입, 80 이상 매각",
         [("stochastic", "buy", 20.0)], [("stochastic", "sell", 80.0)]),
        ("cci -100 이하 담고, 100 이상 처분",
         [("cci", "buy", -100.0)], [("cci", "sell", 100.0)]),
        ("rsi 30 이하로 떨어지면 매입", [("rsi", "buy", 30.0)], []),
    ],
)
def test_verb_conjugation_synonyms(prompt, exp_entry, exp_exit):
    entry, exit_ = _extract_technical_signals(prompt)
    assert [(s.indicator, s.signal_type, s.value) for s in entry] == exp_entry
    assert [(s.indicator, s.signal_type, s.value) for s in exit_] == exp_exit


@pytest.mark.parametrize(
    "prompt,field,expected",
    [
        ("수익이 20% 나면 처분", "take_profit_pct", 20.0),
        ("10% 하락하면 정리", "stop_loss_pct", 10.0),
        ("수익 15% 나면 매각", "take_profit_pct", 15.0),
    ],
)
def test_risk_verb_synonyms(prompt, field, expected):
    assert extract_risk_field_overrides(prompt).get(field) == expected


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("per도 10 이하", ("per", "<=", 10.0)),
        ("roe도 15 이상", ("roe_or_gpa", ">=", 15.0)),
    ],
)
def test_fundamental_auxiliary_particle_do(prompt, expected):
    filters = _extract_fundamental_filters(prompt)
    assert (filters[0].metric, filters[0].operator, filters[0].value) == expected


# ─── 오타·맞춤법·띄어쓰기 내성 회귀 ──────────────────────────────────────────
# 띄어쓰기 오류는 공백 제거(compact)로, 글자 단위 오타는 _TYPO_CORRECTIONS로 흡수된다.


@pytest.mark.parametrize(
    "prompt,exp_entry_inds,exp_exit_inds",
    [
        ("골드크로스 매수, 데트크로스 매도", ["ma_crossover"], ["ma_crossover"]),
        ("볼린져 하단에서 매수", ["bollinger_bands"], []),
        ("스토케스틱 20 이하 매수", ["stochastic"], []),
        ("스토하스틱 20 이하 매수", ["stochastic"], []),
        # 극단적 띄어쓰기 오류도 공백 제거로 흡수.
        ("골 든 크 로 스 매수", ["ma_crossover"], []),
    ],
)
def test_typo_and_spacing_in_signals(prompt, exp_entry_inds, exp_exit_inds):
    entry, exit_ = _extract_technical_signals(prompt)
    assert [s.indicator for s in entry] == exp_entry_inds
    assert [s.indicator for s in exit_] == exp_exit_inds


def test_typo_rebalancing_and_trailing_and_fee():
    assert _extract_rebalancing_period("한달에한번 리벨런싱", None) == "monthly"
    assert extract_risk_field_overrides("트레이링 10%").get("trailing_stop_pct") == 10.0
    from engine.nl_parser import _extract_rate

    assert _extract_rate("수수로 0.1%", "수수료", 0.015) == 0.1


def test_typo_take_profit_iksul_variant():
    # [회귀] '익설'(익절 오타)로 익절 % 를 인식하지 못해 "요청을 전략 변경으로 해석하지
    # 못해 전략을 유지했다"는 안내가 잘못 뜨던 버그(2026-07-21).
    assert extract_risk_field_overrides("30% 익설 설정해줘") == {"take_profit_pct": 30.0}


def test_typo_universe_and_momentum_ranking():
    from engine.nl_parser import _extract_ranking

    assert _extract_explicit_universe("코스탁 종목 중 per 10 이하") == ["KOSDAQ"]
    assert _extract_ranking("모맨텀 상위 10종목")[0] == "return"


def test_spacing_in_fundamental_filters():
    # 'p b r 1 이하'처럼 영문 지표명 사이 공백도 흡수.
    filters = _extract_fundamental_filters("p b r 1 이하, r o e 15 이상")
    pairs = {(f.metric, f.value) for f in filters}
    assert ("pbr", 1.0) in pairs
    assert ("roe_or_gpa", 15.0) in pairs


def test_typo_correction_preserves_original_description():
    # 오타 보정은 매칭용 compact에만 적용되고 원문(description)은 보존돼야 한다.
    parsed = _parse_rule_based_strategy("골드크로스 매수, 데트크로스 매도, 10종목")
    assert parsed is not None
    assert parsed.description == "골드크로스 매수, 데트크로스 매도, 10종목"


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("종목은 5게", 5),
        ("종목은 120게", 100),     # le=100 상한으로 클램프
        ("5게 이상 보유", 5),
        ("종목 10게로", 10),
    ],
)
def test_typo_count_unit_ge_is_corrected_to_gae(prompt, expected):
    # [회귀] 숫자 뒤 '게'(개 오타)를 종목 수 단위로 인식한다. "종목은 5게"가 무시되던 버그.
    from engine.nl_parser import _extract_max_positions
    assert _extract_max_positions(prompt) == expected


def test_typo_count_unit_does_not_corrupt_real_words():
    # '게'로 시작하는 단어(게임 등)는 보정하지 않는다(120게임 → 120개 아님).
    from engine.nl_parser import _extract_max_positions
    assert _extract_max_positions("120게임 만들기") is None


def test_modify_count_typo_updates_max_positions():
    # [회귀] 전략 수정 "종목은 5게"가 max_positions를 5로 반영한다(오타로 미반영되던 버그).
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_copy(update={"max_positions": 8})
    parsed = _modify_rule_based("종목은 5게", prev.model_dump())
    assert parsed is not None
    assert parsed.max_positions == 5


def test_llm_prompts_carry_typo_tolerance_guidance():
    # [회귀] 결정적 정규화가 못 잡는 미지의 오타는 LLM이 의미로 해석하도록 프롬프트가 안내해야 한다
    # (수정/생성 파서 + 검증기). 결정적 규칙과 LLM 안전망의 이중 방어.
    from engine.nl_parser import MODIFY_PROMPT, SYSTEM_PROMPT, COMPACT_SYSTEM_PROMPT
    from engine.parse_validator import PARSE_VALIDATION_PROMPT
    assert "오타" in MODIFY_PROMPT
    assert "오타" in SYSTEM_PROMPT
    assert "오타" in COMPACT_SYSTEM_PROMPT
    assert "typo" in PARSE_VALIDATION_PROMPT.lower()


# ── 섹터/업종 조건 (FR-STR-024) ──────────────────────────────────────────────

def test_extract_sector_deterministic():
    from engine.nl_parser import _extract_sector
    assert _extract_sector("반도체 관련주 매수") == "반도체"
    assert _extract_sector("2차전지 업종만 대상으로") == "이차전지"
    assert _extract_sector("제약주 위주로") == "바이오/제약"
    assert _extract_sector("AI 관련주") == "소프트웨어/플랫폼"
    # '중심/위주'도 범위를 좁히는 업종 큐다 — "반도체 중심으로 전략을 만들어줘".
    assert _extract_sector("반도체 중심으로 전략을 만들어줘") == "반도체"
    assert _extract_sector("2차전지 위주로 골라줘") == "이차전지"
    # '분야'도 업종 큐다 — 누락 시 수정 병합에서 이전 섹터(반도체)가 유지되던 회귀.
    assert _extract_sector("바이오분야 전략을 만들어 볼까?") == "바이오/제약"
    assert _extract_sector("자동차 분야로 해줘") == "자동차"
    # '주가'는 업종 큐가 아니다 — '반도체 주가가 오르면'을 섹터로 오인하지 않는다.
    assert _extract_sector("반도체 주가가 오르면 매수") is None
    # 지원 목록 밖 업종은 결정적으로 잡지 않는다(LLM 위임 + 미지원 안내).
    assert _extract_sector("메타버스 관련주 매수") is None
    # '로봇'은 독립 정본 섹터다(2026-07-13 신설 — 사명 기준 분류, sector_mapper 파생).
    assert _extract_sector("로봇 관련주 매수") == "로봇"


def test_extract_sector_bare_related_and_theme_cues():
    # [회귀] '관련주' 어순만 보던 큐가 "반도체 관련 전략"·"2차전지 테마"를 놓쳤다 —
    # 같은 계열의 "로봇주 관련 전략"이 안내 없이 전체 시장으로 백테스트되던 사고.
    from engine.nl_parser import _extract_sector
    assert _extract_sector("반도체 관련 전략 만들어줘") == "반도체"
    assert _extract_sector("2차전지 테마 전략") == "이차전지"


def test_extract_sector_cue_less_distinctive_theme():
    # [회귀] "2차전지 전략을 만들자"처럼 큐(관련/업종/테마) 없이 맨 테마명만 말하면 결정적
    # 추출도, 안전망인 LLM(8B)도 sector를 못 잡고 조용히 KOSPI200 전체로 새던 사고.
    # 고유 테마어는 큐 없이도 단독으로 잡는다(회사명 조각·일반어는 제외).
    from engine.nl_parser import _extract_sector
    assert _extract_sector("2차전지 전략을 만들자") == "이차전지"
    assert _extract_sector("배터리 전략 만들어줘") == "이차전지"
    assert _extract_sector("반도체 전략 만들어줘") == "반도체"
    assert _extract_sector("바이오 전략") == "바이오/제약"
    assert _extract_sector("반도체소재 전략") == "반도체 소재"
    assert _extract_sector("2차전지로 골라줘") == "이차전지"
    # 회사명에 붙은 조각은 업종 언급이 아니다 — 원문 경계 검사로 배제한다.
    assert _extract_sector("LG화학 골든크로스") is None
    assert _extract_sector("삼성증권 담아줘") is None
    assert _extract_sector("SFA반도체 전략") is None
    # 더 긴 단어의 일부('바이오리듬')·모호한 산업 일반어(은행·조선)는 큐 없이 잡지 않는다.
    assert _extract_sector("바이오리듬 전략") is None
    assert _extract_sector("은행 전략") is None
    assert _extract_sector("조선 전략") is None
    # 뒤에 시황/주가 명사가 오면 업종 제한이 아니라 가격 서술이다 — 큐 규칙 '주(?!가)'와 동일 취지.
    assert _extract_sector("2차전지 주가가 오르면") is None
    assert _extract_sector("반도체 시장이 좋으면") is None


def test_extract_sector_section_misnomer_cue():
    # [회귀] '섹션'은 '섹터'의 통용 오칭 — "반도체 섹션 종목만 테스트 해보자"가 결정적
    # 추출을 빠져나가 LLM 폴백으로 새고, LLM 미가용 시 타임아웃까지 이어지던 사고.
    from engine.nl_parser import _extract_sector
    assert _extract_sector("반도체 섹션 종목만 테스트 해보자") == "반도체"
    assert _extract_sector("2차전지 섹션으로 바꿔줘") == "이차전지"


def test_unsupported_sector_word_orders_flagged():
    # 목록 밖 업종은 어순('메타버스주 관련'·'메타버스 테마')과 무관하게 미지원 안내가 남아야 한다.
    from engine.nl_parser import build_unsupported_concept_notice
    assert build_unsupported_concept_notice("메타버스주 관련 전략을 만들어보자") is not None
    assert build_unsupported_concept_notice("메타버스 테마 전략 만들어줘") is not None
    # 업종 무관 표현은 섹터 제한 언급이 아니다 — 안내를 내지 않는다.
    assert build_unsupported_concept_notice("업종 상관없이 코스피 모멘텀 전략") is None


def test_unsupported_concept_notice_can_exclude_sector():
    # 미해결 섹터를 되묻기로 능동 처리할 때는 안내에서 'sector'를 뺀다(중복 방지).
    from engine.nl_parser import build_unsupported_concept_notice
    # 섹터만 미지원이면 exclude 시 안내 없음.
    assert build_unsupported_concept_notice("재약주 관련 전략을 만들자", exclude={"sector"}) is None
    # 다른 미지원 개념(변동성)은 남는다.
    notice = build_unsupported_concept_notice("변동성 낮은 메타버스 관련주", exclude={"sector"})
    assert notice is not None and "변동성" in notice and "섹터" not in notice


def test_unresolved_sector_triggers_reask_clarification():
    # [회귀] '재약주 관련 전략을 만들자' — 오타/목록 밖 업종을 조용히 전체 시장으로 강등하지
    # 않고 되묻는다(칩은 파서가 되받을 수 있게 큐 동반).
    from engine.nl_parser import (
        ParsedStrategy, detect_unresolved_sector_clarification, _extract_sector,
    )
    parsed = ParsedStrategy(description="재약주", universe=["KOSPI200"])
    q, s = detect_unresolved_sector_clarification(parsed, "재약주 관련 전략을 만들자")
    assert q is not None and "다시 알려주시겠어요" in q
    assert "업종 상관없음" in s
    # 칩은 재파싱 시 결정적으로 섹터로 잡혀야 한다(되묻기 답이 실제로 반영되도록).
    assert _extract_sector("바이오/제약 관련주") == "바이오/제약"
    assert _extract_sector("반도체 관련주") == "반도체"


def test_resolved_sector_does_not_reask():
    # 지원 업종이 이미 잡혔거나 업종 언급이 없으면 되묻지 않는다.
    from engine.nl_parser import ParsedStrategy, detect_unresolved_sector_clarification
    assert detect_unresolved_sector_clarification(
        ParsedStrategy(description="x", sector="반도체"), "반도체 관련주"
    ) == (None, None)
    assert detect_unresolved_sector_clarification(
        ParsedStrategy(description="x"), "코스피 모멘텀 전략"
    ) == (None, None)


def test_sector_llm_parse_prompts_instruct_typo_correction():
    # 실제 사용되는 LLM 초기 파싱·수정 프롬프트가 명백한 오타를 교정하도록 지시한다.
    from engine.nl_parser import COMPACT_SYSTEM_PROMPT, MODIFY_PROMPT
    assert "재약주" in COMPACT_SYSTEM_PROMPT and "오타" in COMPACT_SYSTEM_PROMPT
    assert "재약주" in MODIFY_PROMPT and "오타" in MODIFY_PROMPT


def test_llm_schema_drift_sector_in_universe_is_repaired():
    # [회귀, 2026-07-12 실측] "2차전지에 투자하는 전략을 만들자" → LLM 폴백이 업종을
    # universe에 넣고 description을 빼먹어 ValidationError → 해석 전체 폐기 → 섹터 없는
    # 전체 시장 전략이 조용히 생성. 드리프트를 버리지 않고 결정적으로 복구해야 한다.
    from engine.nl_parser import ParsedStrategy, _parse_model_json_response
    raw = (
        '{"universe": ["이차전지"], "fundamental_filters": [], "entry_signals": [],'
        ' "exit_signals": [], "rebalancing_period": "none"}'
    )
    parsed = _parse_model_json_response(raw, ParsedStrategy)
    assert parsed.sector == "이차전지"
    assert parsed.universe == ["KOSPI", "KOSDAQ"]  # 업종만 있었으면 섹터 기본=양시장
    assert parsed.description == ""  # 원문은 _apply_prompt_overrides가 채운다


def test_llm_schema_drift_korean_market_and_mixed_universe():
    from engine.nl_parser import ParsedStrategy
    # 한글 시장명은 영문 코드로 정규화한다.
    p = ParsedStrategy(description="x", universe=["코스피"])
    assert p.universe == ["KOSPI"]
    # 시장+업종이 섞이면 시장은 남기고 업종은 sector로 이동한다.
    p2 = ParsedStrategy(description="x", universe=["KOSDAQ", "2차전지"])
    assert p2.universe == ["KOSDAQ"]
    assert p2.sector == "이차전지"
    # sector가 이미 있으면 덮어쓰지 않는다.
    p3 = ParsedStrategy(description="x", universe=["반도체"], sector="이차전지")
    assert p3.sector == "이차전지"
    # 정상 입력은 no-op.
    p4 = ParsedStrategy(description="x", universe=["KOSPI200"])
    assert p4.universe == ["KOSPI200"] and p4.sector is None


# ── 다중 섹터 수정 의미론 (FR-STR-066 ⑦) ────────────────────────────────────────


def test_modify_sector_additive_union():
    # [회귀, 2026-07-13 실측] 반도체 전략에 "로봇 섹터도 추가해줘" — '~도 추가'가 교체로
    # 처리돼 반도체가 사라지던 버그. 추가 의도는 기존 섹터와 합집합(list)이어야 한다.
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_dump()
    prev["sector"] = "반도체"
    for phrasing in ["로봇 섹터도 추가해줘", "로봇도 추가해줘", "로봇 업종 포함해줘"]:
        parsed = _modify_rule_based(phrasing, dict(prev))
        assert parsed is not None, phrasing
        assert parsed.sector == ["반도체", "로봇"], phrasing


def test_modify_sector_replace_without_additive_cue():
    # 추가 표지('도'/추가·포함 동사) 없는 섹터 언급은 기존대로 교체다.
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_dump()
    prev["sector"] = "반도체"
    parsed = _modify_rule_based("기계/장비 업종으로 바꿔줘", dict(prev))
    assert parsed is not None
    assert parsed.sector == "기계/장비"


def test_modify_sector_targeted_removal():
    # 복수 목록에서 특정 업종만 빼면 그 항목만 제거되고, 하나 남으면 정규형 str로 접힌다.
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_dump()
    prev["sector"] = ["반도체", "기계/장비"]
    parsed = _modify_rule_based("반도체 업종은 빼줘", dict(prev))
    assert parsed is not None
    assert parsed.sector == "기계/장비"


def test_modify_sector_removal_not_reinjected():
    # [선행 버그 회귀] "반도체 섹터 빼줘"가 삭제 후 _extract_sector 재추출로 반도체를
    # 되살리던 문제 — 통합 판정이 삭제를 우선해 양 경로 모두 재주입이 없어야 한다.
    from engine.nl_parser import _modify_rule_based
    prev = make_base_strategy().model_dump()
    prev["sector"] = "반도체"
    parsed = _modify_rule_based("반도체 섹터 빼줘", dict(prev))
    assert parsed is not None
    assert parsed.sector is None


def test_modify_sector_removal_of_unlisted_target_is_not_full_clear():
    # 목록에 없는 업종 삭제 요청("반도체 빼줘", prev=기계/장비)은 전체 해제로 오폭하지 않고
    # 결정적 판단을 유보한다(LLM/안내 위임).
    from engine.nl_parser import _sector_change_from_utterance
    changed, value = _sector_change_from_utterance("반도체 업종은 빼줘", "기계/장비")
    assert changed is False and value is None


def test_modify_llm_path_sector_additive_overrides_diff(monkeypatch):
    # LLM diff가 '~도 추가'를 교체(sector="기계/장비")로 오독해도 결정적 판정이 합집합으로
    # 보정한다. 삭제 발화도 동일 경로에서 재주입 없이 유지된다.
    from engine.nl_parser import NLStrategyParser, ParsedStrategyDiff
    monkeypatch.setattr("engine.modify_rag.record_example", lambda *_a, **_k: False)
    parser = NLStrategyParser(backend="mlx")
    prev = make_base_strategy().model_dump()
    prev["sector"] = "반도체"
    prev["description"] = "반도체 저PBR 전략 변동성 어쩌고"  # 룰 파스가 못 풀게

    diff = ParsedStrategyDiff(sector="기계/장비")
    monkeypatch.setattr(parser, "_modify_mlx", lambda *_a, **_k: diff)
    merged = parser.parse_modification("로봇 섹터도 추가해줘 변동성", prev)
    assert merged.sector == ["반도체", "로봇"]

    diff_none = ParsedStrategyDiff()
    monkeypatch.setattr(parser, "_modify_mlx", lambda *_a, **_k: diff_none)
    removed = parser.parse_modification("반도체 섹터 빼줘 변동성", prev)
    assert removed.sector is None


def test_sector_validator_accepts_list_and_collapses():
    # 배열 입력은 항목별 정본화·미지원 드롭·순서보존 dedup 후 정규형으로 접는다
    # (없음=None, 단일=str — 기존 해시·직렬화 호환, 복수=list).
    base = make_base_strategy().model_dump()
    from engine.nl_parser import ParsedStrategy
    s = ParsedStrategy(**{**base, "sector": ["배터리", "로봇", "메타버스", "2차전지"]})
    assert s.sector == ["이차전지", "로봇"]
    assert ParsedStrategy(**{**base, "sector": ["배터리"]}).sector == "이차전지"
    assert ParsedStrategy(**{**base, "sector": ["메타버스"]}).sector is None


def test_canonical_dsl_multi_sector_sorted_single_str():
    # 단일 섹터는 str 그대로(기존 해시 불변), 복수는 정렬 list(순서 무관 동일 해시).
    from engine.strategy_converter import to_canonical_strategy_dsl
    single = make_base_strategy().model_copy(update={"sector": "반도체"})
    assert to_canonical_strategy_dsl(single)["sector"] == "반도체"
    multi_a = make_base_strategy().model_copy(update={"sector": ["반도체", "기계/장비"]})
    multi_b = make_base_strategy().model_copy(update={"sector": ["기계/장비", "반도체"]})
    assert to_canonical_strategy_dsl(multi_a)["sector"] == ["기계/장비", "반도체"]
    assert to_canonical_strategy_dsl(multi_a)["sector"] == to_canonical_strategy_dsl(multi_b)["sector"]


def test_overrides_fill_missing_description_with_user_input():
    from engine.nl_parser import ParsedStrategy, _apply_prompt_overrides
    parsed = ParsedStrategy(description="", universe=["KOSPI"])
    out = _apply_prompt_overrides(parsed, "2차전지에 투자하는 전략을 만들자")
    assert out.description == "2차전지에 투자하는 전략을 만들자"


def test_llm_sector_with_default_universe_gets_both_markets(monkeypatch):
    # LLM이 sector는 냈지만 universe를 스키마 기본(KOSPI200)으로 둔 경우,
    # 시장 언급 없는 섹터 전략 기본=양시장 규칙을 LLM 폴백 경로에서도 강제한다.
    from engine.nl_parser import NLStrategyParser, ParsedStrategy
    p = NLStrategyParser()
    drift = ParsedStrategy(description="", sector="이차전지")
    monkeypatch.setattr(p, "_parse_ollama", lambda text: drift)
    out = p.parse("2차전지에 투자하는 전략을 만들자")
    assert out.sector == "이차전지"
    assert out.universe == ["KOSPI", "KOSDAQ"]
    # 시장을 명시하면 강제하지 않는다.
    drift2 = ParsedStrategy(description="", sector="이차전지", universe=["KOSPI200"])
    monkeypatch.setattr(p, "_parse_ollama", lambda text: drift2)
    out2 = p.parse("코스피200 중에서 2차전지에 투자하는 전략")
    assert out2.universe == ["KOSPI200"]


def test_unresolved_sector_mention_also_gets_both_markets(monkeypatch):
    # [회귀] '재약주 관련 전략을 만들자' — 오타로 섹터가 미해결(None)이라 KOSPI200 기본이
    # 그대로 남아, 되묻기로 섹터를 확정한 뒤에도 사용자가 고르지 않은 KOSPI200에 섹터만
    # 얹히던 사고. 업종을 말했으면(미해결이라도) 시장 미언급 시 양시장으로 확장한다.
    from engine.nl_parser import NLStrategyParser, ParsedStrategy
    p = NLStrategyParser()
    # 섹터 미해결(None) + 스키마 기본 universe.
    drift = ParsedStrategy(description="", universe=["KOSPI200"])
    monkeypatch.setattr(p, "_parse_ollama", lambda text: drift)
    out = p.parse("재약주 관련 전략을 만들자")
    assert out.sector is None                    # 오타라 아직 미해결
    assert out.universe == ["KOSPI", "KOSDAQ"]   # 업종 언급 → 시장 미언급 시 양시장
    # 시장을 명시하면 존중한다(미해결 섹터여도).
    drift2 = ParsedStrategy(description="", universe=["KOSPI200"])
    monkeypatch.setattr(p, "_parse_ollama", lambda text: drift2)
    out2 = p.parse("코스피200 재약주 관련 전략")
    assert out2.universe == ["KOSPI200"]


def test_rule_parse_sector_strategy_sets_sector_and_market_default():
    # 섹터 전략은 시장 언급이 없으면 '그 업종 전체'(양시장)로 해석한다 —
    # KOSPI200 기본값이면 시총 상위 200 ∩ 섹터로 과도하게 좁아진다.
    from engine.nl_parser import _parse_rule_based_strategy
    parsed = _parse_rule_based_strategy(
        "반도체 관련주 중 최근 3개월 수익률이 높은 상위 5종목을 매수, 월간 리밸런싱"
    )
    assert parsed is not None
    assert parsed.sector == "반도체"
    assert parsed.universe == ["KOSPI", "KOSDAQ"]
    assert parsed.ranking_metric == "return"


def test_rule_parse_sector_respects_explicit_market():
    from engine.nl_parser import _parse_rule_based_strategy
    parsed = _parse_rule_based_strategy(
        "코스닥 반도체 관련주 중 최근 3개월 수익률 상위 5종목 매수, 월간 리밸런싱"
    )
    assert parsed is not None
    assert parsed.sector == "반도체"
    assert parsed.universe == ["KOSDAQ"]


def test_supported_sector_no_longer_flagged_unsupported():
    # 섹터가 지원 개념이 된 뒤에도, 지원 목록 밖 업종('메타버스')은 여전히 안내가 남아야 한다.
    from engine.nl_parser import build_unsupported_concept_notice
    assert build_unsupported_concept_notice("반도체 관련주 매수 전략") is None
    notice = build_unsupported_concept_notice("메타버스 관련주 매수 전략")
    assert notice is not None and "섹터/업종" in notice


def test_sector_flows_to_backtest_request_and_canonical_dsl():
    # [스키마 누수 방어] sector가 요청·canonical DSL·백엔드 스키마를 모두 통과해야 한다
    # (ranking_metric이 extra=ignore로 버려져 0거래가 됐던 사고와 동일 함정).
    from engine.nl_parser import _parse_rule_based_strategy
    from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
    from schemas import BacktestRequest

    parsed = _parse_rule_based_strategy(
        "반도체 관련주 중 최근 3개월 수익률 상위 5종목 매수, 월간 리밸런싱"
    )
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["sector"] == "반도체"
    assert to_canonical_strategy_dsl(parsed)["sector"] == "반도체"
    roundtrip = BacktestRequest(**{**req, "symbols": []}).model_dump()
    assert roundtrip["sector"] == "반도체"


def test_canonical_dsl_hash_unchanged_without_sector():
    # 섹터 없는 기존 전략의 canonical DSL에는 sector 키가 없어 해시가 변하지 않는다.
    from engine.strategy_converter import to_canonical_strategy_dsl
    assert "sector" not in to_canonical_strategy_dsl(make_base_strategy())


def test_sector_validator_normalizes_llm_free_text():
    # LLM이 자유 문자열('배터리')을 내도 정본 섹터명으로 정규화되고, 미지원은 None이 된다.
    base = make_base_strategy()
    assert base.model_copy(update={}).sector is None
    from engine.nl_parser import ParsedStrategy
    s = ParsedStrategy(**{**base.model_dump(), "sector": "배터리"})
    assert s.sector == "이차전지"
    s2 = ParsedStrategy(**{**base.model_dump(), "sector": "메타버스"})
    assert s2.sector is None
