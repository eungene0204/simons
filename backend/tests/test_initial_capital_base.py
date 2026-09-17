"""수익률·낙폭 지표의 기준 = 초기자본(엔진 v16.12).

창 첫날 체결(v16.12)로 자산곡선의 첫 값(첫 거래일 종가 평가액)이 초기자본과 달라졌는데,
프론트 매퍼 4곳이 `initialCapital = equity[0]`로 채워 카드·로그의 초기자금·총수익·ROI가 첫날
손익을 뺀 값으로 나갔다(2026-09-17 실측: 초기자금 9,748,557원·ROI +42.11%, 실제 +38.54%).
결과에 초기자본이 없었고, 엔진 안에서도 최대낙폭(vbt max_drawdown)·낙폭 기간·분위/리밸런싱 비교표의
낙폭·샤프·워크포워드 연결 곡선·몬테카를로가 자산곡선 첫 값을 출발점으로 썼다.
"""

import os

import numpy as np
import pandas as pd
import polars as pl
import pytest

pytest.importorskip("vectorbt")
pytest.importorskip("stockstats")

from backtest_engine import BacktestEngine  # noqa: E402
from engine.monte_carlo import MonteCarloSimulator  # noqa: E402
from engine.result_handler import ResultHandler  # noqa: E402
from engine.walk_forward import WalkForwardAnalyzer  # noqa: E402

_START = "2023-10-02"
_INIT = 10_000_000


def _data_dir() -> str:
    d = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(d, exist_ok=True)
    return d


def _write_gap_down(symbol: str) -> None:
    """창 직전까지 상승(순위 1위) → 창 첫날 시가 100 → 종가 90(-10%) → 이후 완만히 상승."""
    dates = pd.bdate_range("2023-06-01", "2023-12-29")
    rows = []
    for d in dates:
        day = d.strftime("%Y-%m-%d")
        if day < _START:
            c = 50.0 + 0.2 * len(rows)
            o = c
        elif day == _START:
            o, c = 100.0, 90.0
        else:
            k = len([r for r in rows if r["date"] >= _START])
            o = c = 90.0 * (1.001 ** k)
        rows.append({"date": day, "open": o, "high": max(o, c) * 1.001, "low": min(o, c) * 0.999,
                     "close": c, "volume": 50_000_000.0})
    pl.from_dicts(rows).write_parquet(f"{_data_dir()}/{symbol}.parquet")


def _write_flat(symbol: str) -> None:
    dates = pd.bdate_range("2023-06-01", "2023-12-29")
    rows = [{"date": d.strftime("%Y-%m-%d"), "open": 100.0, "high": 100.1, "low": 99.9,
             "close": 100.0, "volume": 50_000_000.0} for d in dates]
    pl.from_dicts(rows).write_parquet(f"{_data_dir()}/{symbol}.parquet")


def _run_day1_invested():
    _write_gap_down("ICB_GAP")
    _write_flat("ICB_FLAT")
    return BacktestEngine(data_dir=_data_dir()).run_backtest({
        "symbols": ["ICB_GAP", "ICB_FLAT"],
        "entry": {"conditions": []}, "exit": {"conditions": []},
        "risk": {"init_cash": _INIT, "max_positions": 1, "position_size_pct": 100,
                 "ranking_metric": "return", "ranking_lookback_days": 20,
                 "rebalancing_period": "quarterly", "liquidity_limit_pct": 0},
        "options": {"execution_type": "next_open", "fee_rate": 0.00015, "slippage_rate": 0.0005},
        "startDate": _START, "endDate": "2023-12-29",
    })


def test_day1_invested_metrics_use_initial_capital():
    r = _run_day1_invested()
    assert not r.get("error"), r.get("error")
    buys = [s for s in r["signals"] if s["type"] == "buy"]
    assert buys and buys[0]["date"] == _START, buys        # 첫날 시가 체결 → 첫 평가액 ≈ 90%
    eq = r["equity"]
    assert eq[0] < _INIT * 0.92

    assert r["initialCapital"] == _INIT
    assert r["totalReturn"] == pytest.approx((eq[-1] / _INIT - 1) * 100, abs=1e-6)
    assert r["totalProfit"] == pytest.approx(eq[-1] - _INIT, abs=1e-3)
    # 최대낙폭은 초기자본을 출발 고점으로 본다 — 첫날 -10% 갭이 빠지면 안 된다.
    expected_mdd = ResultHandler.max_drawdown_pct(eq, _INIT)
    assert expected_mdd <= (eq[0] / _INIT - 1) * 100 + 1e-9
    assert r["maxDrawdown"] == pytest.approx(expected_mdd)
    assert r["maxDrawdown"] < -9.0
    # 연환산도 초기자본 기준 총수익에서 나온다.
    years, _ = ResultHandler.time_base(pd.DatetimeIndex(r["dates"]))
    assert r["cagr"] == pytest.approx(ResultHandler.annualize_return(r["totalReturn"] / 100, years))


