import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import (
    NLStrategyParser,
    ParsedStrategy,
    ParsedStrategyDiff,
    TechnicalSignal,
    _apply_prompt_overrides,
    _build_fallback_strategy,
    _extract_technical_signals,
    _merge_signals,
    _parse_rule_based_strategy,
    _parse_model_json_response,
    _validate_signals,
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
