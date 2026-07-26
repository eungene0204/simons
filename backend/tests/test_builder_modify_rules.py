"""전략 빌더 조건 수정 규칙(FR-SA-002e) — 진행 중 삭제(REMOVE)·선행 설정(SET-ahead)·
값 없는 변경(MODIFY 되묻기) 테스트.

빌더는 선형 설문이 아니라 편집 과정이다: 어느 단계에서든 이미 결정된 조건을
삭제("손절 빼줘")·추가("손절 10% 걸어줘")·변경("시장 바꿔줘")할 수 있어야 한다.
"""

from __future__ import annotations

from intent import strategy_builder as sb


def _mid_state(**overrides) -> sb.BuilderState:
    """골든크로스 파라미터까지 채워 보유 종목 수 질문 단계에 있는 상태."""
    base = dict(
        universe="KOSPI", strategy_type="golden_cross",
        ma_kind="sma", ma_short=5, ma_long=20, filters_asked=True,
    )
    base.update(overrides)
    return sb.BuilderState(**base)


# ─── REMOVE: 채워진 조건 삭제 ────────────────────────────────────────────────────

def test_remove_stop_loss_keeps_take_profit():
    state = _mid_state(stop_loss_pct=10.0, take_profit_pct=20.0, risk_done=True)
    res = sb.step(state, "손절 빼줘")
    assert res.status == "collecting"
    assert res.state.stop_loss_pct is None
    assert res.state.take_profit_pct == 20.0
    assert res.state.risk_done is True  # 익절이 남아 청산 단계는 유지
    assert "손절 10%" in res.reply and "제거" in res.reply
    assert "종목" in res.reply  # 기존 진행 위치(보유 종목 수 질문)로 복귀


def test_remove_last_risk_condition_reopens_risk_step():
    state = _mid_state(holding_count=5, stop_loss_pct=10.0, risk_done=True)
    res = sb.step(state, "손절 빼줘")
    assert res.state.stop_loss_pct is None
    assert res.state.risk_done is False  # 청산은 필수 — 다시 묻도록 연다
    assert "제거" in res.reply


def test_remove_specific_filter_keeps_others():
    state = _mid_state(trend_filter_ma=200, liquidity_min=100.0)
    res = sb.step(state, "거래대금 필터 빼줘")
    assert res.state.liquidity_min is None
    assert res.state.trend_filter_ma == 200
    assert "거래대금 100억 필터" in res.reply and "제거" in res.reply


def test_remove_all_filters_generic_word():
    state = _mid_state(trend_filter_ma=200, liquidity_min=100.0)
    res = sb.step(state, "필터 다 빼줘")
    assert res.state.trend_filter_ma is None
    assert res.state.liquidity_min is None
    assert res.state.filters_asked is True  # 이미 물은 단계 — 재질문하지 않는다


def test_remove_sector_restriction():
    state = _mid_state(sector="반도체")
    res = sb.step(state, "업종 제한 빼줘")
    assert res.state.sector is None
    assert "업종 제한" in res.reply and "제거" in res.reply


def test_remove_holding_count_reasks_required_field():
    state = _mid_state(holding_count=10, rebalance_cycle="monthly")
    res = sb.step(state, "종목 수 빼줘")
    assert res.state.holding_count is None
    assert "종목" in res.reply  # 필수 항목 — 해당 질문으로 되돌아간다


def test_remove_rebalance_becomes_none():
    state = _mid_state(holding_count=5, rebalance_cycle="monthly")
    res = sb.step(state, "리밸런싱 빼줘")
    assert res.state.rebalance_cycle == "none"
    assert "리밸런싱" in res.reply


def test_stop_loss_cancel_word_is_removal_not_builder_exit():
    # "손절 취소해줘"의 '취소'는 빌더 취소가 아니라 그 조건의 삭제다.
    state = _mid_state(stop_loss_pct=10.0, take_profit_pct=20.0, risk_done=True)
    res = sb.step(state, "손절 취소해줘")
    assert res.status == "collecting"
    assert res.state.stop_loss_pct is None
    # 대상 없는 맨 '취소'는 여전히 빌더 취소다.
    assert sb.step(_mid_state(), "취소").status == "exited"


