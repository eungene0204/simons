"""정액 적립식(DCA) 장부 — engine/contributions.py (엔진 v16.20).

핵심 계약:
- 납입 일정 = 각 주기의 첫 거래일. 첫 봉은 초기 자본, 이후는 회차 납입액.
- 정수 주만 사고 잔돈은 종목 예산에 이월. 1주 값 > 예산이면 그 회차는 못 사고 다음에 합쳐 산다.
- 납입일에 거래 불가인 종목은 거래 가능해지는 첫 봉에 산다.
- 시간가중 수익률은 납입 효과를 걷어낸다: 가격이 제자리면 납입이 아무리 들어와도 0%.
- 금액가중 수익률(XIRR)은 납입 시점을 반영한다.
- 벤치마크도 같은 날 같은 금액을 넣은 곡선이다.
"""

import numpy as np
import pandas as pd
import pytest

from engine.contributions import (
    contributed_benchmark_equity,
    contribution_flows,
    contribution_settings,
    money_weighted_return,
    simulate_contributions,
    time_weighted_returns,
)


def _frames(prices, index=None, available=None):
    idx = index if index is not None else pd.bdate_range("2024-01-01", periods=len(next(iter(prices.values()))))
    px = pd.DataFrame(prices, index=idx, dtype=float)
    avail = pd.DataFrame(True, index=idx, columns=px.columns) if available is None else available
    return px, avail


# ─── 요청 해석 ────────────────────────────────────────────────────────────────

def test_settings_absent_means_ordinary_backtest():
    assert contribution_settings({}) is None
    assert contribution_settings({"contribution_amount": None, "contribution_period": None}) is None


def test_settings_half_request_fails_fast():
    with pytest.raises(ValueError):
        contribution_settings({"contribution_amount": 500_000})
    with pytest.raises(ValueError):
        contribution_settings({"contribution_period": "monthly"})


def test_settings_rejects_bad_values():
    with pytest.raises(ValueError):
        contribution_settings({"contribution_amount": 0, "contribution_period": "monthly"})
    with pytest.raises(ValueError):
        contribution_settings({"contribution_amount": 100, "contribution_period": "none"})


# ─── 납입 일정 ────────────────────────────────────────────────────────────────

def test_flows_first_bar_is_initial_capital_then_period_firsts():
    idx = pd.bdate_range("2024-01-15", "2024-03-15")
    flows = contribution_flows(idx, 1_000_000, 500_000, "monthly")
    paid = idx[flows > 0]
    assert list(paid.strftime("%Y-%m-%d")) == ["2024-01-15", "2024-02-01", "2024-03-01"]
    assert flows[0] == 1_000_000
    assert flows.sum() == 2_000_000


# ─── 장부 ─────────────────────────────────────────────────────────────────────

def test_integer_shares_and_cash_carry_over():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-02-01", "2024-02-02"])
    px, avail = _frames({"A": [300.0, 300.0, 300.0, 300.0]}, index=idx)
    flows = contribution_flows(idx, 1000, 500, "monthly")           # 1000, 0, 500, 0
    ledger = simulate_contributions(px, px, avail, flows, 0.0, 0.0)
    # 1회차: 1000 → 3주(900), 잔돈 100. 2회차: 100+500=600 → 2주, 잔돈 0.
    assert [(o["date"], o["quantity"], o["round"]) for o in ledger.orders] == [
        ("2024-01-02", 3, 1), ("2024-02-01", 2, 2)]
    assert list(ledger.cash) == [100.0, 100.0, 0.0, 0.0]
    assert list(ledger.equity) == [1000.0, 1000.0, 1500.0, 1500.0]
    assert ledger.total_contributed == 1500.0


def test_fee_and_slippage_match_order_arithmetic():
    idx = pd.to_datetime(["2024-01-02"])
    px, avail = _frames({"A": [100.0]}, index=idx)
    ledger = simulate_contributions(px, px, avail, np.array([1000.0]), 0.01, 0.02)
    # 체결 단가 102, 수수료 1% → 주당 103.02 → 9주. 현금 = 1000 − 9×102×1.01
    assert ledger.orders[0]["quantity"] == 9
    assert ledger.orders[0]["price"] == pytest.approx(102.0)
    assert ledger.cash[0] == pytest.approx(1000 - 9 * 102 * 1.01)
    assert ledger.equity[0] == pytest.approx(ledger.cash[0] + 9 * 100)


