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
    contribution_rules,
    contribution_settings,
    rule_symbol_flows,
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
    with pytest.raises(ValueError, match="정액 적립식"):
        engine.run_backtest(_dca_request(ranking_metric="return"))


# ─── 조건부 납입액(v16.21) ────────────────────────────────────────────────────

_BELOW_MA = {"type": "indicator", "id": "ma_crossover", "weight": 1.0,
             "params": {"signalType": "buy", "shortMA": 1, "longMA": 20, "mode": "below"}}


def test_rules_absent_and_bad_rules():
    assert contribution_rules({}) == []
    with pytest.raises(ValueError):
        contribution_rules({"contribution_rules": [{"condition": _BELOW_MA, "amount": 0, "mode": "set"}]})
    with pytest.raises(ValueError):
        contribution_rules({"contribution_rules": [{"condition": _BELOW_MA, "amount": 10, "mode": "double"}]})
    with pytest.raises(ValueError):
        contribution_rules({"contribution_rules": [{"condition": {}, "amount": 10, "mode": "set"}]})


def test_rule_amounts_base_then_set_max_then_add():
    """기본 100 → set(200·300 중 큰 쪽) → add(+50). 첫 봉(초기 자본)은 규칙 대상이 아니다."""
    base = np.array([1000.0, 0.0, 100.0, 100.0, 100.0])
    rules = [{"amount": 200.0, "mode": "set"}, {"amount": 300.0, "mode": "set"},
             {"amount": 50.0, "mode": "add"}]
    hits = [np.array([[True], [True], [True], [False], [False]]),
            np.array([[True], [False], [True], [False], [False]]),
            np.array([[True], [False], [False], [True], [False]])]
    per_symbol, counts = rule_symbol_flows(base, 100.0, rules, hits)
    assert per_symbol[:, 0].tolist() == [1000.0, 0.0, 300.0, 150.0, 100.0]
    assert counts == [1, 1, 1]


def test_rule_amounts_apply_per_symbol_share():
    base = np.array([1000.0, 100.0])
    hits = [np.array([[False, False], [True, False]])]
    per_symbol, _ = rule_symbol_flows(base, 100.0, [{"amount": 200.0, "mode": "set"}], hits)
    assert per_symbol.tolist() == [[500.0, 500.0], [100.0, 50.0]]


def test_ledger_uses_symbol_flows():
    px, avail = _frames({"A": [100.0] * 3})
    ledger = simulate_contributions(px, px, avail, np.zeros(3), 0.0, 0.0,
                                    symbol_flows=np.array([[1000.0], [0.0], [300.0]]))
    assert ledger.flows.tolist() == [1000.0, 0.0, 300.0]
    assert ledger.shares[:, 0].tolist() == [10.0, 10.0, 13.0]


@pytest.fixture
def falling_data_dir(tmp_path):
    # 60봉 완만한 상승(종가 > 20일선) → 이후 하락: 하락 구간의 납입일만 '종가 ≤ 20일선'이 성립한다.
    closes = [10_000.0 + 10.0 * i for i in range(60)] + [10_590.0 - 40.0 * i for i in range(1, 71)]
    _write_parquet(tmp_path / "AAA.parquet", closes)
    return tmp_path


def test_engine_applies_conditional_contribution(falling_data_dir):
    from backtest_engine import BacktestEngine

    rule = {"condition": _BELOW_MA, "amount": 1_000_000.0, "mode": "set"}
    plain = BacktestEngine(data_dir=str(falling_data_dir)).run_backtest(_dca_request())
    ruled = BacktestEngine(data_dir=str(falling_data_dir)).run_backtest(
        _dca_request(contribution_rules=[rule]))
    block = ruled["contributions"]
    applied = block["rules"][0]["applied"]
    assert block["rules"][0]["mode"] == "set" and applied >= 1
    assert block["count"] == plain["contributions"]["count"]          # 일정은 같고 금액만 다르다
    assert block["totalContributed"] == plain["contributions"]["totalContributed"] + applied * 500_000
    assert any("조건부 납입액 규칙" in w for w in ruled["warnings"])
    assert len(ruled["warnings"]) == len(ruled["warningParts"])


def test_conditional_contribution_does_not_look_ahead(tmp_path):
    """시가 체결: 납입일 **당일** 종가로 조건이 처음 성립하면 그 회차는 기본액이다(전일 기준 판정)."""
    from backtest_engine import BacktestEngine

    dates = pd.bdate_range("2023-01-02", periods=45)
    first_feb = next(i for i, d in enumerate(dates) if d.month == 2)
    # 완만한 상승(종가 > 20일선) — 엔진의 '아래'는 <= 라 제자리 가격은 성립으로 본다.
    closes = [10_000.0 + 10.0 * i for i in range(len(dates))]
    closes[first_feb] = 9_000.0                                       # 2월 첫 거래일 하루만 급락
    _write_parquet(tmp_path / "AAA.parquet", closes)
    rule = {"condition": _BELOW_MA, "amount": 1_000_000.0, "mode": "set"}
    next_open = BacktestEngine(data_dir=str(tmp_path)).run_backtest(
        _dca_request(contribution_rules=[rule]))
    assert next_open["contributions"]["rules"][0]["applied"] == 0
    same_close = _dca_request(contribution_rules=[rule])
    same_close["options"]["execution_type"] = "same_close"
    at_close = BacktestEngine(data_dir=str(tmp_path)).run_backtest(same_close)
    assert at_close["contributions"]["rules"][0]["applied"] == 1


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


