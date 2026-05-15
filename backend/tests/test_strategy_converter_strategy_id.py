import os
import sys
from unittest.mock import patch

sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine.nl_parser import FundamentalFilter, ParsedStrategy, TechnicalSignal
from engine.nl_parser import _apply_prompt_overrides
from engine.strategy_converter import (
    canonical_strategy_json,
    compute_strategy_id,
    to_backtest_request,
    to_canonical_strategy_dsl,
)


def make_strategy(**overrides) -> ParsedStrategy:
    base = {
        "description": "기본 전략 설명",
        "universe": ["KOSPI200"],
        "fundamental_filters": [],
        "entry_signals": [],
        "exit_signals": [],
        "max_positions": 10,
        "hold_period_days": None,
        "rebalancing_period": "none",
        "stop_loss_pct": None,
        "take_profit_pct": None,
        "trailing_stop_pct": None,
        "max_mdd_limit_pct": None,
        "backtest_period": "5y",
        "initial_capital": 10000000.0,
        "execution_timing": "next_open",
        "fee_rate": 0.015,
        "slippage_rate": 0.05,
    }
    base.update(overrides)
    return ParsedStrategy(**base)


def test_compute_strategy_id_ignores_description_metadata():
    left = make_strategy(description="프롬프트 A")
    right = make_strategy(description="완전히 다른 프롬프트 B")

    assert compute_strategy_id(left) == compute_strategy_id(right)
    assert "description" not in to_canonical_strategy_dsl(left)


def test_compute_strategy_id_normalizes_unordered_strategy_arrays():
    left = make_strategy(
        universe=["KOSDAQ", "KOSPI"],
        fundamental_filters=[
            FundamentalFilter(metric="per", operator="<=", value=7.0),
            FundamentalFilter(metric="pbr", operator="<=", value=1.0),
        ],
        entry_signals=[
            TechnicalSignal(indicator="macd", signal_type="buy", mode="crossover"),
            TechnicalSignal(indicator="rsi", signal_type="buy", period=14, operator="<=", value=30),
        ],
        exit_signals=[
            TechnicalSignal(indicator="rsi", signal_type="sell", period=14, operator=">=", value=70),
            TechnicalSignal(indicator="macd", signal_type="sell", mode="zero"),
        ],
    )
    right = make_strategy(
        universe=["KOSPI", "KOSDAQ"],
        fundamental_filters=[
            FundamentalFilter(metric="pbr", operator="<=", value=1.0),
            FundamentalFilter(metric="per", operator="<=", value=7.0),
        ],
        entry_signals=[
            TechnicalSignal(indicator="rsi", signal_type="buy", period=14, operator="<=", value=30),
            TechnicalSignal(indicator="macd", signal_type="buy", mode="crossover"),
        ],
        exit_signals=[
            TechnicalSignal(indicator="macd", signal_type="sell", mode="zero"),
            TechnicalSignal(indicator="rsi", signal_type="sell", period=14, operator=">=", value=70),
        ],
    )

    assert canonical_strategy_json(left) == canonical_strategy_json(right)
    assert compute_strategy_id(left) == compute_strategy_id(right)


@patch("engine.strategy_converter._load_universe", return_value=["005930", "000660"])
def test_to_backtest_request_includes_strategy_id_and_canonical_dsl(_mock):
    strategy = make_strategy(
        description="PBR 1 이하 전략",
        universe=["KOSPI"],
        fundamental_filters=[FundamentalFilter(metric="pbr", operator="<=", value=1.0)],
    )

    request = to_backtest_request(strategy)

    assert request["strategy_id"] == compute_strategy_id(strategy)
    assert request["canonical_strategy_dsl"] == to_canonical_strategy_dsl(strategy)
    assert request["canonical_strategy_dsl"]["fundamental_filters"] == [
        {"metric": "pbr", "operator": "<=", "value": 1.0}
    ]
    assert "description" not in request["canonical_strategy_dsl"]


@patch("engine.strategy_converter._load_universe")
def test_to_backtest_request_can_defer_symbol_resolution(mock_load_universe):
    strategy = make_strategy(universe=["KOSPI200"])

    request = to_backtest_request(strategy, resolve_symbols=False)

    mock_load_universe.assert_not_called()
    assert request["symbols"] == []
    assert request["symbols_resolved"] is False
    assert request["symbol_count"] == 200
    assert request["strategy_id"] == compute_strategy_id(strategy)


@patch("engine.strategy_converter._load_universe", return_value=["005930", "000660"])
def test_to_backtest_request_marks_resolved_symbols_by_default(_mock):
    request = to_backtest_request(make_strategy())

    assert request["symbols"] == ["005930", "000660"]
    assert request["symbols_resolved"] is True
    assert request["symbol_count"] == 2


def test_korean_particle_stop_loss_prompt_reaches_backtest_risk():
    prompt = (
        "KOSPI 종목 중 골든크로스가 나오면 매수하고, "
        "반대로 데드크로스가 나오면 매도하는 식으로 만들어 주세요. "
        "종목은 최대 10개, 손절은 -8%로 부탁드립니다."
    )
    parsed = _apply_prompt_overrides(make_strategy(), prompt)

    request = to_backtest_request(parsed, resolve_symbols=False)

    assert parsed.stop_loss_pct == 8.0
    assert request["risk"]["stop_loss_pct"] == 8.0
    assert request["canonical_strategy_dsl"]["stop_loss_pct"] == 8.0
    assert [(item["id"], item["params"]["signalType"]) for item in request["exit"]["conditions"]] == [
        ("ma_crossover", "sell")
    ]
