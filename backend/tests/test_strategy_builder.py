"""Strategy Builder Mode 상태 머신 테스트.

[규제 안전] 열린 종목 추천 전환 직후 빌더 대화가 짧은 답변을 전략 필드로 누적하고,
완성 시 요약·확정·합성까지 거절 없이 이어지는지 검증한다(명세 핵심 케이스 1~4 포함).
"""

from __future__ import annotations

import pytest

from intent import strategy_builder as sb
from intent.scope import OFFTOPIC_REFUSAL


def _step(state: sb.BuilderState, text: str) -> sb.StepResult:
    return sb.step(state, text)


# ─── 필드 파서 ────────────────────────────────────────────────────────────────

def test_parse_universe_variants():
    assert sb._parse_universe("일단 코스피") == "KOSPI"
    assert sb._parse_universe("코스닥으로") == "KOSDAQ"
    assert sb._parse_universe("둘 다") == "KOSPI_KOSDAQ"
    assert sb._parse_universe("전체 시장") == "KOSPI_KOSDAQ"
    assert sb._parse_universe("코스피랑 코스닥 모두") == "KOSPI_KOSDAQ"


def test_parse_universe_single_market_with_jeonche_is_that_market():
    # [회귀] "코스피 전체"는 코스피 전 종목이지 양시장이 아니다. 예전엔 '전체'가 양시장
    # 패턴에 먼저 잡혀 KOSPI_KOSDAQ로 오해석됐다(메인 NL 파서는 KOSPI로 해석 — 불일치).
    assert sb._parse_universe("코스피 전체") == "KOSPI"
    assert sb._parse_universe("코스닥 전체로 해줘") == "KOSDAQ"
    # 시장명 없는 '전체/모두'는 여전히 양시장.
    assert sb._parse_universe("전체") == "KOSPI_KOSDAQ"
    assert sb._parse_universe("모두") == "KOSPI_KOSDAQ"
    assert sb._parse_universe("코스피·코스닥 전체") == "KOSPI_KOSDAQ"


def test_parse_universe_kospi200_not_swallowed_by_kospi():
    # [회귀] '코스피200'은 '코스피'를 부분 문자열로 포함해 KOSPI로 조용히 새던 버그.
    # 엔진이 지원하는 KOSPI200 유니버스로 정확히 잡혀야 한다.
    assert sb._parse_universe("코스피200") == "KOSPI200"
    assert sb._parse_universe("코스피 200으로 해줘") == "KOSPI200"
    assert sb._parse_universe("대형주") == "KOSPI200"


def test_parse_rebalance_daily_ilgan():
    # [회귀] 주간/월간/연간은 '-간' 형을 인식하는데 daily만 '일간'을 못 잡아 리밸런싱 단계가
    # 완료되지 않고 대화 흐름이 끊기던 버그.
    assert sb._parse_rebalance("일간") == "daily"
    assert sb._parse_rebalance("매일") == "daily"
    assert sb._parse_rebalance("하루마다") == "daily"


def test_parse_strategy_type_variants():
    assert sb._parse_strategy_type("모멘텀") == "momentum"
    assert sb._parse_strategy_type("최근 오른 종목") == "momentum"
    assert sb._parse_strategy_type("골든크로스") == "golden_cross"
    assert sb._parse_strategy_type("이동평균 교차") == "golden_cross"
    assert sb._parse_strategy_type("MACD") == "macd"
    assert sb._parse_strategy_type("전고점 돌파") == "breakout"
    assert sb._parse_strategy_type("거래량 급증") == "volume_spike"
    assert sb._parse_strategy_type("과매도 반등") == "mean_reversion"
    assert sb._parse_strategy_type("저평가 가치주") == "value"
    assert sb._parse_strategy_type("직접 설명할게") == "custom"


def test_parse_lookback_months_and_days():
    s = sb.BuilderState(universe="KOSPI", strategy_type="momentum")
    patch = sb.parse_input("3개월", s, expecting="lookback_days")
    assert patch["lookback_days"] == 63
    assert patch["lookback_label"] == "3개월"

    s2 = sb.BuilderState(universe="KOSPI", strategy_type="breakout")
    patch2 = sb.parse_input("60일", s2, expecting="lookback_days")
    assert patch2["lookback_days"] == 60


