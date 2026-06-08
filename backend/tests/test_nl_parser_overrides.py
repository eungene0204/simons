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
    _build_fallback_strategy,
    detect_missing_entry_clarification,
    _extract_technical_signals,
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
    assert parser.ollama_model == "qwen3.5:4b"
    assert parser.ollama_model_32b == "qwen3.5:4b"


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
    assert parsed.universe == ["KOSPI"]
    assert [(f.metric, f.operator, f.value) for f in parsed.fundamental_filters] == [
        ("pbr", "<=", 1.0),
    ]
    assert parsed.max_positions == 8
    assert parsed.hold_period_days == 126
    assert parsed.stop_loss_pct == 12.0


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
