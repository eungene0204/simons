"""경쟁 격차 1차(엔진 v16.28) — 대화 레인(검증→컴파일→엔진 요청→디컴파일 왕복) 계약.

- 비중 방식 8종 정규화(표기 변형 → 정본), 리스크 패리티는 이제 엔진 ERC(근사 안내 없음).
- 새 설정(밴드·최소 보유·재진입 금지·트레일링 활성화·지정가·분할·사이징·안전자산·절대 모멘텀·평균가 체결·
  거래량 슬리피지)이 ParsedStrategy → 엔진 요청까지 관통하고, 값 대기(회차·비율 미정)면 되묻기 + 미전송.
- 고정 배분의 종목 표기는 정본 코드로 옮겨지고 지정 종목 목록에 더해진다.
- 디컴파일 왕복이 새 필드를 전부 보존한다(수정 턴에서 조용히 풀리지 않게).
- 새 설정이 없는 전략의 정본 DSL은 변하지 않는다(해시 불변).
"""

import pytest

from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry import capability_registry as caps
from strategy_conversation.validation.pipeline import run_validation


def _intent(**strategy_overrides):
    strategy = {
        "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": [], "symbols": []},
        "entry_conditions": [],
        "exit_conditions": [],
        "ranking": [{"metric": "ranking.return", "lookback_days": 120}],
        "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly"},
        "risk_management": {},
        "backtest": {},
    }
    strategy.update(strategy_overrides)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": strategy,
    })


def _compile(intent):
    validated, report = run_validation(intent)
    parsed, dropped, pending = compile_partial(validated, report, "")
    return validated, report, parsed, dropped, pending


@pytest.mark.parametrize("raw,expected", [
    ("시가총액", "market_cap"), ("market cap", "market_cap"), ("최소분산", "min_variance"),
    ("Risk Parity", "risk_parity"), ("erc", "risk_parity"), ("MVO", "max_sharpe"),
    ("min_cvar", "min_cvar"), ("고정비중", "fixed"), ("역변동성", "inverse_volatility"),
])
def test_weighting_aliases_normalize_to_engine_enum(raw, expected):
    assert caps.normalize_weighting(raw) == expected
    assert expected in caps.SUPPORTED_WEIGHTINGS


@pytest.mark.parametrize("weighting", ["market_cap", "min_variance", "risk_parity", "max_sharpe", "min_cvar"])
def test_weighting_reaches_engine_request_and_round_trips(weighting):
    _, report, parsed, _, _ = _compile(_intent(
        portfolio={"selection_count": 10, "rebalance_frequency": "monthly",
                   "weighting": weighting, "weighting_lookback_days": 90},
    ))
    assert not report.unsupported_features
    assert parsed.allocation_type == weighting
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["allocation_type"] == weighting
    if weighting == "market_cap":
        assert parsed.allocation_lookback_days is None
    else:
        assert risk["allocation_lookback_days"] == 90
    assert decompile_strategy(parsed).portfolio.weighting == weighting


def test_optimizer_without_lookback_asks_for_period():
    _, report, parsed, _, _ = _compile(_intent(
        portfolio={"selection_count": 10, "rebalance_frequency": "monthly", "weighting": "min_variance"},
    ))
    assert parsed.allocation_type == "min_variance"
    assert any(q.field == "strategy.portfolio.weighting_lookback_days" for q in report.clarification_questions)


def test_fixed_weights_resolve_symbols_and_become_explicit_universe():
    _, report, parsed, _, _ = _compile(_intent(
        ranking=[],
        universe={"markets": ["KOSPI"], "sectors": [], "symbols": []},
        portfolio={"weighting": "fixed", "rebalance_frequency": "quarterly",
                   "target_weights": {"삼성전자": 60, "SK하이닉스": 40}},
    ))
    assert parsed.allocation_type == "fixed"
    assert parsed.target_weights == {"005930": 60.0, "000660": 40.0}
    assert set(parsed.target_symbols) == {"005930", "000660"}
    req = to_backtest_request(parsed)
    assert req["risk"]["allocation_type"] == "fixed"
    assert req["risk"]["target_weights"] == {"005930": 60.0, "000660": 40.0}
    assert decompile_strategy(parsed).portfolio.target_weights == {"005930": 60.0, "000660": 40.0}


def test_fixed_without_weights_asks():
    _, report, parsed, _, _ = _compile(_intent(portfolio={"weighting": "fixed", "rebalance_frequency": "monthly"}))
    assert any(q.field == "strategy.portfolio.target_weights" for q in report.clarification_questions)