def test_bare_number_resolves_by_expecting():
    s = sb.BuilderState(universe="KOSPI", strategy_type="momentum")
    # 기준 기간을 묻는 중 "3" → 3개월
    assert sb.parse_input("3", s, expecting="lookback_days")["lookback_days"] == 63
    # 보유 수를 묻는 중 "10" → 10개
    assert sb.parse_input("10", s, expecting="holding_count")["holding_count"] == 10


def test_parse_holding_and_rebalance():
    s = sb.BuilderState()
    assert sb.parse_input("10개", s, expecting="holding_count")["holding_count"] == 10
    assert sb.parse_input("20종목", s, expecting="holding_count")["holding_count"] == 20
    assert sb._parse_rebalance("매주") == "weekly"
    assert sb._parse_rebalance("월간 리밸런싱") == "monthly"
    assert sb._parse_rebalance("분기마다") == "quarterly"
    assert sb._parse_rebalance("안 함") == "none"
    assert sb._parse_rebalance("리밸런싱 안 함") == "none"
    assert sb._parse_rebalance("그대로 보유") == "none"


def test_rebalance_none_option_offered_and_completes():
    """리밸런싱 '안 함'은 정상 옵션으로 제공되고 선택 시 전략을 완성시킨다."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum",
                            lookback_days=63, holding_count=10)
    # 다음 질문(리밸런싱)에 '안 함' 칩이 포함된다.
    _, suggestions = sb.next_question(state)
    assert "안 함" in suggestions
    # '안 함' 선택 → rebalance_cycle="none", 다음은 청산 조건 질문.
    res = _step(state, "안 함")
    assert res.state.rebalance_cycle == "none"
    assert res.status == "collecting"
    assert "청산 조건" in res.reply
    # 청산 조건(필수)을 채우면 confirmed, 합성 프롬프트엔 리밸런싱 문구가 없다.
    done = _step(res.state, "10% 손절")
    assert done.status == "confirmed"
    assert "리밸런싱" not in done.prompt


# ─── 명세 핵심 케이스 1~4 ─────────────────────────────────────────────────────────

def test_case1_kospi_after_entry_no_refusal_and_next_question():
    """Case 1: 빌더 진입 후 '일단 코스피' → universe=KOSPI, 거절 없음, 다음 질문(전략 유형)."""
    res = _step(sb.BuilderState(), "일단 코스피")
    assert res.state.universe == "KOSPI"
    assert res.status == "collecting"
    assert OFFTOPIC_REFUSAL not in res.reply
    assert "현재 질문에는 도움을 드릴 수 없습니다" not in res.reply
    assert "방식" in res.reply  # 전략 유형을 묻는 다음 질문
    assert "모멘텀" in res.suggestions


def test_blank_input_shows_opening_question_without_mutation():
    """빌더 진입 직후 빈 입력 → 상태 변화 없이 첫 질문(시장 선택)을 띄운다.

    후속 입력을 기다리지 않고 빌더의 첫 질문을 능동적으로 보여주는 경로가 의존한다.
    """
    res = _step(sb.BuilderState(), "")
    assert res.status == "collecting"
    assert res.state == sb.BuilderState()  # 아무것도 채우지 않는다
    assert "시장" in res.reply
    assert res.suggestions == ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체"]


def test_blank_input_does_not_complete_partial_risk_state():
    """청산 조건만 남은 상태에서 빈 입력이 risk_done을 켜 전략을 잘못 완성시키지 않는다."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum",
                            lookback_days=63, holding_count=10, rebalance_cycle="weekly")
    res = _step(state, "")
    assert res.status == "collecting"
    assert res.state.risk_done is False
    assert "청산 조건" in res.reply


def test_strategy_type_offers_describe_own_chip_rightmost():
    """전략 유형 질문에 '직접 설명하기' 칩이 가장 오른쪽으로 노출된다."""
    state = sb.BuilderState(universe="KOSPI")
    _, suggestions = sb.next_question(state)
    assert suggestions[-1] == "직접 설명하기"
    assert "모멘텀" in suggestions