def test_completeness_takes_a_stated_etf_universe_as_the_accumulation_target():
    """2026-09-22 사용자 보고: "S&P500 ETF를 100만 원씩"이라고 말했는데 "어떤 종목(또는 ETF)을 사 모을까요?"를
    물었다 — 'S&P500 ETF'는 국내 S&P500 ETF 전체가 유니버스다. 상품 유니버스를 말했으면 묻지 않고,
    시장만 말했으면(ETF 전체) 종전대로 묻는다."""
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.completeness_validator import validate_completeness

    def _intent(universe):
        return StrategyIntent.model_validate({
            "schema_version": "1.0", "intent": "CREATE_STRATEGY",
            "strategy": {"universe": universe,
                         "backtest": {"contribution_amount": "100만원", "contribution_period": "monthly"}}})

    missing, _ = validate_completeness(_intent({"markets": ["ETF"], "etf_theme": "S&P500"}))
    assert "strategy.universe.symbols" not in missing
    missing, _ = validate_completeness(_intent({"markets": ["ETF"]}))
    assert "strategy.universe.symbols" in missing


def test_engine_runs_contribution_lane_over_a_universe(tmp_path, monkeypatch):
    """적립 대상이 유니버스(backtest_mode=universe)여도 같은 장부로 돈다 — 종목 전체에 균등 분할.
    (종전에는 single_asset이 아니면 거절했다 — "S&P500 ETF"는 국내 S&P500 ETF 전체가 유니버스다, 2026-09-22.)"""
    from backtest_engine import BacktestEngine
    from engine import universe_pit

    # ETF 마스터 조회는 실제 상장 코드로 바꿔치므로, 테스트 데이터의 두 종목이 그대로 유니버스가 되게 한다.
    monkeypatch.setattr(universe_pit, "resolve_etf_symbols", lambda *_a, **_k: [])
    monkeypatch.setattr(universe_pit, "etf_master_includes_delisted", lambda: True)
    _write_parquet(tmp_path / "AAA.parquet", [10_000.0] * 130)
    _write_parquet(tmp_path / "BBB.parquet", [20_000.0] * 130)
    req = _dca_request()
    req.update({"symbols": ["AAA", "BBB"], "backtest_mode": "universe", "universe_id": "ETF"})
    req["risk_params"]["max_positions"] = 10
    result = BacktestEngine(data_dir=str(tmp_path)).run_backtest(req)
    block = result["contributions"]
    assert block["count"] == 6 and block["totalContributed"] == 1_000_000 + 5 * 500_000
    buys = [s for s in result["signals"] if s.get("type") == "buy"]
    assert {b["symbol"] for b in buys} == {"AAA", "BBB"}
    assert result["equity"][-1] == pytest.approx(3_500_000)


def test_contribution_plan_predicate_accepts_an_etf_universe():
    from engine.strategy_slots import has_contribution_plan
    from engine.strategy_converter import ParsedStrategy

    themed = ParsedStrategy(description="적립", universe=["ETF"], etf_theme="S&P500",
                            contribution_amount=1_000_000, contribution_period="monthly")
    assert has_contribution_plan(themed)
    assert not has_contribution_plan(ParsedStrategy(description="적립", universe=["ETF"],
                                                    contribution_amount=1_000_000, contribution_period="monthly"))


def test_validation_agent_treats_contribution_plan_as_entry_and_needs_no_exit():
    """2026-09-22 사용자 보고: 적립식에 '백테스트 시작'을 누르자 전략 검증이 "진입 조건을 입력해 주세요"를 냈다 —
    검증 agent가 적립 계획을 모르고 진입·청산·손절·익절 누락을 보고했다. 납입 일정이 곧 매수 규칙이고 매도가
    없다(슬롯 정본 CONTRIBUTION_NOT_APPLICABLE과 동형). 반쪽 계획(대상 없음)은 종전대로 묻는다."""
    from ai.strategy_validation_agent import StrategyValidationAgent
    from api.coach_routes import _validation_payload
    from engine.strategy_converter import ParsedStrategy

    plan = ParsedStrategy(description="적립", universe=["ETF"], etf_theme="S&P500", backtest_period="3y",
                          contribution_amount=1_000_000, contribution_period="monthly")
    issues = StrategyValidationAgent().validate(_validation_payload(plan.model_dump()))["issues"]
    assert not any(i["field"] in ("entry_rule", "exit_rule", "stop_loss_pct", "take_profit_pct") for i in issues), issues

    half = plan.model_copy(update={"etf_theme": None})
    issues = StrategyValidationAgent().validate(_validation_payload(half.model_dump()))["issues"]
    assert any(i["field"] == "entry_rule" for i in issues)


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


# ─── 조건부 납입액 — 대화 레인(v16.21) ────────────────────────────────────────

def _rule_intent(entry_conditions, **backtest):
    from strategy_conversation.interpreter.models import StrategyIntent

    return StrategyIntent.model_validate({
        "schema_version": "1.0", "intent": "CREATE_STRATEGY",
        "strategy": {
            "universe": {"symbols": ["KODEX 200"]},
            "entry_conditions": entry_conditions,
            "backtest": {"contribution_amount": "100만원", "contribution_period": "monthly", **backtest},
        },
    })


_BELOW_200 = {"factor": "technical.ma_crossover", "operator": "<",
              "parameters": {"short_period": 1, "long_period": 200},
              "source_text": "종가가 200일 이동평균선 아래에 있으면",
              "buy_amount": "200만원", "buy_amount_mode": "set"}
_RSI_ADD = {"factor": "technical.rsi", "operator": "<", "value": 30, "parameters": {"period": 14},
            "source_text": "RSI(14)가 30 미만이면", "buy_amount": "100만원", "buy_amount_mode": "add"}


