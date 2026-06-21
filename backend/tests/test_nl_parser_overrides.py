import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import (
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
    _merge_signals,
    _parse_rule_based_strategy,
    _parse_model_json_response,
    _validate_signals,
    _STOP_LOSS_CUE,
    _STOP_LOSS_BLOCK,
    _TAKE_PROFIT_CUE,
    _TAKE_PROFIT_BLOCK,
    _TRAILING_CUE,
    _TRAILING_BLOCK,
)

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


def test_extract_rsi_sell_with_particle():
    """'RSI가 70 이상이면 매도' — 조사가 끼어도 RSI 매도 추출"""
    _, exit_ = _extract_technical_signals("RSI가 70 이상이면 매도")
    rsi_sell = [s for s in exit_ if s.indicator == "rsi" and s.signal_type == "sell"]
    assert len(rsi_sell) == 1
    assert rsi_sell[0].value == 70.0


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


def test_parse_modification_keeps_previous_universe_when_prompt_does_not_change_it(monkeypatch):
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

    parsed = parser.parse_modification("트레일링 15% 추가해줘", previous)

    assert parsed.universe == ["KOSPI"]
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