def test_describe_own_chip_routes_to_free_text_entry_rule():
    """'직접 설명하기' 선택 → custom 유형 → 칩 없는 진입 조건 질문(프론트가 채팅창 재노출)."""
    state = sb.BuilderState(universe="KOSPI")
    res = _step(state, "직접 설명하기")
    assert res.state.strategy_type == "custom"
    assert res.status == "collecting"
    assert res.suggestions == []  # 칩이 없어 프론트가 채팅창을 다시 보여준다
    assert "매수" in res.reply
    # 이어서 자유 서술 입력은 진입 규칙으로 그대로 저장된다.
    res2 = _step(res.state, "RSI가 30 이하로 떨어지면 매수")
    assert res2.state.entry_rule == "RSI가 30 이하로 떨어지면 매수"


def test_case2_bare_kospi_interpreted_as_universe():
    """Case 2: 시장 선택을 유도한 상태에서 '코스피' → universe로 처리."""
    res = _step(sb.BuilderState(), "코스피")
    assert res.state.universe == "KOSPI"
    assert res.status == "collecting"


def test_case3_three_months_with_momentum():
    """Case 3: strategyType=momentum 상태에서 '3개월' → lookback 처리 후 다음 질문."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum")
    res = _step(state, "3개월")
    assert res.state.lookback_days == 63
    assert res.status == "collecting"
    assert res.state.holding_count is None  # 다음은 보유 수


def test_case4_cancel_resets_to_normal():
    """Case 4: '취소' → 상태 초기화 + exited(일반 모드 복귀)."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum", lookback_days=63)
    res = _step(state, "취소")
    assert res.status == "exited"
    assert res.state == sb.BuilderState()


# ─── 전체 흐름: 진입 → 완성 → 확정 → 합성 ──────────────────────────────────────────

def test_full_momentum_flow_to_confirmation():
    """리밸런싱 다음 청산 조건 단계까지 거친 뒤, 답하면 곧바로 confirmed로 합성된다."""
    state = sb.BuilderState()
    state = _step(state, "코스피").state
    state = _step(state, "모멘텀").state
    state = _step(state, "3개월").state
    state = _step(state, "10개").state
    risk_q = _step(state, "매주")
    assert risk_q.status == "collecting"  # 마지막은 청산 조건 질문
    assert "청산 조건" in risk_q.reply
    confirmed = _step(risk_q.state, "10% 손절")
    assert confirmed.status == "confirmed"
    assert confirmed.prompt
    assert "코스피" in confirmed.prompt
    assert "63일" in confirmed.prompt and "상위 10개" in confirmed.prompt
    assert "매주 리밸런싱" in confirmed.prompt
    assert "10% 손절" in confirmed.prompt


# ─── 시드(빌더 진입 시 원본 메시지 선반영) ──────────────────────────────────────────

def test_seed_state_prefills_recognized_fields():
    """STOCK_PICK 원본 메시지의 인식 가능한 조건을 미리 채운다(빠진 것만 묻기 위함)."""
    state = sb.seed_state(
        "최근 1주일 동안 수익률이 좋았던 종목 10개를 사서 -15%에 손절하고 30%에 익절해줘"
    )
    assert state.strategy_type == "momentum"
    assert state.lookback_days == 5 and state.lookback_label == "1주일"
    assert state.holding_count == 10
    assert state.stop_loss_pct == 15.0
    assert state.take_profit_pct == 30.0
    assert state.risk_done is True
    assert state.universe is None  # 유니버스만 빠짐


def test_seed_state_asks_only_missing_universe_then_rebalance():
    """이미 말한 전략유형·보유수·청산은 다시 묻지 않고 유니버스부터 묻는다."""
    state = sb.seed_state(
        "최근 1주일 동안 수익률이 좋았던 종목 10개를 사서 -15%에 손절하고 30%에 익절해줘"
    )
    first = sb.step(state, "")
    assert first.status == "collecting"
    assert "시장" in first.reply              # 첫 질문은 유니버스
    assert "방식으로 종목" not in first.reply  # 전략유형은 다시 묻지 않음

    after_univ = sb.step(first.state, "코스닥")
    # 직전 답변(유니버스)을 확인해야지, 시드된 보유수를 엉뚱하게 확인하면 안 된다.
    assert "코스닥 시장을 대상으로" in after_univ.reply
    assert "리밸런싱" in after_univ.reply       # 진짜 빠진 다음 질문

    confirmed = sb.step(after_univ.state, "매월")
    assert confirmed.status == "confirmed"
    assert "코스닥" in confirmed.prompt
    assert "상위 10개" in confirmed.prompt
    assert "-15% 손절" in confirmed.prompt and "30% 익절" in confirmed.prompt