def test_share_pricier_than_budget_is_missed_then_bought_with_accumulated_cash():
    idx = pd.to_datetime(["2024-01-02", "2024-02-01", "2024-03-01"])
    px, avail = _frames({"A": [700.0, 700.0, 700.0]}, index=idx)
    flows = np.array([500.0, 500.0, 500.0])
    ledger = simulate_contributions(px, px, avail, flows, 0.0, 0.0)
    assert ledger.missed_rounds == 1
    assert [(o["date"], o["quantity"]) for o in ledger.orders] == [("2024-02-01", 1), ("2024-03-01", 1)]


def test_unavailable_on_deposit_day_buys_on_first_available_bar():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    px, _ = _frames({"A": [100.0, 100.0, 100.0]}, index=idx)
    avail = pd.DataFrame({"A": [False, False, True]}, index=idx)
    ledger = simulate_contributions(px, px, avail, np.array([1000.0, 0.0, 0.0]), 0.0, 0.0)
    assert [(o["date"], o["quantity"]) for o in ledger.orders] == [("2024-01-04", 10)]
    assert list(ledger.cash) == [1000.0, 1000.0, 0.0]


def test_deposit_split_equally_across_symbols():
    idx = pd.to_datetime(["2024-01-02"])
    px, avail = _frames({"A": [100.0], "B": [50.0]}, index=idx)
    ledger = simulate_contributions(px, px, avail, np.array([1000.0]), 0.0, 0.0)
    assert {o["symbol"]: o["quantity"] for o in ledger.orders} == {"A": 5, "B": 10}


# ─── 수익률 ───────────────────────────────────────────────────────────────────

def test_time_weighted_return_ignores_deposits_when_price_is_flat():
    idx = pd.bdate_range("2024-01-01", "2024-06-28")
    px, avail = _frames({"A": [100.0] * len(idx)}, index=idx)
    flows = contribution_flows(idx, 10_000, 10_000, "monthly")
    ledger = simulate_contributions(px, px, avail, flows, 0.0, 0.0)
    assert ledger.equity[-1] == pytest.approx(60_000)             # 자산곡선은 납입만큼 오른다
    twr = time_weighted_returns(ledger.equity, ledger.flows)
    assert np.allclose(twr, 0.0)                                   # 수익률은 0


def test_time_weighted_return_equals_price_return_when_fully_invested():
    idx = pd.bdate_range("2024-01-01", "2024-04-30")
    closes = np.linspace(100.0, 150.0, len(idx))
    px, avail = _frames({"A": closes}, index=idx)
    flows = contribution_flows(idx, 100_000, 100_000, "monthly")   # 100의 배수라 잔돈이 거의 없다
    ledger = simulate_contributions(px, px, avail, flows, 0.0, 0.0)
    total = np.prod(1 + time_weighted_returns(ledger.equity, ledger.flows)) - 1
    # 같은 봉 종가에 사므로 첫 봉 수익률은 0 — 이후는 종가 수익률을 따른다(현금 잔돈만큼의 오차).
    assert total == pytest.approx(closes[-1] / closes[0] - 1, abs=0.01)


def test_money_weighted_return_single_deposit_equals_cagr():
    idx = pd.to_datetime(["2020-01-01", "2022-01-01"])
    rate = money_weighted_return(idx, [1000.0, 0.0], 1210.0)
    years = 731 / 365.25
    assert rate == pytest.approx(1.21 ** (1 / years) - 1, abs=1e-6)


def test_money_weighted_return_reflects_deposit_timing():
    idx = pd.to_datetime(["2020-01-01", "2021-01-01", "2022-01-01"])
    # 같은 총 납입 2000·기말 2200이어도, 늦게 넣은 돈이 많을수록 같은 이익을 더 짧은 시간에 낸 것이다.
    early = money_weighted_return(idx, [1900.0, 100.0, 0.0], 2200.0)
    late = money_weighted_return(idx, [100.0, 1900.0, 0.0], 2200.0)
    assert late > early > 0


def test_money_weighted_return_handles_losses_and_degenerate_input():
    idx = pd.to_datetime(["2020-01-01", "2021-01-01"])
    assert money_weighted_return(idx, [1000.0, 0.0], 500.0) == pytest.approx(0.5 ** (365.25 / 366) - 1, abs=1e-6)
    assert money_weighted_return(idx, [0.0, 0.0], 500.0) is None
    assert money_weighted_return(idx[:1], [1000.0], 1000.0) is None