def test_main_prompt_carries_no_buy_amount_slot():
    """메인 프롬프트에 자리를 만드는 안은 측정으로 기각했다(2026-09-21, 120B): 규칙 4줄+형태 키는
    적립 문장을 4/4 해석했지만 되묻기 하니스 2건이 회귀했고(A/B로 인과 확인), 2줄로 줄이면 해석이
    1/4로 떨어졌다 — 금액은 전용 패스(contribution_amount_check)가 옮긴다."""
    from strategy_conversation.interpreter.prompts import build_system_prompt

    assert "buy_amount" not in build_system_prompt()


def _plain(cond):
    return {k: v for k, v in cond.items() if not k.startswith("buy_amount")}


def _amount_chat(payload):
    def chat(_system, _user, **_kw):
        return payload
    return chat


_DCA_SENTENCE = ("매월 첫 거래일마다 S&P500 ETF를 100만 원씩 매수합니다. 종가가 200일 이동평균선 아래에 "
                 "있으면 200만 원을 매수합니다. RSI(14)가 30 미만이면 추가로 100만 원을 더 매수합니다. "
                 "단일 매수 금액은 보유 현금의 10%를 넘지 않으며, 항상 일정 수준의 현금을 유지합니다.")
_PLAN_ECHO = {"factor": "fundamental.trading_value", "operator": ">=", "value": 100, "unit": "억원",
              "source_text": "S&P500 ETF를 100만 원씩 매수합니다"}
_JUNK_CAP = {"factor": "fundamental.trading_value", "operator": "<=",
             "source_text": "단일 매수 금액은 보유 현금의 10%를 넘지 않으며"}
# 통합 판정의 전형적인 답 — 규칙은 [조건] 인용으로 대조하고, 순서·개수에 기대지 않는다.
_PLAN_REPLY = ('{"plan": {"quote": "매월 첫 거래일마다 S&P500 ETF를 100만 원씩 매수합니다", "amount": "100만 원", '
               '"period": "monthly"}, '
               '"rules": [{"quote": "매월 첫 거래일마다 100만 원씩", "amount": "100만원", "mode": "set", "state": null}, '
               '{"quote": "종가가 200일 이동평균선 아래에 있으면", "amount": "200만원", "mode": "set", "state": "below"}, '
               '{"quote": "RSI(14)가 30 미만이면", "amount": "100만 원", "mode": "add", "state": null}], '
               '"cash_reserve": {"stated": true, "percent": null, "amount": null, "quote": "항상 일정 수준의 현금을 유지합니다"}, '
               '"max_buy": {"percent": 10, "quote": "단일 매수 금액은 보유 현금의 10%를 넘지 않으며"}}')


def _no_plan_intent(entry_conditions, unsupported=()):
    from strategy_conversation.interpreter.models import StrategyIntent

    return StrategyIntent.model_validate({
        "schema_version": "1.0", "intent": "CREATE_STRATEGY",
        "strategy": {"entry_conditions": entry_conditions},
        "unsupported_features": list(unsupported),
    })


def test_plan_check_tags_rules_by_quote_not_by_position():
    """2026-09-22 12:08 사고: 조건 1개를 물었는데 120B가 문장 순서대로 3개를 답해 '항목 수 불일치'로 판정이
    없어졌다. 통합 판정은 [조건] 인용으로 대조한다 — 여분(기본 납입 되풀이)은 버리고, 짝이 없는 조건은 꼬리표 없음."""
    from strategy_conversation.interpreter import contribution_plan_check as cpc
    from strategy_conversation.primary import _resolve_contribution_plan

    event = {**_plain(_BELOW_200), "operator": "crosses_below"}
    intent = _rule_intent([_JUNK_CAP, event, _plain(_RSI_ADD)])
    intent.unsupported_features = ["항상 일정 수준의 현금을 유지합니다", "소르티노 지수"]
    assert cpc.applies_to(intent)
    _resolve_contribution_plan(intent, _DCA_SENTENCE, _amount_chat(_PLAN_REPLY))

    conds = intent.strategy.entry_conditions
    assert [c.factor for c in conds] == ["technical.ma_crossover", "technical.rsi"]      # 지어낸 상한 조건은 걷힘
    assert [(c.buy_amount, c.buy_amount_mode, c.operator) for c in conds] == [
        (2_000_000, "set", "<"),          # 교차 사건 → 상태 연산자
        (1_000_000, "add", "<")]          # 이미 낸 비교는 불변
    pool = intent.strategy.backtest.cash_pool
    assert (pool.reserve_stated, pool.reserve_pct, pool.max_buy_pct, pool.is_complete()) == (True, None, 10, False)
    assert intent.unsupported_features == ["소르티노 지수"]
    assert intent.strategy.backtest.contribution_amount == 1_000_000                    # 1차 값은 덮어쓰지 않는다