def test_is_empty_gates_seeding():
    assert sb.is_empty(sb.BuilderState()) is True
    assert sb.is_empty(sb.BuilderState(universe="KOSPI")) is False


def test_parse_strategy_type_recognizes_profit_phrasing():
    assert sb._parse_strategy_type("수익률이 좋았던 종목") == "momentum"
    assert sb._parse_strategy_type("많이 오른 종목") == "momentum"


def test_parse_lookback_weeks():
    assert sb._parse_lookback("최근 1주일")["lookback_days"] == 5
    assert sb._parse_lookback("2주")["lookback_days"] == 10


def test_restart_keeps_builder_and_clears_state():
    state = sb.BuilderState(universe="KOSPI", strategy_type="momentum", lookback_days=63)
    res = _step(state, "처음부터")
    assert res.status == "reset"
    assert res.state == sb.BuilderState()
    assert "시장" in res.reply  # 첫 질문(유니버스)


def test_exit_other_question_returns_to_normal():
    state = sb.BuilderState(universe="KOSPI")
    res = _step(state, "다른 질문 할게")
    assert res.status == "exited"


def test_failed_parse_reasks_without_refusal():
    """파싱 실패 시 거절하지 않고 같은 질문을 다시 한다."""
    res = _step(sb.BuilderState(), "음 글쎄요")
    assert res.status == "collecting"
    assert res.state.universe is None
    assert "시장" in res.reply
    assert OFFTOPIC_REFUSAL not in res.reply


# ─── 유형별 합성 프롬프트 ──────────────────────────────────────────────────────────

def test_synthesize_breakout_volume_meanrev():
    bo = sb.BuilderState(universe="KOSDAQ", strategy_type="breakout",
                         lookback_days=60, holding_count=10, rebalance_cycle="weekly")
    assert "신고가를 돌파" in sb.synthesize_prompt(bo)
    assert "코스닥" in sb.synthesize_prompt(bo)

    vol = sb.BuilderState(universe="KOSPI", strategy_type="volume_spike",
                          holding_count=5, rebalance_cycle="monthly")
    assert "거래량이 평소보다 급증" in sb.synthesize_prompt(vol)
    assert "매월 리밸런싱" in sb.synthesize_prompt(vol)

    mr = sb.BuilderState(universe="KOSPI", strategy_type="mean_reversion",
                         holding_count=10, rebalance_cycle="weekly")
    assert "RSI가 30 이하" in sb.synthesize_prompt(mr)


def test_synthesize_golden_macd_value():
    gc = sb.BuilderState(universe="KOSPI", strategy_type="golden_cross",
                         holding_count=10, rebalance_cycle="weekly")
    assert "골든크로스" in sb.synthesize_prompt(gc)

    macd = sb.BuilderState(universe="KOSDAQ", strategy_type="macd",
                           holding_count=5, rebalance_cycle="monthly")
    assert "MACD" in sb.synthesize_prompt(macd)
    assert "코스닥" in sb.synthesize_prompt(macd)

    val = sb.BuilderState(universe="KOSPI", strategy_type="value",
                          holding_count=10, rebalance_cycle="quarterly")
    assert "PBR 1 이하" in sb.synthesize_prompt(val)
    assert "ROE 10% 이상" in sb.synthesize_prompt(val)


def test_new_strategy_types_skip_lookback_question():
    # 골든크로스·MACD·가치는 기준기간(lookback) 질문 없이 곧장 보유 종목 수로 넘어간다
    # (모멘텀·돌파만 lookback 필수).
    for stype in ("golden_cross", "macd", "value"):
        state = sb.BuilderState(universe="KOSPI", strategy_type=stype)
        assert sb.required_missing(state) == "holding_count"


