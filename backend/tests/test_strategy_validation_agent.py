"""Regression tests for the deterministic strategy validation contract."""

from __future__ import annotations

import json

from ai.strategy_validation_agent import StrategyValidationAgent


def _valid_strategy(**overrides):
    strategy = {
        "universe": ["KOSPI200"],
        "entry_rule": [
            {"indicator": "rsi", "operator": "<=", "value": 30, "period": 14},
        ],
        "exit_rule": [
            {"indicator": "rsi", "operator": ">=", "value": 70, "period": 14},
        ],
        "rebalance_rule": "monthly",
        "position_sizing": {"method": "equal_weight"},
        "max_positions": 10,
        "stop_loss_pct": 10,
        "take_profit_pct": 20,
        "data_frequency": "daily",
        "backtest_period": "5y",
    }
    strategy.update(overrides)
    return strategy


def _codes(result):
    return {issue["code"] for issue in result["issues"]}


def test_valid_strategy_returns_exact_contract():
    result = StrategyValidationAgent().validate(_valid_strategy())

    assert result == {"is_valid": True, "issues": []}
    assert json.loads(StrategyValidationAgent().validate_json(_valid_strategy())) == result


def test_missing_required_fields_are_errors():
    result = StrategyValidationAgent().validate({})

    assert result["is_valid"] is False
    assert _codes(result) == {
        "MISSING_UNIVERSE",
        "MISSING_ENTRY_RULE",
        "MISSING_EXIT_RULE",
        "MISSING_REBALANCE_RULE",
        "MISSING_POSITION_SIZING",
        "MISSING_MAX_POSITIONS",
        "MISSING_STOP_LOSS",
        "MISSING_TAKE_PROFIT",
        "MISSING_DATA_FREQUENCY",
        "MISSING_BACKTEST_PERIOD",
    }
    assert all(issue["category"] == "missing_field" for issue in result["issues"])


def test_holding_period_can_define_exit_and_engine_aliases_are_supported():
    result = StrategyValidationAgent().validate({
        "symbols": ["005930", "000660"],
        "entry": {"conditions": [{"id": "rsi", "params": {"period": 14}}]},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "max_holding_days": 20,
            "stop_loss_pct": 10,
            "take_profit_pct": 20,
            "rebalancing_period": "none",
        },
        "options": {"timeframe": "1d"},
        "period": "5Y",
    })

    assert result == {"is_valid": True, "issues": []}


def test_missing_take_profit_is_reported_as_non_blocking_warning():
    strategy = _valid_strategy()
    strategy.pop("take_profit_pct")

    result = StrategyValidationAgent().validate(strategy)

    assert result["is_valid"] is True
    assert result["issues"] == [{
        "code": "MISSING_TAKE_PROFIT",
        "severity": "warning",
        "category": "missing_field",
        "field": "take_profit_pct",
        "message": "익절 조건이 정의되어 있지 않습니다.",
    }]


def test_missing_stop_loss_is_reported_as_non_blocking_warning():
    strategy = _valid_strategy()
    strategy.pop("stop_loss_pct")

    result = StrategyValidationAgent().validate(strategy)

    assert result["is_valid"] is True
    assert result["issues"] == [{
        "code": "MISSING_STOP_LOSS",
        "severity": "warning",
        "category": "missing_field",
        "field": "stop_loss_pct",
        "message": "손절 조건이 정의되어 있지 않습니다.",
    }]


def test_missing_exit_and_risk_controls_are_reported_together():
    result = StrategyValidationAgent().validate({
        "universe": ["KOSPI200"],
        "entry_rule": [{"indicator": "pbr", "operator": "<=", "value": 1}],
        "rebalance_rule": "monthly",
        "position_sizing": {"method": "equal_weight"},
        "max_positions": 10,
        "data_frequency": "daily",
        "backtest_period": "5y",
    })

    assert result["is_valid"] is False
    assert _codes(result) == {
        "MISSING_EXIT_RULE",
        "MISSING_STOP_LOSS",
        "MISSING_TAKE_PROFIT",
    }


def test_conflicting_conditions_are_detected_within_same_rule_only():
    conflict = StrategyValidationAgent().validate(_valid_strategy(entry_rule=[
        {"metric": "per", "operator": "<", "value": 5},
        {"metric": "per", "operator": ">", "value": 20},
    ]))
    separate_rules = StrategyValidationAgent().validate(_valid_strategy(
        entry_rule=[{"indicator": "rsi", "operator": "<", "value": 30}],
        exit_rule=[{"indicator": "rsi", "operator": ">", "value": 70}],
    ))

    issue = next(item for item in conflict["issues"] if item["code"] == "LOGICAL_CONFLICT_PER")
    assert issue["category"] == "logical_conflict"
    assert issue["severity"] == "error"
    assert separate_rules["is_valid"] is True


def test_conflicting_rank_conditions_are_detected():
    result = StrategyValidationAgent().validate(_valid_strategy(entry_rule=[
        {"field": "market_cap", "direction": "top", "percentile": 20},
        {"field": "market_cap", "direction": "bottom", "percentile": 20},
    ]))

    assert "LOGICAL_CONFLICT_MARKET_CAP_RANK" in _codes(result)