# ─── 벤치마크 ─────────────────────────────────────────────────────────────────

def test_benchmark_receives_the_same_deposits():
    rets = np.array([0.0, 0.10, 0.0, -0.50])
    flows = np.array([1000.0, 0.0, 1000.0, 0.0])
    eq = contributed_benchmark_equity(rets, flows)
    # 1000 → 1100 → (+1000) 2100 → 1050. 목돈 2000 곡선(2000→2200→2200→1100)과 다르다.
    assert list(eq) == pytest.approx([1000.0, 1100.0, 2100.0, 1050.0])


def test_benchmark_deposit_earns_its_own_bar_return():
    eq = contributed_benchmark_equity(np.array([0.10]), np.array([1000.0]))
    assert eq[0] == pytest.approx(1100.0)


# ─── 엔진 통합 ────────────────────────────────────────────────────────────────

def _write_parquet(path, closes, start="2023-01-02"):
    dates = pd.bdate_range(start, periods=len(closes))
    pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": closes, "high": closes, "low": closes, "close": closes,
        "volume": 1_000_000,
    }).to_parquet(path)


def _dca_request(**risk_overrides):
    return {
        "symbols": ["AAA"], "universe_id": None, "backtest_mode": "single_asset", "period": "FULL",
        "entry": {"logic": "AND", "conditions": []}, "exit": {"conditions": []},
        "risk_params": {"init_cash": 1_000_000.0, "max_positions": 1, "ranking_enabled": False,
                        "contribution_amount": 500_000.0, "contribution_period": "monthly",
                        **risk_overrides},
        "options": {"execution_type": "next_open", "fee_rate": 0.0, "slippage_rate": 0.0,
                    "total_return": False},
    }


@pytest.fixture
def flat_data_dir(tmp_path):
    _write_parquet(tmp_path / "AAA.parquet", [10_000.0] * 130)     # 약 6개월, 가격 제자리
    return tmp_path


def test_engine_runs_contribution_lane(flat_data_dir):
    from backtest_engine import BacktestEngine

    result = BacktestEngine(data_dir=str(flat_data_dir)).run_backtest(_dca_request())
    block = result["contributions"]
    assert block["period"] == "monthly" and block["amount"] == 500_000.0
    assert block["count"] == 6                                     # 첫 봉 + 2~6월 첫 거래일
    assert block["totalContributed"] == 1_000_000 + 5 * 500_000
    assert block["finalValue"] == pytest.approx(block["totalContributed"])
    assert block["cumulative"][-1] == block["totalContributed"]
    # 가격이 제자리면 납입이 들어와도 수익률·낙폭은 0 — 자산곡선만 납입만큼 오른다.
    assert result["totalReturn"] == pytest.approx(0.0)
    assert result["maxDrawdown"] == pytest.approx(0.0)
    assert result["equity"][-1] == pytest.approx(3_500_000)
    assert result["initialCapital"] == 1_000_000
    buys = result["signals"]
    assert len(buys) == 6 and all(s["type"] == "buy" for s in buys)
    assert buys[1]["condition"] == "정기 적립 매수 (2회차)"
    assert buys[1]["quantity"] == 50
    assert any("정액 적립식 결과입니다" in w for w in result["warnings"])
    assert len(result["warnings"]) == len(result["warningParts"])


def test_engine_rejects_contributions_mixed_with_conditions(flat_data_dir):
    from backtest_engine import BacktestEngine

    engine = BacktestEngine(data_dir=str(flat_data_dir))
    with pytest.raises(ValueError, match="정액 적립식"):
        engine.run_backtest(_dca_request(stop_loss_pct=10))
    universe_req = _dca_request()
    universe_req["backtest_mode"] = "universe"
    with pytest.raises(ValueError, match="정액 적립식"):
        engine.run_backtest(universe_req)


def test_request_schema_keeps_contribution_fields():
    """스키마에 없는 키는 model_dump가 조용히 버린다 — 납입 필드가 엔진까지 가는지 고정한다."""
    from schemas import BacktestResponse, RiskManagement

    dumped = RiskManagement(
        position_size_pct=100, contribution_amount=500_000, contribution_period="monthly").model_dump()
    assert dumped["contribution_amount"] == 500_000 and dumped["contribution_period"] == "monthly"
    assert "contributions" in BacktestResponse.model_fields