@pytest.mark.parametrize("stype", ["golden_cross", "macd", "value"])
def test_new_strategy_types_synthesize_parses_to_buy_criteria(stype):
    # [회귀] 새 전략 유형의 합성 프롬프트는 반드시 매수 기준(진입 신호/재무 필터)으로 파싱돼야 한다.
    # 그렇지 않으면 빈 전략으로 판정돼 다시 빌더로 되돌아가는 무한루프가 생긴다.
    from engine.nl_parser import _extract_fundamental_filters, _extract_technical_signals

    state = sb.BuilderState(universe="KOSPI", strategy_type=stype,
                            holding_count=10, rebalance_cycle="weekly")
    prompt = sb.synthesize_prompt(state)
    buy, _sell = _extract_technical_signals(prompt)
    fund = _extract_fundamental_filters(prompt)
    assert buy or fund, f"{stype} 합성 프롬프트가 매수 기준으로 파싱되지 않음: {prompt}"


def test_custom_flow_captures_entry_rule():
    state = sb.BuilderState(universe="KOSPI")
    state = _step(state, "직접 설명할게").state
    assert state.strategy_type == "custom"
    # 다음 입력은 진입 규칙 서술로 저장된다.
    state = _step(state, "20일선이 60일선을 상향 돌파하면").state
    assert state.entry_rule == "20일선이 60일선을 상향 돌파하면"
    state = _step(state, "10개").state
    state = _step(state, "매주").state  # 청산 조건 질문
    res = _step(state, "10% 손절")
    assert res.status == "confirmed"
    assert "20일선이 60일선을 상향 돌파" in res.prompt


def test_custom_entry_rule_captures_explicit_holding_count():
    """진입 서술에 명시적 종목 수("상위 5개")가 섞여 있으면 보유 수로 함께 잡아 다시 묻지 않는다.

    [회귀] 'custom' 진입 서술 단계가 입력 전체를 entry_rule로만 저장하면서 명시적 "5개"를
    버려, 사용자가 이미 종목 수를 말했는데도 보유 수를 다시 묻던 버그."""
    state = sb.BuilderState(universe="KOSDAQ", strategy_type="custom")
    res = _step(state, "코스닥 시총 상위 5개를 사는 전략")
    assert res.state.entry_rule == "코스닥 시총 상위 5개를 사는 전략"
    assert res.state.holding_count == 5
    # 보유 수가 채워졌으므로 다음 질문은 보유 수가 아니라 리밸런싱이다.
    assert sb.required_missing(res.state) == "rebalance_cycle"
    assert "몇 종목" not in res.reply


