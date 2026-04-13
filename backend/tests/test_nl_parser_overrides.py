import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import (
    NLStrategyParser,
    ParsedStrategy,
    TechnicalSignal,
    _apply_prompt_overrides,
    _extract_technical_signals,
    _merge_signals,
    _validate_signals,
)


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


def test_nl_strategy_parser_defaults_point_to_qwen35_9b():
    parser = NLStrategyParser()

    assert parser.model_7b == "mlx-community/Qwen3.5-9B-OptiQ-4bit"
    assert parser.model_32b == "mlx-community/Qwen3.5-9B-OptiQ-4bit"
    assert parser.ollama_model_7b == "qwen3.5:9b"
    assert parser.ollama_model_32b == "qwen3.5:9b"


def test_nl_strategy_parser_model_log_label_uses_actual_model_name():
    parser = NLStrategyParser()

    assert parser._model_log_label(parser.model_7b) == "Qwen3.5-9B"
    assert parser._model_log_label("mlx-community/Qwen2.5-7B-Instruct-4bit") == "Qwen2.5-7B"


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