# ─── SET-ahead: 다른 단계에서 미리 말한 조건 캡처 ─────────────────────────────────

def test_risk_mentioned_ahead_is_captured_and_not_reasked():
    state = _mid_state()  # 보유 종목 수 질문 단계
    res = sb.step(state, "손절 10% 걸어줘")
    assert res.state.stop_loss_pct == 10.0
    assert res.state.risk_done is True
    assert "10% 손절" in res.reply  # 캡처 확인 문장
    assert "종목" in res.reply       # 진행 위치 유지
    # 남은 필수 필드를 채우면 청산 질문 없이 곧바로 확정된다.
    res2 = sb.step(res.state, "5개")
    res3 = sb.step(res2.state, "매월")
    assert res3.status == "confirmed"


def test_combined_answer_fills_current_field_and_risk():
    state = _mid_state()
    res = sb.step(state, "5종목으로 하고 손절 8% 익절 20%")
    assert res.state.holding_count == 5
    assert res.state.stop_loss_pct == 8.0
    assert res.state.take_profit_pct == 20.0
    assert res.state.risk_done is True


def test_filter_modified_mid_flow_with_explicit_word():
    state = _mid_state(liquidity_min=100.0)
    res = sb.step(state, "거래대금 필터 300억으로 바꿔줘")
    assert res.state.liquidity_min == 300.0
    assert "종목" in res.reply  # 진행 위치 유지


def test_remove_and_set_in_one_message():
    state = _mid_state(stop_loss_pct=10.0, risk_done=True)
    res = sb.step(state, "손절 빼고 익절 20%로 해줘")
    assert res.state.stop_loss_pct is None
    assert res.state.take_profit_pct == 20.0
    assert res.state.risk_done is True


# ─── 값 없는 변경(MODIFY): 필드를 비워 그 질문으로 자연 복귀 ──────────────────────

def test_valueless_risk_change_keeps_value_and_reopens_step():
    state = _mid_state(holding_count=5, stop_loss_pct=10.0, risk_done=True)
    res = sb.step(state, "손절 바꿔줘")
    assert res.state.stop_loss_pct == 10.0  # 값은 유지 — 새 값이 덮어쓴다
    assert res.state.risk_done is False
    assert "청산" in res.reply
    res2 = sb.step(res.state, "매월")            # 리밸런싱 답변
    res3 = sb.step(res2.state, "손절 15%")       # 다시 열린 청산 단계
    assert res3.status == "confirmed"
    assert res3.state.stop_loss_pct == 15.0


def test_valueless_universe_change_reasks_market():
    state = _mid_state(holding_count=5)
    res = sb.step(state, "시장 바꿔줘")
    assert res.state.universe is None
    assert "시장" in res.reply
    res2 = sb.step(res.state, "코스닥")
    assert res2.state.universe == "KOSDAQ"
    assert res2.state.strategy_type == "golden_cross"  # 나머지 조건 유지


def test_valueless_type_change_resets_type_params():
    state = _mid_state(holding_count=5)
    res = sb.step(state, "전략 바꿀래")
    assert res.state.strategy_type is None
    assert res.state.ma_short is None and res.state.ma_long is None
    assert "방식" in res.reply  # 전략 유형 질문으로 복귀


# ─── 호환성 검토 ────────────────────────────────────────────────────────────────

def test_etf_universe_change_blocked_when_value_strategy_set():
    state = sb.BuilderState(
        universe="KOSPI", strategy_type="value", value_pbr=1.0, value_roe=10.0,
    )
    res = sb.step(state, "ETF로 바꿔줘")
    assert res.state.universe == "KOSPI"  # 적용하지 않고
    assert "ETF" in res.reply and "가치" in res.reply  # 이유를 설명한다


def test_sector_change_cue_overwrites_existing_sector():
    patch = sb.parse_input("업종을 반도체로 바꿔줘", _mid_state(sector="로봇"), "holding_count")
    assert patch.get("sector") is not None
    assert patch["sector"] != "로봇"