def test_unsupported_indicator_and_price_field_are_errors():
    result = StrategyValidationAgent().validate(_valid_strategy(entry_rule=[
        {"indicator": "news_sentiment", "operator": ">", "value": 0.5},
        {"id": "price", "price_field": "adjusted_future_close"},
        {"field": "future_eps", "operator": ">", "value": 0},
    ]))

    assert "UNSUPPORTED_FIELD_NEWS_SENTIMENT" in _codes(result)
    assert "UNSUPPORTED_FIELD_FUTURE_EPS" in _codes(result)
    assert "UNSUPPORTED_PRICE_FIELD_ADJUSTED_FUTURE_CLOSE" in _codes(result)
    assert all(issue["category"] == "unsupported_field" for issue in result["issues"])


def test_engine_supported_metrics_are_not_flagged_unsupported():
    """엔진 SOT(FUNDAMENTAL_CIDS)의 재무 지표와 후기 추가 기술 지표를 '미지원 필드'로
    오탐하지 않는다 — 하드코딩 사본이 뒤처져 순이익증가율이 차단되던 사고의 회귀 가드."""
    from engine.signals import FUNDAMENTAL_CIDS

    metric_rules = [{"metric": cid, "operator": ">=", "value": 1} for cid in FUNDAMENTAL_CIDS]
    indicator_rules = [
        {"indicator": name, "operator": ">=", "value": 1}
        for name in ("williams_r", "mfi", "roc")
    ]
    result = StrategyValidationAgent().validate(
        _valid_strategy(entry_rule=metric_rules + indicator_rules)
    )

    assert not any(code.startswith("UNSUPPORTED_FIELD_") for code in _codes(result))


def test_trailing_stop_only_exit_is_not_flagged_unsupported():
    """트레일링 스탑만으로 청산하는 전략은 차단되면 안 된다.

    coach_routes._validation_payload는 청산 신호·보유기간이 없을 때 리스크 청산
    필드(stop_loss_pct/take_profit_pct/trailing_stop_pct/max_mdd_limit_pct)로
    exit_rule을 합성한다. 이 중 trailing_stop_pct가 지원 목록에 빠져 있어 유효한
    트레일링 전략이 UNSUPPORTED_FIELD 에러로 잘못 차단되던 회귀를 막는다.
    """
    from api.coach_routes import _validation_payload

    parsed = {
        "universe": ["KOSPI200"],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 0.8}],
        "entry_signals": [],
        "exit_signals": [],
        "max_positions": 5,
        "rebalancing_period": "monthly",
        "backtest_period": "5y",
        "trailing_stop_pct": 10.0,
        "stop_loss_pct": None,
        "take_profit_pct": None,
    }
    result = StrategyValidationAgent().validate(_validation_payload(parsed))

    assert result["is_valid"] is True
    assert "UNSUPPORTED_FIELD_TRAILING_STOP_PCT" not in _codes(result)
    assert not any(issue["severity"] == "error" for issue in result["issues"])


def test_invalid_parameters_are_reported_without_advice():
    result = StrategyValidationAgent().validate(_valid_strategy(
        max_positions=0,
        entry_rule=[{"indicator": "rsi", "period": 0, "weight": 1.2}],
        position_sizing={"position_size_pct": 120},
        stop_loss_pct=-1,
        rebalance_interval=-5,
    ))

    assert {
        "INVALID_MAX_POSITIONS",
        "INVALID_PERIOD",
        "INVALID_WEIGHT",
        "INVALID_POSITION_SIZE",
        "INVALID_STOP_LOSS_PCT",
        "INVALID_REBALANCE_INTERVAL",
    } <= _codes(result)
    assert all(issue["category"] == "invalid_parameter" for issue in result["issues"])


def test_impossible_position_count_and_condition_frequency_are_errors():
    result = StrategyValidationAgent().validate(_valid_strategy(
        universe=["005930", "000660"],
        universe_size=2,
        max_positions=3,
        entry_rule=[{"indicator": "rsi", "period": 14, "frequency": "60min"}],
    ))

    assert "MAX_POSITIONS_EXCEEDS_UNIVERSE" in _codes(result)
    assert "CONDITION_FREQUENCY_TOO_SHORT" in _codes(result)
    impossible = [issue for issue in result["issues"] if issue["category"] == "impossible_condition"]
    assert all(issue["severity"] == "error" for issue in impossible)


def test_restrictive_filter_returns_warning_without_invalidating_execution():
    result = StrategyValidationAgent().validate(_valid_strategy(entry_rule=[
        {"metric": "pbr", "operator": "<", "value": 0.1},
    ]))

    assert result["is_valid"] is True
    assert result["issues"] == [{
        "code": "EMPTY_UNIVERSE_POSSIBLE",
        "severity": "warning",
        "category": "impossible_condition",
        "field": "universe",
        "message": "조건으로 인해 대상 종목이 존재하지 않을 수 있습니다.",
    }]


def test_result_messages_never_contain_coaching_language():
    result = StrategyValidationAgent().validate(_valid_strategy(
        entry_rule=[{"indicator": "unsupported_alpha"}],
        max_positions=0,
    ))
    serialized = json.dumps(result, ensure_ascii=False)

    forbidden = (
        "수익률을 높이려면",
        "추가하는 것이 좋습니다",
        "늘려보세요",
        "사용해보세요",
        "추천",
        "개선이 필요",
    )
    assert not any(phrase in serialized for phrase in forbidden)


def test_non_object_input_still_returns_json_contract():
    result = StrategyValidationAgent().validate("RSI 전략")

    assert result["is_valid"] is False
    assert result["issues"][0]["code"] == "INVALID_STRATEGY_TYPE"