def test_plan_check_restores_a_dropped_plan_with_strict_source_match():
    """1차가 계획을 비우고 "100만 원씩 매수"를 거래대금 조건으로 지어낸 턴(2026-09-21 19:47) — 통합 판정이 계획을
    채우고 같은 구절의 거래대금 조건을 걷는다. 인용·금액 표기가 입력에 그대로 없으면 채우지 않는다."""
    from strategy_conversation.primary import _resolve_contribution_plan

    intent = _no_plan_intent([_PLAN_ECHO, _plain(_RSI_ADD)])
    _resolve_contribution_plan(intent, _DCA_SENTENCE, _amount_chat(_PLAN_REPLY))
    bt = intent.strategy.backtest
    assert (bt.contribution_amount, bt.contribution_period) == (1_000_000, "monthly")
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.rsi"]
    assert intent.strategy.entry_conditions[0].buy_amount == 1_000_000

    invented = _PLAN_REPLY.replace("매월 첫 거래일마다 S&P500 ETF를 100만 원씩 매수합니다", "매주 50만원씩 적립") \
                          .replace('"amount": "100만 원", "period": "monthly"', '"amount": "50만원", "period": "weekly"')
    intent = _no_plan_intent([_PLAN_ECHO], unsupported=["항상 일정 수준의 현금을 유지합니다"])
    _resolve_contribution_plan(intent, _DCA_SENTENCE, _amount_chat(invented))
    assert intent.strategy.backtest.contribution_amount is None and len(intent.strategy.entry_conditions) == 1


def test_plan_check_is_gated_and_fails_open():
    from strategy_conversation.interpreter import contribution_plan_check as cpc
    from strategy_conversation.primary import _resolve_contribution_plan

    def _must_not_call(*_a, **_kw):
        raise AssertionError("적립이 아닌 턴은 호출이 없어야 한다")

    clean = _no_plan_intent([_plain(_RSI_ADD)])
    assert not cpc.applies_to(clean)
    _resolve_contribution_plan(clean, _DCA_SENTENCE, _must_not_call)

    calls = []

    def broken(_s, _u, **_kw):
        calls.append(1)
        return "not json"
    intent = _rule_intent([_plain(_RSI_ADD)])
    _resolve_contribution_plan(intent, _DCA_SENTENCE, broken)
    assert len(calls) == 2                                            # 1회 재시도 뒤 판정 없음
    assert intent.strategy.entry_conditions[0].buy_amount is None
    # enum 밖 방식·환산 불가 금액·범위 밖 비율은 그 항목만 버린다
    odd = ('{"plan": null, "rules": [{"quote": "RSI(14)가 30 미만이면", "amount": "많이", "mode": "set"}], '
           '"cash_reserve": {"stated": true, "percent": 150}, "max_buy": {"percent": 0}}')
    intent = _rule_intent([_plain(_RSI_ADD)])
    _resolve_contribution_plan(intent, _DCA_SENTENCE, _amount_chat(odd))
    assert intent.strategy.entry_conditions[0].buy_amount is None
    pool = intent.strategy.backtest.cash_pool
    assert (pool.reserve_pct, pool.max_buy_pct, pool.is_complete()) == (None, None, False)


def test_sell_relocation_leaves_contribution_turns_alone():
    """2026-09-22 12:08 사고의 마지막 고리: 재생성본의 crosses_below(사건)를 일반 전략용 보정이 매도 선언으로 보고
    청산 칸에 옮겨 '매수·매도 조건이 있는 적립식'이 됐다. 적립 턴(계획 칸이 채워진 뒤)에는 재배치하지 않는다."""
    from strategy_conversation.primary import _fill_deterministic_condition_params

    event = {**_plain(_BELOW_200), "operator": "crosses_below"}
    intent = _rule_intent([event])
    _fill_deterministic_condition_params(intent)
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.ma_crossover"]
    assert intent.strategy.exit_conditions == []

    plain = _no_plan_intent([event])
    _fill_deterministic_condition_params(plain)
    assert plain.strategy.entry_conditions == [] and len(plain.strategy.exit_conditions) == 1   # 일반 전략은 종전대로



def test_amount_tagged_conditions_keep_the_plan_and_compile_to_rules():
    from strategy_conversation.compiler.strategy_compiler import compile_partial
    from strategy_conversation.validation.pipeline import run_validation

    intent, report = run_validation(_rule_intent([_BELOW_200, _RSI_ADD]))
    assert intent.strategy.backtest.contribution_amount == 1_000_000
    assert not any("청산" in q.question or "팔지" in q.question for q in report.clarification_questions)
    parsed, dropped, _pending = compile_partial(intent, report, "적립")
    assert not dropped and not parsed.entry_signals
    rules = parsed.contribution_rules
    assert [(r.signal.indicator, r.mode, r.amount) for r in rules] == [
        ("ma_crossover", "set", 2_000_000), ("rsi", "add", 1_000_000)]
    assert (rules[0].signal.mode, rules[0].signal.short_period, rules[0].signal.long_period) == ("below", 1, 200)


def test_junk_amount_conditions_are_dropped_without_killing_the_plan():
    """120B 실측: 기본 납입을 거래대금 조건으로 되풀이(같은 금액·set)=조용히, 그 밖의 비기술 조건=안내."""
    from strategy_conversation.validation.capability_validator import validate_capability

    restated = {"factor": "fundamental.trading_value", "operator": ">=",
                "source_text": "매월 첫 거래일마다 100만 원씩 매수합니다",
                "buy_amount": "100만원", "buy_amount_mode": "set"}
    cash_cap = {"factor": "fundamental.trading_value", "operator": "<=",
                "source_text": "단일 매수 금액은 보유 현금의 10%를 넘지 않으며",
                "buy_amount": "50만원", "buy_amount_mode": "set"}
    intent = _rule_intent([restated, cash_cap, _BELOW_200])
    _errors, _warnings, unsupported, _fixes = validate_capability(intent)
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.ma_crossover"]
    assert intent.strategy.backtest.contribution_amount == 1_000_000
    assert unsupported == ["단일 매수 금액은 보유 현금의 10%를 넘지 않으며"]


