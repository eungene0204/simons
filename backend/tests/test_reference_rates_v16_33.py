"""엔진 v16.33 회귀 — 무위험수익률·물가·배당세·비교 지수·정기 인출·스크리너.

이 묶음이 지키는 계약:
  · 샤프의 기준 금리는 0이 아니라 창 기간 단기금리 평균이고, 요청이 말하면 그 값이 이긴다.
  · 물가 자료가 창 끝까지 닿지 않으면 ffill로 늘리지 않고 닿은 구간과 그 사실을 함께 싣는다.
  · 배당 재투자는 세후 배당으로 굴린다(0이면 종전과 바이트 동일).
  · 정기 인출은 현금 → 보유 평가액 비례 매도 순으로 마련하고, 모자라면 만들 수 있는 만큼만 낸다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import macro_data
from engine.contributions import (
    money_weighted_return,
    simulate_contributions,
    withdrawal_flows,
    withdrawal_settings,
)


# ── 무위험수익률·물가 ────────────────────────────────────────────────────────

def _write_series(tmp_path, series_id: str, dates, values) -> str:
    """data/ohlcv 형제 디렉터리(data/macro)에 시리즈 parquet을 쓴다 — 로더와 같은 경로 규약."""
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir(exist_ok=True)
    macro_dir = tmp_path / "macro"
    macro_dir.mkdir(exist_ok=True)
    pd.DataFrame({"date": pd.to_datetime(dates), "value": values}).to_parquet(
        macro_dir / f"{series_id}.parquet", index=False)
    return str(data_dir)


def test_average_short_rate_uses_window_mean(tmp_path):
    index = pd.bdate_range("2020-01-01", "2020-12-31")
    data_dir = _write_series(tmp_path, "kr3m", ["2019-12-31", "2020-06-30"], [1.0, 3.0])
    out = macro_data.average_short_rate("kr", index, data_dir)
    assert out is not None
    # 상반기 1%, 하반기 3% → 창 평균은 그 사이. 소수(연 수익률)로 돌려준다.
    assert 0.01 < out["rate"] < 0.03
    assert out["series"] == "kr3m"


def test_average_short_rate_missing_file_is_none(tmp_path):
    data_dir = _write_series(tmp_path, "us3m", ["2020-01-01"], [1.0])
    assert macro_data.average_short_rate("kr", pd.bdate_range("2020-01-01", "2020-02-01"), data_dir) is None


def test_inflation_does_not_extend_past_last_observation(tmp_path):
    """물가 자료가 창 끝보다 이르면 ffill한 꼬리로 기간을 늘리지 않는다(과대 환산 금지)."""
    index = pd.bdate_range("2020-01-01", "2024-12-31")
    data_dir = _write_series(tmp_path, "kr_cpi", ["2019-12-31", "2021-12-31"], [100.0, 110.0])
    out = macro_data.inflation_over_window("kr", index, data_dir)
    assert out is not None
    assert out["to"] == "2021-12-31"          # 마지막 실측 관측일
    assert out["windowTo"] == "2024-12-31"    # 창 끝은 따로 싣는다
    assert out["covered"] is False
    assert out["total"] == pytest.approx(0.10)


def test_inflation_none_when_single_observation(tmp_path):
    index = pd.bdate_range("2020-01-01", "2020-12-31")
    data_dir = _write_series(tmp_path, "kr_cpi", ["2019-12-31"], [100.0])
    assert macro_data.inflation_over_window("kr", index, data_dir) is None


def test_cpi_is_not_a_condition_filter_series():
    """CPI는 공표가 늦어 매매 조건(매크로 필터)으로 쓰면 미래 참조다 — 필터 목록에 없어야 한다."""
    assert "kr_cpi" not in macro_data.MACRO_SERIES
    assert "us_cpi" not in macro_data.MACRO_SERIES
    assert "kr_cpi" in macro_data.ALL_SERIES and "us_cpi" in macro_data.ALL_SERIES


# ── 배당세·비교 지수 해석 ────────────────────────────────────────────────────

def test_dividend_tax_defaults_by_region_and_override():
    from backtest_engine import BacktestEngine

    assert BacktestEngine.resolve_dividend_tax_rate({}, "kr", True) == pytest.approx(0.154)
    assert BacktestEngine.resolve_dividend_tax_rate({}, "us", True) == pytest.approx(0.15)
    # 배당 미반영이면 세금도 없다(가격 패널이 바뀌지 않는다).
    assert BacktestEngine.resolve_dividend_tax_rate({}, "kr", False) == 0.0
    # 명시값이 이긴다 — 0이면 종전 동작(세전 재투자).
    assert BacktestEngine.resolve_dividend_tax_rate({"dividend_tax_rate": 0}, "kr", True) == 0.0
    assert BacktestEngine.resolve_dividend_tax_rate({"dividend_tax_rate": 0.2}, "kr", True) == pytest.approx(0.2)


def test_dividend_tax_rate_reaches_prep_cache_key():
    """세율은 가격 패널을 바꾼다 — 캐시 키에 들어가지 않으면 다른 세율 결과가 섞인다."""
    from engine import phase1

    base = dict(entry=None, exit_=None, warmup_start_str=None, has_period_filter=False,
                period_start_str=None, end_str="2024-01-01", apply_dividends=True,
                skip_risk=False, skip_pos=False, init_cash=1.0, pos_size_pct=10.0,
                liquid_limit=10.0, exec_type="next_open", delisted_symbols=set(),
                rank_metric_cols=[], tracked_metrics=None, ai_needed=False)
    ctx_a = phase1.build_context(**base, dividend_tax_rate=0.0)
    ctx_b = phase1.build_context(**base, dividend_tax_rate=0.154)
    assert phase1.prep_cache_key("005930", ctx_a) != phase1.prep_cache_key("005930", ctx_b)


def test_net_dividend_lowers_total_return_adjustment():
    from engine.dividends import dividend_adjust_factor

    close = pd.Series([100.0, 100.0, 100.0], index=pd.bdate_range("2024-01-01", periods=3))
    gross = pd.Series([0.0, 10.0, 0.0], index=close.index)
    net = gross * (1.0 - 0.154)
    # 토탈리턴 지수는 첫 봉에 맞춰 리베이스된다 — 배당이 적을수록 이후 배수가 작다(성과가 낮다).
    assert dividend_adjust_factor(close, net).iloc[-1] < dividend_adjust_factor(close, gross).iloc[-1]


@pytest.mark.parametrize("value,expected_symbol", [
    ("kosdaq", "229200"), ("KOSPI200", "069500"), ("s p500", "SPY"),
    ("069500", "069500"), ("SPY", "SPY"),
])
def test_benchmark_choice_normalizes(value, expected_symbol):
    from backtest_engine import BacktestEngine

    resolved = BacktestEngine.resolve_benchmark_choice(value)
    assert resolved is not None and resolved[0] == expected_symbol


def test_benchmark_choice_unknown_is_none():
    from backtest_engine import BacktestEngine

    assert BacktestEngine.resolve_benchmark_choice("코스닥 지수와 비교") is None
    assert BacktestEngine.resolve_benchmark_choice(None) is None


# ── 정기 인출 ────────────────────────────────────────────────────────────────

def test_withdrawal_settings_requires_both_fields():
    assert withdrawal_settings({}) is None
    assert withdrawal_settings({"withdrawal_amount": 1000, "withdrawal_period": "monthly"}) == (1000.0, "monthly")
    with pytest.raises(ValueError):
        withdrawal_settings({"withdrawal_amount": 1000})
    with pytest.raises(ValueError):
        withdrawal_settings({"withdrawal_amount": 0, "withdrawal_period": "monthly"})


def test_withdrawal_flows_skip_first_bar():
    index = pd.bdate_range("2024-01-01", periods=70)
    flows = withdrawal_flows(index, 100.0, "monthly")
    assert flows[0] == 0.0          # 넣자마자 빼지 않는다
    assert flows.sum() > 0


def _frames(prices):
    index = pd.bdate_range("2024-01-01", periods=len(prices))
    price_df = pd.DataFrame({"A": prices}, index=index)
    return price_df, price_df.copy(), pd.DataFrame({"A": [True] * len(prices)}, index=index)


def test_withdrawal_sells_holdings_and_records_orders():
    price_df, exec_df, avail = _frames([100.0] * 10)
    flows = np.zeros(10)
    flows[0] = 10_000.0
    withdrawals = np.zeros(10)
    withdrawals[5] = 3_000.0
    ledger = simulate_contributions(price_df, exec_df, avail, flows, 0.0, 0.0,
                                    withdrawals=withdrawals, sell_fee_rate=0.0,
                                    sell_tax=np.zeros(10))
    sells = [o for o in ledger.orders if o.get("side") == "sell"]
    assert len(sells) == 1 and sells[0]["quantity"] == 30
    assert ledger.withdrawn_total == pytest.approx(3_000.0)
    assert ledger.shortfall_rounds == 0
    # 인출은 밖으로 나간 돈이라 흐름에 음수로 실린다 — 총 납입액은 넣은 돈만 센다.
    assert ledger.flows[5] == pytest.approx(-3_000.0)
    assert ledger.total_contributed == pytest.approx(10_000.0)


def test_withdrawal_shortfall_is_counted_not_borrowed():
    price_df, exec_df, avail = _frames([100.0] * 6)
    flows = np.zeros(6)
    flows[0] = 1_000.0
    withdrawals = np.zeros(6)
    withdrawals[3] = 5_000.0     # 보유를 다 팔아도 모자라다
    ledger = simulate_contributions(price_df, exec_df, avail, flows, 0.0, 0.0,
                                    withdrawals=withdrawals, sell_fee_rate=0.0,
                                    sell_tax=np.zeros(6))
    assert ledger.shortfall_rounds == 1
    assert ledger.withdrawn_total <= 1_000.0
    assert (np.asarray(ledger.cash) >= -1e-9).all()   # 빚을 내지 않는다


def test_withdrawal_covers_from_other_holdings_when_proportional_share_is_capped():
    """비례 몫이 한 종목의 보유 한도에 걸려도, 팔 것이 남아 있으면 부족 회차로 세지 않는다."""
    index = pd.bdate_range("2024-01-01", periods=6)
    price_df = pd.DataFrame({"A": [100.0] * 6, "B": [100.0] * 6}, index=index)
    avail = pd.DataFrame({"A": [True] * 6, "B": [True] * 6}, index=index)
    flows = np.zeros(6)
    flows[0] = 10_000.0                       # A·B에 5,000원씩 = 각 50주
    withdrawals = np.zeros(6)
    withdrawals[3] = 9_000.0                  # 비례 몫 4,500원씩이면 둘 다 가능하지만 경계 확인
    ledger = simulate_contributions(price_df, price_df.copy(), avail, flows, 0.0, 0.0,
                                    withdrawals=withdrawals, sell_fee_rate=0.0,
                                    sell_tax=np.zeros(6))
    assert ledger.shortfall_rounds == 0
    assert ledger.withdrawn_total == pytest.approx(9_000.0)


def test_withdrawal_none_keeps_previous_behaviour():
    price_df, exec_df, avail = _frames([100.0] * 8)
    flows = np.zeros(8)
    flows[0] = 1_000.0
    a = simulate_contributions(price_df, exec_df, avail, flows, 0.0, 0.0)
    b = simulate_contributions(price_df, exec_df, avail, flows, 0.0, 0.0, withdrawals=np.zeros(8))
    assert np.array_equal(a.equity, b.equity)
    assert [o["symbol"] for o in a.orders] == [o["symbol"] for o in b.orders]


def test_money_weighted_return_counts_withdrawals_as_inflow():
    index = pd.bdate_range("2020-01-01", periods=522)   # 약 2년
    flows = np.zeros(len(index))
    flows[0] = 1_000.0
    flows[-1] = -1_100.0         # 마지막에 전액 인출
    rate = money_weighted_return(index, flows, 0.0)
    assert rate is not None and rate > 0


# ── 스크리너 ─────────────────────────────────────────────────────────────────

def test_screener_reports_missing_buy_criteria():
    from engine.screener import run_screen

    out = run_screen(object(), {"entry": {"conditions": []}, "risk": {}})
    assert out["reason"] == "no_buy_criteria"
    assert out["rows"] == [] and out["matched"] == 0


def test_screener_reports_empty_universe(monkeypatch):
    from engine import screener

    monkeypatch.setattr(screener, "resolve_live_universe", lambda *_args, **_kw: [])
    out = screener.run_screen(object(), {
        "entry": {"conditions": [{"id": "rsi", "params": {"period": 14}}]}, "risk": {}})
    assert out["reason"] == "empty_universe"


def test_screener_sorts_by_fundamental_rank(monkeypatch):
    """재무 팩터 랭킹은 최신 행의 지표 값으로 정렬한다(값 없는 종목은 뒤로, 0으로 위장하지 않는다)."""
    from engine import screener

    monkeypatch.setattr(screener, "resolve_live_universe", lambda *_a, **_k: ["A", "B", "C"])
    monkeypatch.setattr(screener, "evaluate_live_strategy_signals",
                        lambda *_a, **_k: [{"symbol": s, "entry_signal": True, "entry_reason": None,
                                            "ranking_return": None} for s in ("A", "B", "C")])
    values = {"A": 5.0, "B": 20.0, "C": None}
    monkeypatch.setattr(screener, "_enrich",
                        lambda _loader, sym, _col: {"close": 1.0, "changePct": 0.0,
                                                    "tradingValue": 1.0, "date": "2026-09-22",
                                                    "rankValue": values[sym]})
    monkeypatch.setattr(screener, "_display_name", lambda sym: sym)
    monkeypatch.setattr(screener, "_sector", lambda sym: "-")
    out = screener.run_screen(object(), {
        "entry": {"conditions": [{"id": "rsi", "params": {"period": 14}}]},
        "risk": {"ranking_metric": "roe", "ranking_direction": "top"}})
    assert [row["symbol"] for row in out["rows"]] == ["B", "A", "C"]


def test_new_result_fields_survive_response_model():
    """응답 모델에 없는 키는 조용히 사라진다 — 기준값·인출 블록이 HTTP 응답에서 빠지지 않는지."""
    from schemas import BacktestResponse

    for key in ("riskFreeRate", "inflation", "withdrawals"):
        assert key in BacktestResponse.model_fields, key
    dumped = BacktestResponse(
        symbols=["069500"], totalReturn=1.0, cagr=1.0, buyAndHoldReturn=1.0, maxDrawdown=-1.0,
        winRate=50.0, sharpe=0.5, sortino=0.5, volatility=10.0,
        trades=1, signals=[], equity=[1.0], dates=["2024-01-01"],
        riskFreeRate={"annualPct": 3.0, "source": "market", "series": "kr3m"},
        inflation={"totalPct": 10.0, "annualPct": 2.0, "covered": False},
        withdrawals={"period": "monthly", "amount": 1.0, "count": 2,
                     "totalWithdrawn": 2.0, "shortfallRounds": 0},
    ).model_dump()
    assert dumped["riskFreeRate"]["series"] == "kr3m"
    assert dumped["inflation"]["covered"] is False
    assert dumped["withdrawals"]["count"] == 2