def test_anchored_helpers_equal_legacy_when_first_day_is_cash():
    eq = [_INIT, 10_200_000, 9_800_000, 10_500_000]
    legacy = (np.asarray(eq) / np.maximum.accumulate(eq) - 1).min() * 100
    assert ResultHandler.max_drawdown_pct(eq, _INIT) == pytest.approx(legacy)
    rets = ResultHandler.anchored_returns(eq, _INIT)
    assert rets[0] == 0.0 and len(rets) == len(eq)
    # 첫날 체결로 첫 값이 낮으면 그 하락이 낙폭·수익률에 들어간다.
    eq2 = [9_000_000, 9_900_000, 10_100_000]
    assert ResultHandler.max_drawdown_pct(eq2, _INIT) == pytest.approx(-10.0)
    assert ResultHandler.anchored_returns(eq2, _INIT)[0] == pytest.approx(-0.1)


def test_walk_forward_chain_uses_window_initial_capital():
    windows = [
        {"oos_equity": [9_000_000, 9_900_000], "oos_dates": ["2024-01-02", "2024-01-03"],
         "oos_initial_capital": _INIT},
        {"oos_equity": [10_000_000, 11_000_000], "oos_dates": ["2024-02-01", "2024-02-02"],
         "oos_initial_capital": _INIT},
    ]
    combined, dates = WalkForwardAnalyzer._combine_equity(object.__new__(WalkForwardAnalyzer), windows)
    # 첫 창의 첫날 -10%가 연결 곡선에 남는다(첫 값으로 나누면 1.0에서 출발해 사라졌다).
    assert combined[0] == pytest.approx(0.9)
    assert combined[-1] == pytest.approx(0.99 * 1.1, abs=0.01)   # 연결 곡선은 소수 2자리 반올림
    assert dates == ["2024-01-02", "2024-01-03", "2024-02-01", "2024-02-02"]


def test_monte_carlo_includes_first_day_return_from_initial_capital():
    eq = list(9_000_000 * np.cumprod(np.full(90, 1.001)))
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-02", periods=90)]
    with_init = MonteCarloSimulator().run({"equity": eq, "dates": dates, "initialCapital": _INIT},
                                          n_iterations=400, seed=1)
    without = MonteCarloSimulator().run({"equity": eq, "dates": dates}, n_iterations=400, seed=1)
    assert with_init["status"] == without["status"] == "ok"
    # 첫 값 기준이면 모든 경로가 같은 일정 수익률(표본에 첫날 -10%가 없다). 초기자본 기준이면
    # 첫날 -10%가 표본에 들어가 평균 CAGR이 낮아진다.
    assert with_init["cagr"]["mean"] < without["cagr"]["mean"] - 0.005
    # 첫 값 = 초기자본(첫날 현금)이면 종전과 같은 표본이다.
    same = MonteCarloSimulator().run({"equity": [_INIT] + eq[1:], "dates": dates, "initialCapital": _INIT},
                                     n_iterations=50, seed=3)
    legacy = MonteCarloSimulator().run({"equity": [_INIT] + eq[1:], "dates": dates}, n_iterations=50, seed=3)
    assert same["cagr"] == legacy["cagr"]


def test_benchmark_first_day_return_measured_from_previous_close():
    """벤치마크도 전략과 같은 출발점(첫 거래일 시가 전)에 맞춘다 — 첫날 수익률 = 첫날 종가 ÷ 창 직전 종가."""
    idx = pd.bdate_range("2024-01-02", periods=3)
    # 창 직전 종가 100(12/29) → 창 첫날 110 → 121. 첫날 수익률 +10%가 빠지면 총수익이 10%로 나온다.
    bench = pd.Series([100.0, 110.0, 121.0, 121.0],
                      index=pd.DatetimeIndex(["2023-12-29", "2024-01-02", "2024-01-03", "2024-01-04"]))
    import vectorbt as vbt
    close = pd.DataFrame({"A": [100.0, 100.0, 100.0]}, index=idx)
    pf = vbt.Portfolio.from_orders(close=close, size=pd.DataFrame({"A": [np.nan] * 3}, index=idx),
                                   init_cash=_INIT, cash_sharing=True, group_by=True, freq="D")
    out = ResultHandler.format_results(pf, ["A"], {}, {}, {}, {}, idx, {}, "next_open", _INIT,
                                       benchmark_prices=bench)
    assert out["benchmark_equity"][0] == pytest.approx(_INIT * 1.1)
    assert out["buyAndHoldReturn"] == pytest.approx(21.0)
