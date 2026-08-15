"""전략 빌더 단일 종목 모드 (FR-STR-068b).

single_symbol이 설정된 빌더는 종목 선별용 질문(유니버스·보유 수·리밸런싱)을 건너뛰고,
횡단면 전략 유형(모멘텀 랭킹·가치 스크리닝)을 이유 설명과 함께 차단하며, 완성 시
단일 종목 엔진 계약(target_symbols·max_positions=1·리밸런싱 없음)으로 DSL을 만든다.
"""
import intent.strategy_builder as sb
from engine.strategy_converter import to_backtest_request


def _single_state(**kw) -> sb.BuilderState:
    return sb.BuilderState(single_symbol="005930", single_label="삼성전자 (005930)", **kw)


def test_required_missing_skips_cross_sectional_fields():
    # 유니버스는 묻지 않고 곧장 전략 유형으로.
    assert sb.required_missing(_single_state()) == "strategy_type"
    # 파라미터가 다 찼으면 보유 수·리밸런싱을 건너뛰고 청산 조건으로 직행.
    state = _single_state(strategy_type="golden_cross", ma_kind="sma",
                          ma_short=5, ma_long=20, filters_asked=True)
    assert sb.required_missing(state) == "risk"


def test_first_question_is_entry_method_not_stock_picking(monkeypatch):
    # 프로파일 유무와 무관하게 질문이 나와야 한다 — 조회 실패를 강제해 폴백을 검증.
    import engine.stock_profile as sp
    monkeypatch.setattr(sp, "get_stock_profile", lambda symbol: None)
    result = sb.step(_single_state(), "")
    assert "언제" in result.reply or "진입 방식" in result.reply or "사고팔지" in result.reply
    # 선택지는 매수 조건 정본에서 횡단면(여러 종목 비교) 항목만 뺀 목록이다(2026-08-16).
    from engine import strategy_slots

    assert result.suggestions == strategy_slots.entry_chips(cross_sectional=False)
    assert not any("상위" in chip for chip in result.suggestions)  # 랭킹은 단일 종목에 무의미
    assert "골든크로스(5일/20일) 발생 시 매수" in result.suggestions


def test_first_question_uses_profile_signal_counts(monkeypatch):
    import engine.stock_profile as sp
    from tests.test_stock_profile import _profile_with

    monkeypatch.setattr(sp, "get_stock_profile", lambda symbol: _profile_with())
    result = sb.step(_single_state(), "")
    assert "50회" in result.reply  # golden_cross_5_20_count=50 이 근거로 노출된다


def test_no_seed_echo_of_system_defaults(monkeypatch):
    """프론트가 자동 세팅한 보유 1종목·리밸런싱 없음을 사용자 조건처럼 복창하지 않는다
    ("좋아요. 1종목, 안 함 리밸런싱(으)로 이해했어요" 버그)."""
    import engine.stock_profile as sp
    monkeypatch.setattr(sp, "get_stock_profile", lambda symbol: None)
    state = _single_state(universe="KOSPI_KOSDAQ", holding_count=1, rebalance_cycle="none")
    result = sb.step(state, "")
    assert "이해했어요" not in result.reply
    assert "리밸런싱" not in result.reply


def test_no_duplicate_free_input_chip(monkeypatch):
    """'직접 입력' 칩은 프론트가 붙이므로 백엔드는 '직접 설명하기'를 노출하지 않는다."""
    import engine.stock_profile as sp
    monkeypatch.setattr(sp, "get_stock_profile", lambda symbol: None)
    result = sb.step(_single_state(), "")
    assert "직접 설명하기" not in result.suggestions


def test_free_description_becomes_custom_entry():
    """유형 미매칭 자유 서술('직접 입력' 경로)은 custom 진입 규칙으로 저장돼 막다른 길이 없다."""
    result = sb.step(_single_state(), "3일 연속 하락하면 매수해줘")
    assert result.state.strategy_type == "custom"
    assert result.state.entry_rule == "3일 연속 하락하면 매수해줘"
    # 맨숫자·짧은 답은 서술로 오인하지 않는다(같은 질문 유지).
    again = sb.step(_single_state(), "14")
    assert again.state.strategy_type is None


def test_momentum_and_value_blocked_with_explanation():
    state = _single_state()
    r_momentum = sb.step(state, "모멘텀")
    assert r_momentum.state.strategy_type is None
    assert "단일 종목에는 적용할 수 없어요" in r_momentum.reply
    r_value = sb.step(state, "저평가 가치주")
    assert r_value.state.strategy_type is None
    assert "단일 종목에는 적용할 수 없어요" in r_value.reply


def test_confirmed_dsl_uses_single_asset_engine_contract():
    state = _single_state(strategy_type="golden_cross", ma_kind="sma",
                          ma_short=5, ma_long=20, filters_asked=True)
    result = sb.step(state, "10% 손절")
    assert result.status == "confirmed"
    parsed = sb.build_parsed_strategy(result.state)
    assert parsed.target_symbols == ["005930"]
    assert parsed.max_positions == 1
    assert parsed.rebalancing_period == "none"
    assert parsed.stop_loss_pct == 10.0

    req = to_backtest_request(parsed)
    assert req["backtest_mode"] == "single_asset"
    assert req["symbols"] == ["005930"]
    assert req["universe_id"] is None
    assert req["risk"]["max_positions"] == 1
    assert req["risk"]["ranking_enabled"] is False


def test_synthesized_prompt_describes_single_asset():
    state = _single_state(strategy_type="golden_cross", ma_kind="sma",
                          ma_short=5, ma_long=20, filters_asked=True,
                          stop_loss_pct=10.0, risk_done=True)
    prompt = sb.synthesize_prompt(state)
    assert prompt.startswith("삼성전자 (005930) 단일 종목에 적용하는 전략")
    # 종목 선별 서술("종목 중 ... 최대 N종목")이 남지 않는다.
    assert "종목 중" not in prompt


def test_universe_builder_unchanged():
    """단일 종목 모드가 아니면 기존 흐름 그대로(회귀 가드)."""
    assert sb.required_missing(sb.BuilderState()) == "universe"
    state = sb.BuilderState(universe="KOSPI", strategy_type="golden_cross",
                            ma_kind="sma", ma_short=5, ma_long=20, filters_asked=True)
    assert sb.required_missing(state) == "holding_count"