def test_band_min_hold_cash_asset_and_absolute_momentum_reach_engine():
    _, report, parsed, _, _ = _compile(_intent(
        portfolio={"selection_count": 5, "rebalance_frequency": "monthly", "rebalance_band_percent": 5,
                   "min_hold_period_days": 10, "cash_asset": "삼성전자",
                   "absolute_momentum_threshold_percent": 0},
    ))
    assert not report.unsupported_features and not report.errors
    assert parsed.rebalance_threshold_pct == 5 and parsed.min_holding_days == 10
    assert parsed.cash_asset == "005930" and parsed.absolute_momentum_threshold_pct == 0
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["rebalance_threshold_pct"] == 5 and risk["min_holding_days"] == 10
    assert risk["cash_asset"] == "005930" and risk["absolute_momentum_threshold_pct"] == 0
    spec = decompile_strategy(parsed)
    assert spec.portfolio.rebalance_band_percent == 5 and spec.portfolio.min_hold_period_days == 10
    assert spec.portfolio.cash_asset == "005930" and spec.portfolio.absolute_momentum_threshold_percent == 0


def test_risk_extensions_reach_engine_and_incomplete_ones_ask():
    _, report, parsed, _, _ = _compile(_intent(
        risk_management={"stop_loss": 8, "trailing_stop": 10, "trailing_stop_activation": 15,
                         "stop_cooldown_days": 5,
                         "partial_take_profits": [{"profit_percent": 10, "sell_percent": 50}],
                         "position_sizing": {"method": "atr_risk", "risk_per_trade_percent": 1, "atr_multiple": 2}},
    ))
    assert not report.unsupported_features
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["stop_cooldown_days"] == 5 and risk["trailing_stop_activation_pct"] == 15
    assert risk["partial_take_profits"] == [{"profit_pct": 10.0, "sell_pct": 50.0}]
    assert risk["position_sizing"] == {"method": "atr_risk", "risk_per_trade_pct": 1.0, "atr_multiple": 2.0}
    spec = decompile_strategy(parsed).risk_management
    assert spec.stop_cooldown_days == 5 and spec.partial_take_profits[0].sell_percent == 50
    assert spec.position_sizing.method == "atr_risk"

    _, report2, parsed2, _, _ = _compile(_intent(
        risk_management={"partial_take_profits": [{"profit_percent": 10}],
                         "position_sizing": {"method": "kelly"}},
    ))
    fields = {q.field for q in report2.clarification_questions}
    assert "strategy.risk_management.partial_take_profits.0" in fields
    assert "strategy.risk_management.position_sizing.kelly_fraction" in fields
    risk2 = to_backtest_request(parsed2, resolve_symbols=False)["risk"]
    assert risk2["partial_take_profits"] is None and risk2["position_sizing"] is None   # 값 대기 = 미전송


def test_execution_extensions_reach_engine_and_reject_same_close():
    _, report, parsed, _, _ = _compile(_intent(
        backtest={"execution_timing": "next_avg", "entry_limit_percent": 2, "exit_limit_percent": 1,
                  "entry_tranches": {"count": 3, "step_percent": 5}, "slippage_model": "volume_impact"},
    ))
    assert not report.unsupported_features and not report.errors
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["risk"]["execution_timing"] == "next_avg"
    assert req["risk"]["entry_limit_pct"] == 2 and req["risk"]["exit_limit_pct"] == 1
    assert req["risk"]["entry_tranches"] == {"count": 3, "step_pct": 5.0}
    assert req["options"]["slippage_model"] == "volume_impact"
    spec = decompile_strategy(parsed).backtest
    assert spec.execution_timing == "next_avg" and spec.entry_tranches.count == 3
    assert spec.slippage_model == "volume_impact"

    _, report2, parsed2, _, _ = _compile(_intent(
        backtest={"execution_timing": "current_close", "entry_limit_percent": 2},
    ))
    assert any("지정가" in e for e in report2.errors)
    assert parsed2.entry_limit_pct is None

    _, report3, parsed3, _, _ = _compile(_intent(backtest={"entry_tranches": {"count": 3}}))
    assert any(q.field == "strategy.backtest.entry_tranches" for q in report3.clarification_questions)
    assert to_backtest_request(parsed3, resolve_symbols=False)["risk"]["entry_tranches"] is None


def test_strategy_without_new_settings_keeps_canonical_dsl():
    _, _, parsed, _, _ = _compile(_intent())
    dsl = to_canonical_strategy_dsl(parsed)
    for key in ("target_weights", "rebalance_threshold_pct", "min_holding_days", "stop_cooldown_days",
                "trailing_stop_activation_pct", "entry_limit_pct", "exit_limit_pct", "entry_tranches",
                "partial_take_profits", "position_sizing", "cash_asset", "absolute_momentum_threshold_pct",
                "slippage_model", "slippage_impact_coeff"):
        assert key not in dsl
