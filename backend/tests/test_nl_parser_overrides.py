from engine.nl_parser import ParsedStrategy, TechnicalSignal, _apply_prompt_overrides


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