def test_plain_entry_next_to_rules_is_dropped_with_notice_not_the_plan():
    from strategy_conversation.validation.capability_validator import validate_capability

    plain = {"factor": "technical.rsi", "operator": "<", "value": 40, "source_text": "RSI 40 아래"}
    intent = _rule_intent([plain, _BELOW_200])
    _errors, _warnings, unsupported, _fixes = validate_capability(intent)
    assert [c.buy_amount for c in intent.strategy.entry_conditions] == [2_000_000]
    assert intent.strategy.backtest.contribution_period == "monthly"
    assert unsupported == ["RSI 40 아래"]


def test_plain_entries_only_still_strip_the_plan():
    from strategy_conversation.validation.capability_validator import validate_capability

    plain = {"factor": "technical.rsi", "operator": "<", "value": 40, "source_text": "RSI 40 아래"}
    intent = _rule_intent([plain])
    errors, _warnings, _unsupported, _fixes = validate_capability(intent)
    assert intent.strategy.backtest.contribution_amount is None
    assert any("정액 적립식" in e for e in errors)


def test_buy_amount_without_a_plan_is_unsupported_and_cleared():
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.capability_validator import validate_capability

    intent = StrategyIntent.model_validate({
        "schema_version": "1.0", "intent": "CREATE_STRATEGY",
        "strategy": {"entry_conditions": [_RSI_ADD]},
    })
    _errors, _warnings, unsupported, _fixes = validate_capability(intent)
    assert intent.strategy.entry_conditions[0].buy_amount is None
    assert unsupported


def test_rules_round_trip_through_decompiler_and_reach_the_engine_request():
    from engine.nl_parser import ContributionRule, ParsedStrategy, TechnicalSignal
    from engine.strategy_converter import to_backtest_request
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy

    parsed = ParsedStrategy(
        description="적립", target_symbols=["069500"],
        contribution_amount=1_000_000, contribution_period="monthly",
        contribution_rules=[ContributionRule(
            signal=TechnicalSignal(indicator="rsi", signal_type="buy", period=14, operator="<", value=30),
            amount=1_000_000, mode="add")])
    spec = decompile_strategy(parsed)
    assert [(c.factor, c.buy_amount, c.buy_amount_mode) for c in spec.entry_conditions] == [
        ("technical.rsi", 1_000_000, "add")]
    risk = to_backtest_request(parsed)["risk"]
    assert risk["contribution_rules"] == [{
        "condition": {"type": "indicator", "id": "rsi", "weight": 1.0,
                      "params": {"signalType": "buy", "period": 14, "operator": "<", "value": 30}},
        "amount": 1_000_000, "mode": "add"}]
    assert not to_backtest_request(parsed)["entry"]["conditions"]
    # 적립 일정이 없으면 규칙은 엔진에 가지 않는다
    parsed.contribution_amount = None
    assert to_backtest_request(parsed)["risk"]["contribution_rules"] is None


def test_crossing_event_cannot_be_an_amount_rule():
    """납입액 규칙은 납입일의 상태를 본다 — 교차 사건 연산자는 빼고 알린다(조용히 틀린 규칙 금지)."""
    from strategy_conversation.validation.capability_validator import validate_capability

    event = dict(_BELOW_200, operator="crosses_above")
    intent = _rule_intent([event, _RSI_ADD])
    _errors, _warnings, unsupported, _fixes = validate_capability(intent)
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.rsi"]
    assert unsupported == ["종가가 200일 이동평균선 아래에 있으면"]
    assert intent.strategy.backtest.contribution_amount == 1_000_000


# ─── 현금 풀(v16.22) — 보유 현금에서 꺼내 사는 적립 ────────────────────────────

def test_cash_pool_settings_parse_and_fail_fast():
    from engine.contributions import cash_pool_settings

    assert cash_pool_settings({}, 1_000_000) is None
    assert cash_pool_settings({"contribution_funding": "cash_pool"}, 1_000_000) == (0.0, None)
    assert cash_pool_settings(
        {"contribution_funding": "cash_pool", "cash_reserve_pct": 20, "max_buy_cash_pct": 10},
        1_000_000) == (200_000.0, 0.10)
    assert cash_pool_settings(
        {"contribution_funding": "cash_pool", "cash_reserve_amount": 300_000}, 1_000_000) == (300_000.0, None)
    for bad in ({"cash_reserve_pct": 100}, {"cash_reserve_pct": -1}, {"cash_reserve_amount": 1_000_000},
                {"max_buy_cash_pct": 0}, {"max_buy_cash_pct": 101},
                {"cash_reserve_pct": 10, "cash_reserve_amount": 100}):
        with pytest.raises(ValueError):
            cash_pool_settings({"contribution_funding": "cash_pool", **bad}, 1_000_000)


def test_cash_pool_buys_from_cash_and_respects_the_floor():
    from engine.contributions import simulate_cash_pool

    px, avail = _frames({"A": [100.0] * 5})
    mask = np.array([True, False, True, True, True])
    targets = np.full((5, 1), 400.0)
    ledger, limited = simulate_cash_pool(px, px, avail, mask, targets, 1_000.0, 200.0, None, 0.0, 0.0)
    # 1000 → 600 → 200(하한) — 세 번째 회차부터는 하한 때문에 살 돈이 없다.
    assert ledger.cash.tolist() == [600.0, 600.0, 200.0, 200.0, 200.0]
    assert ledger.shares[:, 0].tolist() == [4.0, 4.0, 8.0, 8.0, 8.0]
    assert limited == 2
    assert ledger.flows.tolist() == [1_000.0, 0.0, 0.0, 0.0, 0.0]       # 밖에서 들어온 돈은 초기 자본뿐
    assert ledger.equity.tolist() == [1_000.0] * 5                        # 가격 제자리 → 자산 불변