def test_custom_entry_rule_does_not_misread_bare_threshold_as_count():
    """진입 서술의 맨숫자(RSI 30)는 보유 수로 오인하지 않는다(명시적 개/종목 접미사만 인정)."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="custom")
    res = _step(state, "RSI가 30 이하로 떨어지면 매수")
    assert res.state.holding_count is None


def test_holding_count_step_offers_free_input_chip_rightmost():
    """보유 수 질문에 '직접 입력' 칩이 가장 오른쪽으로 노출된다(5/10/20 외 종목 수 직접 타이핑)."""
    momentum = sb.BuilderState(universe="KOSPI", strategy_type="momentum", lookback_days=63)
    golden = sb.BuilderState(universe="KOSPI", strategy_type="golden_cross")
    for state in (momentum, golden):
        _, suggestions = sb.next_question(state)
        assert sb.required_missing(state) == "holding_count"
        assert suggestions[-1] == "직접 입력"


def test_holding_count_step_free_text_parses_custom_value():
    """'직접 입력' 후 사용자가 타이핑한 임의 종목 수('7개')가 그대로 파싱된다."""
    state = sb.BuilderState(universe="KOSPI", strategy_type="golden_cross")
    res = _step(state, "7개")
    assert res.state.holding_count == 7


# ─── 청산 조건(손절·익절·트레일링·보유기간) 단계 ─────────────────────────────────────

def _ready_for_risk() -> sb.BuilderState:
    """리밸런싱까지 채워 청산 조건만 남은 상태."""
    return sb.BuilderState(universe="KOSPI", strategy_type="momentum",
                           lookback_days=63, holding_count=10, rebalance_cycle="weekly")


def test_risk_step_offered_after_rebalance():
    """리밸런싱을 채우면 청산 조건 질문이 칩과 함께 제시된다(청산 조건은 필수)."""
    msg, suggestions = sb.next_question(_ready_for_risk())
    assert "청산 조건" in msg
    assert "10% 손절" in suggestions
    # 청산 조건은 필수이므로 '청산 조건 없음' 칩은 제공하지 않는다.
    assert "청산 조건 없음" not in suggestions


def test_risk_step_offers_free_input_chip_rightmost():
    """청산 조건 질문에 '직접 입력' 칩이 가장 오른쪽으로 노출된다(프론트가 채팅창 토글)."""
    _, suggestions = sb.next_question(_ready_for_risk())
    assert suggestions[-1] == "직접 입력"


def test_risk_step_free_text_after_direct_input_parses_custom_value():
    """'직접 입력' 후 사용자가 타이핑한 커스텀 청산 값('15% 손절')이 그대로 파싱된다."""
    r = _step(_ready_for_risk(), "15% 손절")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 15.0
    assert "15% 손절" in r.prompt


def test_risk_step_parses_stop_loss_with_korean_particle():
    """'15%에 손절 30% 익절'처럼 퍼센트와 키워드 사이에 조사(에)가 끼어도 손절을 인식한다."""
    r = _step(_ready_for_risk(), "15%에 손절 30% 익절")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 15.0
    assert r.state.take_profit_pct == 30.0
    assert "15% 손절" in r.prompt and "30% 익절" in r.prompt


def test_risk_step_keyword_first_order_no_misattribution():
    """[회귀] '손절 10% 익절 20%'처럼 키워드가 값보다 먼저 와도 정확히 귀속돼야 한다.
    예전엔 익절 정규식이 앞의 '10%'(손절 값)를 훔쳐가 손절=None·익절=10으로 조용히 틀리던 버그."""
    r = _step(_ready_for_risk(), "손절 10% 익절 20%")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 10.0
    assert r.state.take_profit_pct == 20.0
    assert "10% 손절" in r.prompt and "20% 익절" in r.prompt


def test_risk_step_negated_stop_loss_not_extracted():
    """'손절 없이 익절 20%'는 손절을 뽑지 않고 익절만 20%로 잡아야 한다(부정어 가드)."""
    r = _step(_ready_for_risk(), "손절 없이 익절 20%")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct is None
    assert r.state.take_profit_pct == 20.0


@pytest.mark.parametrize(
    "question, term",
    [
        ("손절이 뭐야?", "손절"),
        ("트레일링 스탑이 무슨 뜻이에요?", "트레일링"),
        ("리밸런싱이 뭔가요?", "리밸런싱"),
        ("모멘텀이 무엇인가요", "모멘텀"),
    ],
)
def test_glossary_question_mid_builder_answers_and_reasks(question, term):
    """[회귀] 빌더 진행 중 용어 질문은 필드 답변으로 오인돼 같은 질문만 반복되던 막다른 길 —
    짧은 정의를 답하고 현재 질문을 이어가며 상태는 바뀌지 않는다."""
    state = _ready_for_risk()
    r = _step(state, question)
    assert r.status == "collecting"
    assert r.state == state  # 상태 불변
    assert term in r.reply.split("\n\n")[0]  # 앞부분이 정의문
    assert "청산 조건" in r.reply  # 뒤에 현재 질문이 이어짐
    assert "10% 손절" in r.suggestions


def test_glossary_does_not_intercept_normal_answers():
    """정의 표지 없는 일반 답변("10% 손절", "모멘텀")은 용어집이 가로채지 않는다."""
    r = _step(_ready_for_risk(), "10% 손절")
    assert r.status == "confirmed"
    st = sb.BuilderState(universe="KOSPI")
    r2 = _step(st, "모멘텀")
    assert r2.state.strategy_type == "momentum"


@pytest.mark.parametrize("answer", ["없음", "청산 조건은 따로 없이 갈래", "필요 없어"])
def test_risk_step_refusal_explains_why_required(answer):
    """[회귀] 청산 조건 거부("없음")에 같은 질문을 그대로 무한 반복하던 침묵 루프 —
    청산 조건이 필수인 이유를 설명하며 되묻는다(필수 설계는 유지, risk_done은 켜지 않음)."""
    r = _step(_ready_for_risk(), answer)
    assert r.status == "collecting"
    assert r.state.risk_done is False
    assert r.reply == sb.RISK_REQUIRED_REPLY
    assert "10% 손절" in r.suggestions


def test_risk_step_llm_recovers_value_regex_missed():
    """정규식이 키워드(손절)는 봤지만 값을 못 뽑으면 LLM 보강 파서로 값을 채운다."""
    calls = []

    def fake_extractor(text: str) -> dict:
        calls.append(text)
        return {"stop_loss_pct": 20.0}

    # '이십프로 손절'은 정규식이 수치를 못 뽑지만 키워드는 있어 LLM 보강이 트리거된다.
    r = sb.step(_ready_for_risk(), "이십프로 손절", fake_extractor)
    assert calls == ["이십프로 손절"]
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 20.0
    assert "20% 손절" in r.prompt


def test_risk_step_regex_match_skips_llm():
    """정규식이 깨끗이 잡으면 LLM 보강 파서를 호출하지 않는다(비용/지연 절감)."""
    calls = []

    def fake_extractor(text: str) -> dict:
        calls.append(text)
        return {}

    r = sb.step(_ready_for_risk(), "10% 손절", fake_extractor)
    assert calls == []  # LLM 미호출
    assert r.state.stop_loss_pct == 10.0


def test_risk_step_regex_takes_priority_over_llm():
    """정규식이 잡은 필드는 LLM 결과로 덮어쓰지 않는다(결정론 우선)."""
    # 손절은 정규식이 잡고(15), 익절은 '삼십프로'라 정규식이 놓쳐 LLM이 채운다(30).
    r = sb.step(
        _ready_for_risk(),
        "15% 손절에 삼십프로 익절",
        lambda _t: {"stop_loss_pct": 99.0, "take_profit_pct": 30.0},
    )
    assert r.state.stop_loss_pct == 15.0  # 정규식 값 유지(LLM 99 무시)
    assert r.state.take_profit_pct == 30.0  # 정규식이 놓친 값만 LLM 보강


def test_risk_step_llm_failure_falls_back_to_regex():
    """LLM 보강이 예외를 던져도 정규식 결과로 안전하게 폴백한다."""
    def boom(_t: str) -> dict:
        raise RuntimeError("LLM down")

    r = sb.step(_ready_for_risk(), "15%에 손절", boom)
    assert r.state.stop_loss_pct == 15.0  # 정규식이 이미 잡음


def test_risk_step_parses_stop_take_trailing_hold():
    state = _ready_for_risk()

    r = _step(state, "10% 손절·20% 익절")
    assert r.status == "confirmed"
    assert r.state.stop_loss_pct == 10.0 and r.state.take_profit_pct == 20.0
    assert "10% 손절" in r.prompt and "20% 익절" in r.prompt

    r2 = _step(state, "최고가 대비 10% 하락 시 청산")
    assert r2.state.trailing_stop_pct == 10.0
    assert "최고가 대비 10% 하락 시 청산" in r2.prompt

    r3 = _step(state, "트레일링 8%")
    assert r3.state.trailing_stop_pct == 8.0

    r4 = _step(state, "20일 보유 후 청산")
    assert r4.state.hold_period_days == 20
    assert "20거래일 보유" in r4.prompt

    r5 = _step(state, "3개월 보유")
    assert r5.state.hold_period_days == 63


def test_risk_step_requires_a_condition_and_reasks_otherwise():
    """청산 조건은 필수 — 인식 가능한 조건이 없으면 완료하지 않고 같은 질문을 다시 한다."""
    r = _step(_ready_for_risk(), "청산 조건 없음")
    assert r.status == "collecting"
    assert r.state.risk_done is False
    assert "청산 조건" in r.reply
    # 그 뒤 유효한 조건을 주면 완료된다.
    done = _step(r.state, "10% 손절")
    assert done.status == "confirmed"
    assert done.state.stop_loss_pct == 10.0


def test_risk_step_cancel_still_exits():
    """청산 조건 단계에서도 '취소'는 빌더를 종료한다."""
    r = _step(_ready_for_risk(), "취소")
    assert r.status == "exited"
