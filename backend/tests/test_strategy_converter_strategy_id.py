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


def test_to_backtest_request_converts_percent_costs_to_engine_rates():
    strategy = make_strategy(fee_rate=0.015, slippage_rate=0.05)

    request = to_backtest_request(strategy, resolve_symbols=False)

    assert request["canonical_strategy_dsl"]["fee_rate"] == 0.015
    assert request["canonical_strategy_dsl"]["slippage_rate"] == 0.05
    assert request["options"]["fee_rate"] == 0.00015
    assert request["options"]["slippage_rate"] == 0.0005


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


def test_ranking_strategy_passes_return_ranking_into_risk_params():
    """상대강도 랭킹 전략: ranking_metric/lookback이 risk로 전달되고, 회전은 리밸런싱이 구동."""
    parsed = make_strategy(
        universe=["KOSDAQ"],
        ranking_metric="return",
        ranking_lookback_days=60,
        rebalancing_period="monthly",
        max_positions=6,
        stop_loss_pct=9.0,
    )

    request = to_backtest_request(parsed, resolve_symbols=False)
    risk = request["risk"]

    assert risk["ranking_metric"] == "return"
    assert risk["ranking_lookback_days"] == 60
    assert risk["rebalancing_period"] == "monthly"
    # 리밸런싱이 회전을 구동하므로 보유기간 만료는 끈다(중복 회전 방지).
    assert risk["max_holding_days"] is None
    assert request["canonical_strategy_dsl"]["ranking_metric"] == "return"
    # 진입 조건은 비어 있음 — 선정 자체가 진입.
    assert request["entry"]["conditions"] == []


def test_ranking_strategy_defaults_lookback():
    """lookback 미지정 시 60으로 기본."""
    parsed = make_strategy(ranking_metric="return", ranking_lookback_days=None)

    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]

    assert risk["ranking_lookback_days"] == 60


def test_rebalancing_period_disables_holding_turnover():
    """리밸런싱 주기가 있으면 max_holding_days는 None(달력 리밸런싱이 회전 구동)."""
    parsed = make_strategy(hold_period_days=252, rebalancing_period="yearly")

    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]

    assert risk["rebalancing_period"] == "yearly"
    assert risk["max_holding_days"] is None


def test_no_rebalancing_keeps_holding_period():
    """리밸런싱이 없으면 보유기간은 그대로 max_holding_days로 유지."""
    parsed = make_strategy(hold_period_days=126, rebalancing_period="none")

    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]

    assert risk["max_holding_days"] == 126


def test_non_ranking_strategy_has_null_ranking_metric():
    """랭킹이 아닌 전략은 ranking_metric이 None."""
    risk = to_backtest_request(make_strategy(), resolve_symbols=False)["risk"]

    assert risk["ranking_metric"] is None