def test_cash_pool_caps_each_buy_at_a_share_of_current_cash():
    from engine.contributions import simulate_cash_pool

    px, avail = _frames({"A": [10.0] * 4})
    ledger, limited = simulate_cash_pool(
        px, px, avail, np.array([True] * 4), np.full((4, 1), 500.0), 1_000.0, 0.0, 0.10, 0.0, 0.0)
    # 보유 현금의 10%: 100 → 90 → 81 → 72.9(정수 주라 70)
    assert ledger.cash.tolist() == [900.0, 810.0, 730.0, 660.0]
    assert limited == 4


def test_cash_pool_scales_symbol_shares_together():
    from engine.contributions import simulate_cash_pool

    px, avail = _frames({"A": [10.0] * 2, "B": [10.0] * 2})
    targets = np.array([[300.0, 100.0], [0.0, 0.0]])
    ledger, limited = simulate_cash_pool(
        px, px, avail, np.array([True, False]), targets, 1_000.0, 800.0, None, 0.0, 0.0)
    # 요청 400, 쓸 수 있는 돈 200 → 절반으로 같이 줄인다(150·50)
    assert ledger.shares[0].tolist() == [15.0, 5.0] and limited == 1


def test_engine_runs_cash_pool_lane(flat_data_dir):
    from backtest_engine import BacktestEngine

    result = BacktestEngine(data_dir=str(flat_data_dir)).run_backtest(_dca_request(
        init_cash=2_000_000.0, contribution_funding="cash_pool", cash_reserve_pct=25))
    block = result["contributions"]
    assert block["funding"] == "cash_pool" and block["cashReserve"] == 500_000
    assert block["totalContributed"] == 2_000_000                     # 초기 자본만
    # 회차 6번(첫 봉 포함) × 50만 = 300만을 원하지만 하한 50만을 남기고 150만까지만 산다.
    assert block["investedTotal"] == pytest.approx(1_500_000)
    assert block["finalCash"] == pytest.approx(500_000)
    assert block["count"] == 3 and block["limitedRounds"] == 3
    assert result["equity"][-1] == pytest.approx(2_000_000)           # 가격 제자리
    assert result["totalReturn"] == pytest.approx(0.0)
    assert any("보유 현금에서 꺼내 사는" in w for w in result["warnings"])
    assert any("적게 매수한 회차" in w for w in result["warnings"])
    assert not any("정액 적립식 결과입니다" in w for w in result["warnings"])
    assert len(result["warnings"]) == len(result["warningParts"])


def test_request_schema_keeps_cash_pool_fields():
    from schemas import RiskManagement

    dumped = RiskManagement(position_size_pct=100, contribution_funding="cash_pool",
                            cash_reserve_pct=20, max_buy_cash_pct=10).model_dump()
    assert (dumped["contribution_funding"], dumped["cash_reserve_pct"], dumped["max_buy_cash_pct"]) == (
        "cash_pool", 20, 10)


# ─── 현금 풀 — 대화 레인(v16.22) ──────────────────────────────────────────────

_SCREENSHOT_SENTENCE = (
    "매월 첫 거래일마다 S&P500 ETF를 100만 원씩 매수합니다. 종가가 200일 이동평균선 아래에 있으면 200만 원을 "
    "매수합니다. RSI(14)가 30 미만이면 추가로 100만 원을 더 매수합니다. 단일 매수 금액은 보유 현금의 10%를 "
    "넘지 않으며, 항상 일정 수준의 현금을 유지합니다.")
_MA_QUOTE = "종가가 200일 이동평균선 아래에 있으면 200만 원을 매수합니다"
_RSI_QUOTE = "RSI(14)가 30 미만이면 추가로 100만 원을 더 매수합니다"


def _screenshot_raw(ma_condition: dict) -> str:
    import json

    return json.dumps({
        "schema_version": "1.0", "intent": "CREATE_STRATEGY",
        "strategy": {
            "universe": {"markets": ["ETF"], "etf_theme": "S&P500"},
            "entry_conditions": [
                {"factor": "fundamental.trading_value", "operator": ">=", "value": 100, "unit": "억원",
                 "source_text": "S&P500 ETF를 100만 원씩 매수합니다"},
                ma_condition,
                {"factor": "technical.rsi", "operator": "<", "value": 30, "parameters": {"period": 14},
                 "source_text": _RSI_QUOTE}],
        },
        "unsupported_features": ["단일 매수 금액은 보유 현금의 10%를 넘지 않으며",
                                 "항상 일정 수준의 현금을 유지합니다"],
    }, ensure_ascii=False)


