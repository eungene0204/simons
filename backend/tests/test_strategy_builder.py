"""Strategy Builder Mode 상태 머신 테스트.

[규제 안전] 열린 종목 추천 전환 직후 빌더 대화가 짧은 답변을 전략 필드로 누적하고,
완성 시 요약·확정·합성까지 거절 없이 이어지는지 검증한다(명세 핵심 케이스 1~4 포함).
"""

from __future__ import annotations

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


def test_parse_strategy_type_variants():
    assert sb._parse_strategy_type("모멘텀") == "momentum"
    assert sb._parse_strategy_type("최근 오른 종목") == "momentum"
    assert sb._parse_strategy_type("전고점 돌파") == "breakout"
    assert sb._parse_strategy_type("거래량 급증") == "volume_spike"
    assert sb._parse_strategy_type("과매도 반등") == "mean_reversion"
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
    assert res.suggestions == ["코스피", "코스닥", "코스피·코스닥 전체"]


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
