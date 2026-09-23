"""엔진 v16.30 — 결과 심화 분석(귀인·팩터 노출·거래 분포·MAE/MFE·VaR·롤링·턴오버·유동성·다중 벤치마크)과
견고성 도구(롤링 시작일·거래비용 스윕) 회귀. 값은 과거 통계이며 체결·자산곡선을 바꾸지 않는다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import result_analytics as ra
from engine.robustness import cost_sweep, rolling_start
from engine.simulator import Simulator

_OPTS = {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0, "sell_tax_rate": 0}
_CASH = 10_000_000.0


def _pf(n=80):
    idx = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.default_rng(3)
    a = 100 * np.cumprod(1 + rng.normal(0.001, 0.01, n))
    b = 100 * np.cumprod(1 + rng.normal(-0.0005, 0.012, n))
    px = pd.DataFrame({"A": a, "B": b}, index=idx)
    ents = pd.DataFrame(False, index=idx, columns=["A", "B"])
    ents.iloc[0] = True
    exts = pd.DataFrame(False, index=idx, columns=["A", "B"])
    exts.iloc[40] = True
    ents.iloc[45] = True
    risk = {"max_positions": 2, "init_cash": _CASH, "entry_signal_driven": True}
    pf = Simulator().run(px, px, ents, exts, risk, _OPTS, high_df=px * 1.01, low_df=px * 0.99)
    return pf, px, idx


def test_trade_distribution_and_mae_mfe_bounds():
    pf, px, _ = _pf()
    td = ra.trade_distribution(pf, (px * 1.01).values, (px * 0.99).values)
    assert td["trades"] >= 2
    assert sum(b["count"] for b in td["returnHistogram"]) == td["trades"]
    assert sum(b["count"] for b in td["holdingHistogram"]) == td["trades"]
    assert td["mae"]["all"]["worst"] <= 0.0 <= td["mfe"]["all"]["best"]
    assert all(len(p) == 3 for p in td["points"])


def test_attribution_sums_to_total_and_orders_by_magnitude():
    pf, _, _ = _pf()
    att = ra.attribution(pf, ["A", "B"], _CASH)
    assert att["symbolCount"] == 2
    assert att["total"] == pytest.approx(sum(r["pnl"] for r in att["symbols"]), rel=1e-6)
    assert abs(att["symbols"][0]["pnl"]) >= abs(att["symbols"][1]["pnl"])
    assert att["symbols"][0]["contributionPct"] == pytest.approx(att["symbols"][0]["pnl"] / _CASH * 100, rel=1e-6)


def test_risk_stats_var_cvar_and_rolling_series():
    rng = np.random.default_rng(0)
    rets = rng.normal(0.0, 0.01, 300)
    idx = pd.bdate_range("2023-01-02", periods=300)
    bench = pd.Series(rets * 0.5 + rng.normal(0, 0.002, 300), index=idx)
    rs = ra.risk_stats(rets, bench, idx, 246.0)
    assert rs["var95"] > 0 and rs["cvar95"] >= rs["var95"]
    assert rs["cvar99"] >= rs["cvar95"]
    assert len(rs["rollingSharpe"]) == 300 and rs["rollingSharpe"][10] is None and rs["rollingSharpe"][-1] is not None
    assert len(rs["rollingBeta"]) == 300 and abs(rs["rollingBeta"][-1] - 2.0) < 0.8   # 베타 ≈ 1/0.5


def test_turnover_and_liquidity_stats():
    pf, px, idx = _pf()
    val = pf.value()
    to = ra.turnover_stats(pf, val, 80 / 246.0)
    assert to["total"] > 0 and to["annual"] > to["total"]
    tv = pd.DataFrame(1e9, index=idx, columns=["A", "B"])
    liq = ra.liquidity_stats(pf, tv, _CASH)
    assert liq["orders"] > 0 and 0 < liq["maxParticipation"] < 100
    assert liq["capitalAtCap"] > 0
    assert ra.liquidity_stats(pf, None, _CASH)["reason"] == "no_trading_value"


def test_factor_exposure_requires_universe_and_recovers_market_beta():
    n, m = 400, 40
    idx = pd.bdate_range("2022-01-03", periods=n)
    rng = np.random.default_rng(1)
    mkt = rng.normal(0.0003, 0.01, n)
    size = rng.normal(0, 0.003, m)                       # 종목별 규모 성향
    rets = np.column_stack([mkt + rng.normal(0, 0.008, n) for _ in range(m)])
    prices = pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=[f"S{i}" for i in range(m)])
    mcap = pd.DataFrame(np.tile(np.exp(size * 100), (n, 1)), index=idx, columns=prices.columns)
    strat = pd.Series(1.5 * mkt + rng.normal(0, 0.002, n), index=idx)
    bench = pd.Series(mkt, index=idx)
    small = ra.factor_exposure(strat, bench, prices.iloc[:, :5], None, None, None, 246.0)
    assert not small["available"] and small["reason"] == "universe_too_small"
    fe = ra.factor_exposure(strat, bench, prices, mcap, None, None, 246.0)
    assert fe["available"] and fe["observations"] > 200
    mkt_beta = next(l for l in fe["loadings"] if l["factor"] == "MKT")["beta"]
    assert abs(mkt_beta - 1.5) < 0.15
    assert any(l["factor"] == "SMB" for l in fe["loadings"]) and fe["r2"] > 0.8


class _StubEngine:
    def __init__(self):
        self.calls = []

    def run_backtest(self, req):
        self.calls.append(req)
        fee = float((req.get("options") or {}).get("fee_rate") or 0.0)
        slip = float((req.get("options") or {}).get("slippage_rate") or 0.0)
        start = pd.Timestamp(req["startDate"])
        return {"cagr": 10.0 - 1000 * (fee + slip) + start.month * 0.1, "maxDrawdown": -12.0, "sharpe": 1.0,
                "totalReturn": 20.0, "profitFactor": 1.4, "winRate": 55.0, "trades": 30}


def test_rolling_start_shifts_windows_and_summarizes():
    eng = _StubEngine()
    out = rolling_start(eng, {"startDate": "2020-01-01", "endDate": "2024-12-31"}, window_months=24, step_months=6, runs=5)
    assert out["status"] == "ok" and len(out["runs"]) == 5
    assert out["runs"][1]["startDate"] == "2020-07-01" and out["runs"][0]["endDate"] == "2021-12-31"
    assert out["summary"]["cagr"]["count"] == 5 and out["positiveShare"] == 100.0
    out2 = rolling_start(eng, {"startDate": "2023-01-01", "endDate": "2024-12-31"}, window_months=24, step_months=6, runs=5)
    assert len(out2["runs"]) == 1        # 종료일을 넘는 창은 만들지 않는다


def test_cost_sweep_grid_and_cagr_drop():
    eng = _StubEngine()
    out = cost_sweep(eng, {"startDate": "2020-01-01", "endDate": "2024-12-31"}, fee_rates_pct=[0.0, 0.1], slippage_rates_pct=[0.0, 0.5])
    assert out["status"] == "ok" and len(out["cells"]) == 4
    assert out["feeLevels"] == [0.0, 0.1] and out["slippageLevels"] == [0.0, 0.5]
    assert out["cagrDrop"] == pytest.approx(1000 * (0.001 + 0.005))
    assert eng.calls[-1]["options"]["fee_rate"] == pytest.approx(0.001)
    assert cost_sweep(eng, {}, fee_rates_pct=[-1], slippage_rates_pct=[0])["status"] == "error"