def test_dropped_plan_turn_is_fully_interpreted(monkeypatch):
    """2026-09-21 19:47 트레이스 재현(120B, 같은 문장 13회 중 1회): 1차 해석이 적립 계획을 비우고 금액
    표현 둘을 거래대금 조건으로 지어냈다 → 적립 전용 판정이 전부 건너뛰어 "일평균거래대금으로 가깝게
    반영"·현금 풀 미지원 두 줄이 나갔다. 재생성(지표 어긋남)·계획 회수·상태 연산자가 이어 받아 계획·규칙
    둘·현금 풀이 모두 해석되고, 남는 안내는 값 확인 전인 현금 하한 하나다."""
    import llm_backend
    from strategy_conversation import primary
    from strategy_conversation.interpreter import condition_recall, contribution_plan_check, quote_check
    from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter

    replies = {
        condition_recall.build_system_prompt():
            '{"phrases": ["종가가 200일 이동평균선 아래에 있으면", "RSI(14)가 30 미만이면"]}',
        condition_recall.build_period_system_prompt(): '{"quote": null, "period": null}',
        quote_check.build_system_prompt(): '{"items": [{"expresses": "no", "describes": "moving_average"}]}',
        contribution_plan_check.build_system_prompt(): _PLAN_REPLY.replace(
            '"quote": "종가가 200일 이동평균선 아래에 있으면"', f'"quote": "{_MA_QUOTE}"').replace(
            '"quote": "RSI(14)가 30 미만이면"', f'"quote": "{_RSI_QUOTE}"'),
    }
    main_calls: list = []

    def chat(system, user, **_kw):
        if system in replies:
            return replies[system]
        main_calls.append(user)
        if len(main_calls) == 1:
            return _screenshot_raw({"factor": "fundamental.trading_value", "operator": ">=", "value": 200,
                                    "unit": "억원", "source_text": _MA_QUOTE})
        return _screenshot_raw({"factor": "technical.ma_crossover", "operator": "crosses_below",
                                "parameters": {"short_period": 1, "long_period": 200},
                                "source_text": _MA_QUOTE})

    monkeypatch.setattr(llm_backend, "is_openrouter", lambda: False)
    monkeypatch.setenv("STRATEGY_CONDITION_RECALL", "on")
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "off")
    monkeypatch.setattr(primary, "_interpreter_singleton", StrategyInterpreter(chat_fn=chat, model="stub"))

    result = primary.run_primary_parse(_SCREENSHOT_SENTENCE)

    assert len(main_calls) == 2                                           # 지표 어긋남 재생성 1회
    parsed = result["parsed"]
    assert (parsed.contribution_amount, parsed.contribution_period) == (1_000_000, "monthly")
    rules = {r.signal.indicator: r for r in parsed.contribution_rules}
    assert (rules["ma_crossover"].amount, rules["ma_crossover"].mode) == (2_000_000, "set")
    assert (rules["ma_crossover"].signal.long_period, rules["ma_crossover"].signal.mode) == (200, "below")
    assert (rules["rsi"].amount, rules["rsi"].mode) == (1_000_000, "add")
    assert parsed.fundamental_filters == [] and parsed.entry_signals == []
    assert parsed.cash_pool is not None and parsed.cash_pool.max_buy_pct == 10
    # 'S&P500 ETF'는 유니버스다 — 종목을 되묻지 않고 현금 하한이 첫 질문이 된다(2026-09-22).
    assert result["clarification_question"].startswith("현금을 얼마나 남겨 둘까요")
    assert result["notices"] == []


def test_pending_value_notice_quotes_the_users_words_not_the_label(monkeypatch):
    """2026-09-22 사용자 보고: "'현금 하한' 조건은 값 확인 전까지…"가 나갔는데 사용자 문장에 '현금 하한'이란
    말이 없다 — 라벨은 내부 표기다. 큐에 실리지 않은 값 대기 항목은 사용자가 한 말(source_text)로 알린다."""
    from strategy_conversation import primary

    dropped = ["현금 하한", "PER"]
    pending = [{"role": "entry", "label": "현금 하한", "source_text": "항상 일정 수준의 현금을 유지합니다"},
               {"role": "entry", "label": "PER", "source_text": None}]
    notices = primary.pending_value_notices(dropped, pending, clarification_question=None, pending_ask=None,
                                            notices=[])
    assert notices == ["'항상 일정 수준의 현금을 유지합니다, PER' 조건은 값 확인 전까지 전략에 반영되지 않았어요."]
    # 큐의 칩 문구가 라벨을 담으면 '다음 턴에 물을 예정'이라 안내하지 않는다
    queued = {"question": "x", "queue": [{"question": "현금을 얼마나 남겨 둘까요?", "chips": ["현금 하한 초기 자본의 10%"]}]}
    assert primary.pending_value_notices(["현금 하한"], pending[:1], clarification_question=None,
                                         pending_ask=queued, notices=[]) == []
    # 지금 질문의 칩도 같다
    assert primary.pending_value_notices(["현금 하한"], pending[:1], clarification_question="현금을 얼마나 남겨 둘까요?",
                                         clarification_suggestions=["현금 하한 초기 자본의 10%"],
                                         pending_ask=None, notices=[]) == []


def test_reserve_level_is_asked_with_chips_and_held_back_from_the_engine():
    from engine import strategy_slots
    from engine.strategy_converter import to_backtest_request
    from strategy_conversation.compiler.strategy_compiler import CASH_RESERVE_LABEL, compile_partial
    from strategy_conversation.validation.pipeline import run_validation

    intent = _rule_intent([_BELOW_200], cash_pool={"reserve_stated": True, "max_buy_pct": 10,
                                                   "source_texts": ["항상 일정 수준의 현금을 유지합니다"]})
    intent, report = run_validation(intent)
    fields = [q.field for q in report.clarification_questions]
    assert "strategy.backtest.cash_pool.reserve_pct" in fields
    parsed, dropped, pending = compile_partial(intent, report, "적립")
    assert CASH_RESERVE_LABEL in dropped and pending[-1]["source_text"] == "항상 일정 수준의 현금을 유지합니다"
    assert parsed.cash_pool is not None and not parsed.cash_pool.is_complete()
    parsed.target_symbols = ["069500"]
    risk = to_backtest_request(parsed)["risk"]
    assert "contribution_funding" not in risk                            # 되묻는 중에는 엔진에 싣지 않는다

    # 칩 답 = 정본 표의 값 결속
    patch = strategy_slots.portfolio_chip_patch("현금 하한 초기 자본의 20%", parsed.model_dump())
    assert patch["cash_pool"]["reserve_pct"] == 20.0
    answered = parsed.model_copy(update={"cash_pool": parsed.cash_pool.model_copy(update={"reserve_pct": 20.0})})
    risk = to_backtest_request(answered)["risk"]
    assert (risk["contribution_funding"], risk["cash_reserve_pct"], risk["max_buy_cash_pct"]) == ("cash_pool", 20.0, 10.0)
    assert strategy_slots.portfolio_chip_patch("현금 하한 초기 자본의 20%", {"cash_pool": None}) is None