# ─── 대화 레인(인터프리터 스펙 → DSL → 엔진 요청) ─────────────────────────────

def _dca_intent(**backtest):
    from strategy_conversation.interpreter.models import StrategyIntent

    return StrategyIntent.model_validate({
        "schema_version": "1.0", "intent": "CREATE_STRATEGY",
        "strategy": {"universe": {"symbols": ["KODEX 200"]}, "backtest": backtest},
    })


def test_interpreter_spec_transcribes_contribution_amount():
    """납입액은 초기 자본과 같은 옮겨 적기 계약 — 말한 표기를 결정론 코드가 환산한다."""
    from strategy_conversation.interpreter.models import BacktestSpec

    spec = BacktestSpec(contribution_amount="50만원", contribution_period="monthly")
    assert spec.contribution_amount == 500_000
    assert BacktestSpec(contribution_amount="$500").contribution_amount == 500


def test_prompt_shape_exposes_contribution_keys():
    """형태에 키가 없으면 모델이 그 자리를 채우지 않는다(etf_theme 실측과 같은 실패 방식)."""
    from strategy_conversation.interpreter.prompts import build_system_prompt

    prompt = build_system_prompt()
    assert '"contribution_amount"' in prompt and '"contribution_period"' in prompt


def test_completeness_asks_for_the_missing_half_instead_of_defaulting():
    from strategy_conversation.validation.completeness_validator import validate_completeness

    missing, questions = validate_completeness(_dca_intent(contribution_amount="50만원"))
    assert "strategy.backtest.contribution_period" in missing
    assert "strategy.entry_conditions" not in missing          # 납입 일정이 곧 매수 규칙이다
    assert any(q.field == "strategy.backtest.contribution_period" for q in questions)

    missing, _ = validate_completeness(_dca_intent(contribution_period="monthly"))
    assert "strategy.backtest.contribution_amount" in missing


def test_completeness_asks_which_symbol_to_accumulate():
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.completeness_validator import validate_completeness

    intent = StrategyIntent.model_validate({
        "schema_version": "1.0", "intent": "CREATE_STRATEGY",
        "strategy": {"backtest": {"contribution_amount": "50만원", "contribution_period": "monthly"}},
    })
    missing, _ = validate_completeness(intent)
    assert "strategy.universe.symbols" in missing


def test_converter_carries_contribution_into_engine_request():
    from engine.nl_parser import ParsedStrategy
    from engine.strategy_converter import to_backtest_request

    parsed = ParsedStrategy(
        description="KODEX 200 적립", target_symbols=["069500"],
        contribution_amount=500_000, contribution_period="monthly")
    req = to_backtest_request(parsed)
    assert req["backtest_mode"] == "single_asset"
    assert req["risk"]["contribution_amount"] == 500_000
    assert req["risk"]["contribution_period"] == "monthly"
    assert not req["entry"]["conditions"]


def test_slots_treat_contribution_plan_as_complete_without_entry_or_exit():
    from engine import strategy_slots
    from engine.nl_parser import ParsedStrategy

    parsed = ParsedStrategy(
        description="적립", target_symbols=["069500", "360750"],
        contribution_amount=500_000, contribution_period="monthly")
    for field in strategy_slots.CONTRIBUTION_NOT_APPLICABLE:
        assert strategy_slots._decided(parsed, field, frozenset()).not_applicable
    half = ParsedStrategy(description="반쪽", target_symbols=["069500", "360750"], contribution_amount=500_000)
    assert strategy_slots._decided(half, strategy_slots.ENTRY, frozenset()) is None


def test_capability_normalizes_period_and_strips_plan_mixed_with_conditions():
    from strategy_conversation.validation.capability_validator import validate_capability

    intent = _dca_intent(contribution_amount="50만원", contribution_period="매월")
    validate_capability(intent)
    assert intent.strategy.backtest.contribution_period == "monthly"

    # 손절과 섞인 적립 요청 — 엔진이 거절하는 조합이라 적립 설정을 빼고 무엇이 빠졌는지 알린다.
    mixed = _dca_intent(contribution_amount="50만원", contribution_period="monthly")
    mixed.strategy.risk_management.stop_loss = 10
    errors, _warnings, unsupported, _fixes = validate_capability(mixed)
    assert mixed.strategy.backtest.contribution_amount is None
    assert mixed.strategy.backtest.contribution_period is None
    assert any("정액 적립식" in e for e in errors) and unsupported