def test_cash_pool_without_a_plan_is_removed_with_the_users_words():
    from strategy_conversation.validation.capability_validator import validate_capability

    plain = {"factor": "technical.rsi", "operator": "<", "value": 40, "source_text": "RSI 40 아래"}
    intent = _rule_intent([plain], cash_pool={"reserve_pct": 20, "reserve_stated": True,
                                              "source_texts": ["현금 20%는 유지"]})
    _errors, _warnings, unsupported, _fixes = validate_capability(intent)
    assert intent.strategy.backtest.cash_pool is None and "현금 20%는 유지" in unsupported


def test_cash_pool_round_trips_through_the_decompiler():
    from engine.nl_parser import CashPool, ParsedStrategy
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy

    parsed = ParsedStrategy(description="적립", target_symbols=["069500"], contribution_amount=1_000_000,
                            contribution_period="monthly",
                            cash_pool=CashPool(reserve_pct=20, reserve_stated=True, max_buy_pct=10))
    pool = decompile_strategy(parsed).backtest.cash_pool
    assert (pool.reserve_pct, pool.reserve_stated, pool.max_buy_pct) == (20, True, 10)


def test_modify_draft_hides_the_cash_pool_but_patches_keep_it():
    """수정 LLM에게는 현금 풀을 보여 주지 않는다 — 초안에 실리자 되묻기 답의 귀속이 흔들렸다
    (2026-09-21 실측). 패치는 원본 초안에 적용되므로 가린 칸은 손실 없이 이월된다."""
    from strategy_conversation.conversation.patch_applier import apply_patches
    from strategy_conversation.interpreter.models import PatchOp
    from strategy_conversation.primary import _draft_for_interpreter

    spec = _rule_intent([_BELOW_200], cash_pool={"reserve_stated": True, "max_buy_pct": 10}).strategy
    assert "cash_pool" not in _draft_for_interpreter(spec)["backtest"]
    assert spec.backtest.cash_pool is not None                          # 원본은 그대로
    patched = apply_patches(spec, [PatchOp(op="replace", path="/universe/symbols", value=["KODEX 200"])])
    assert patched.backtest.cash_pool.max_buy_pct == 10
    answered = apply_patches(spec, [PatchOp(op="replace", path="/backtest/cash_pool/reserve_pct", value=20)])
    assert answered.backtest.cash_pool.reserve_pct == 20 and answered.backtest.cash_pool.is_complete()


def test_answer_passes_transcribe_and_fail_open():
    from strategy_conversation.interpreter import cash_pool_check as cpc
    from strategy_conversation.interpreter import contribution_amount_check as cac

    assert cpc.check_reserve_answer("20%로", _amount_chat('{"percent": 20, "amount": null}')) == {"reserve_pct": 20}
    assert cpc.check_reserve_answer("300만원", _amount_chat('{"percent": null, "amount": "300만원"}')) == {
        "reserve_amount": 3_000_000}
    assert cpc.check_reserve_answer("글쎄", _amount_chat('{"percent": null, "amount": null}')) == {}
    assert cpc.check_reserve_answer("x", _amount_chat("not json")) is None
    assert cac.check_symbol_answer("TIGER 미국S&P500으로", _amount_chat('{"symbols": ["TIGER 미국S&P500"]}')) == [
        "TIGER 미국S&P500"]
    assert cac.check_symbol_answer("x", _amount_chat('{"symbols": "TIGER"}')) is None


def test_answer_routing_is_keyed_on_our_own_question_text(monkeypatch):
    """'이 질문의 답인가'는 우리가 낸 질문 문장의 동일성으로만 판정한다 — 다른 질문이면 일반 레인."""
    from strategy_conversation import primary
    from strategy_conversation.validation.completeness_validator import (
        CASH_RESERVE_QUESTION,
        CONTRIBUTION_SYMBOL_QUESTION,
    )

    class _Interp:
        model_name = "stub"

        def _chat(self, system, _user, **_kw):
            return '{"percent": 20, "amount": null}' if "현금" in system else '{"symbols": ["KODEX 200"]}'

    monkeypatch.setattr(primary, "_get_interpreter", lambda _cls: _Interp())
    spec = _rule_intent([_BELOW_200], cash_pool={"reserve_stated": True}).strategy
    spec.universe.symbols = []
    reserve = primary._cash_reserve_answer_result(spec, "20%로 해줘", CASH_RESERVE_QUESTION[0])
    assert [(p.path, p.value) for p in reserve.intent.patches] == [("/backtest/cash_pool/reserve_pct", 20)]
    assert primary._cash_reserve_answer_result(spec, "20%로 해줘", "손절 기준을 몇 %로 할까요?") is None
    symbol = primary._contribution_symbol_answer_result(spec, "KODEX 200", CONTRIBUTION_SYMBOL_QUESTION[0])
    assert [(p.path, p.value) for p in symbol.intent.patches] == [("/universe/symbols", ["KODEX 200"])]
    assert primary._contribution_symbol_answer_result(spec, "KODEX 200", "최대 몇 종목?") is None
