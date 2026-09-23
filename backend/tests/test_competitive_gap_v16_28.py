"""경쟁 격차 1차(엔진 v16.28) — 비중 방식 확장·밴드 리밸런싱·최소 보유일·재진입 금지·트레일링 활성화·
지정가·분할 매수/익절·ATR/켈리 사이징·현금 대체 자산·거래량 비례 슬리피지·익일 평균가 체결.

설정이 없는 전략은 종전 경로 그대로다(기존 시뮬레이터 회귀 테스트가 그 계약을 지킨다).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import portfolio_weights as pw
from engine import trade_reason as tr
from engine.indicators import atr_pct_panel
from engine.phase1 import exec_price_series
from engine.simulator import Simulator, impact_slippage_matrix, _kelly_weight

_OPTS = {"execution_type": "same_close", "fee_rate": 0, "slippage_rate": 0, "sell_tax_rate": 0}
_NEXT = {"execution_type": "next_open", "fee_rate": 0, "slippage_rate": 0, "sell_tax_rate": 0}
_CASH = 10_000_000.0


def _frames(closes_by_sym, start="2024-01-01"):
    syms = list(closes_by_sym)
    n = len(next(iter(closes_by_sym.values())))
    idx = pd.bdate_range(start, periods=n)
    px = pd.DataFrame({s: list(map(float, v)) for s, v in closes_by_sym.items()}, index=idx)
    ents = pd.DataFrame(True, index=idx, columns=syms)
    exts = pd.DataFrame(False, index=idx, columns=syms)
    rank = pd.DataFrame({s: float(len(syms) - k) for k, s in enumerate(syms)}, index=idx)
    return idx, px, ents, exts, rank


def _weights_at(pf, row):
    vals = pf.asset_value(group_by=False).iloc[row]
    return vals / pf.value().iloc[row]


# ── portfolio_weights ─────────────────────────────────────────────────────────

def _returns(seed=1, n=120, sigmas=(0.01, 0.03, 0.02)):
    rng = np.random.default_rng(seed)
    return np.column_stack([rng.normal(0.0005, s, n) for s in sigmas])


def test_min_variance_prefers_low_volatility_asset():
    rows = _returns()
    w = pw.min_variance_weights(pw._covariance(rows))
    assert w is not None and w.sum() == pytest.approx(1.0) and (w >= 0).all()
    assert w[0] > w[1]  # 변동성 1%가 3%보다 큰 비중


def test_risk_parity_equalizes_risk_contribution():
    rows = _returns()
    cov = pw._covariance(rows)
    w = pw.risk_parity_weights(cov)
    assert w is not None and w.sum() == pytest.approx(1.0)
    rc = w * (cov @ w)
    assert np.allclose(rc / rc.sum(), 1.0 / 3.0, atol=0.02)


def test_max_sharpe_and_min_cvar_return_long_only_weights():
    rows = _returns(seed=3)
    for w in (pw.max_sharpe_weights(rows.mean(axis=0), pw._covariance(rows)), pw.min_cvar_weights(rows)):
        assert w is not None and w.sum() == pytest.approx(1.0) and (w >= -1e-12).all()


def test_max_sharpe_falls_back_to_min_variance_when_no_positive_mean():
    rows = _returns(seed=4) - 0.01
    cov = pw._covariance(rows)
    assert np.allclose(pw.max_sharpe_weights(rows.mean(axis=0), cov), pw.min_variance_weights(cov))


def test_allocation_context_market_cap_fixed_and_fallback():
    basis = np.array([[100.0, 300.0, np.nan]])
    ctx = pw.AllocationContext("market_cap", basis=basis)
    assert np.allclose(ctx.weights(0, np.array([0, 1])), [0.25, 0.75])
    assert ctx.weights(0, np.array([0, 2])) is None and ctx.fallback_days == 1
    fixed = pw.AllocationContext("fixed", fixed=np.array([0.6, 0.4, 0.0]))
    assert np.allclose(fixed.weights(0, np.array([0, 1])), [0.6, 0.4])
    short = pw.AllocationContext("min_variance", returns=_returns(n=10), offset=0, lookback=60)
    assert short.weights(9, np.array([0, 1, 2])) is None   # 관측 부족 → 동일가중 폴백


# ── 순수 리밸런싱 경로: 비중 방식·밴드·현금 대체 자산 ────────────────────────

def test_pure_path_market_cap_weights_follow_basis():
    idx, px, ents, exts, rank = _frames({"A": [100.0] * 30, "B": [100.0] * 30})
    basis = np.tile([[300.0, 100.0]], (30, 1))
    ctx = pw.AllocationContext("market_cap", basis=basis)
    risk = {"max_positions": 2, "init_cash": _CASH, "allocation_type": "market_cap",
            "rebalancing_period": "monthly"}
    pf = Simulator().run(px, px, ents, exts, risk, _OPTS, rank_df=rank, alloc_ctx=ctx)
    w = _weights_at(pf, 5)
    assert w["A"] == pytest.approx(0.75, abs=0.01) and w["B"] == pytest.approx(0.25, abs=0.01)
    assert ctx.applied_days >= 1 and ctx.fallback_days == 0


def test_pure_path_band_rebalance_resets_after_drift():
    a = [100.0] * 5 + [150.0] * 25     # A가 50% 급등 → 비중 60/40(이탈 10%p) → 밴드 8%p 초과
    idx, px, ents, exts, rank = _frames({"A": a, "B": [100.0] * 30})
    risk = {"max_positions": 2, "init_cash": _CASH, "allocation_type": "equal",
            "rebalancing_period": "yearly", "rebalance_threshold_pct": 8}
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, risk, _OPTS, rank_df=rank)
    assert sim.band_events >= 1
    w = _weights_at(pf, 8)
    assert abs(w["A"] - 0.5) < 0.03                       # 되돌린 뒤 다시 50/50
    reasons = {r for by in sim.exit_reason_overrides.values() for r in by.values()}
    assert any(tr.BAND_REBALANCE in r for r in reasons)
    # 밴드가 없으면 드리프트가 그대로 남는다.
    risk_no = {k: v for k, v in risk.items() if k != "rebalance_threshold_pct"}
    pf2 = Simulator().run(px, px, ents, exts, risk_no, _OPTS, rank_df=rank)
    assert _weights_at(pf2, 8)["A"] > 0.58


def test_pure_path_cash_asset_holds_uninvested_share():
    idx, px, ents, exts, rank = _frames({"A": [100.0] * 20, "SAFE": [100.0] * 20})
    ents["SAFE"] = False
    risk = {"max_positions": 1, "init_cash": _CASH, "allocation_type": "equal",
            "rebalancing_period": "monthly", "max_position_weight_pct": 40, "cash_asset": "SAFE"}
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, risk, _OPTS, rank_df=rank, cash_asset_idx=1)
    w = _weights_at(pf, 3)
    assert w["A"] == pytest.approx(0.4, abs=0.01) and w["SAFE"] == pytest.approx(0.6, abs=0.01)
    assert any(tr.CASH_ASSET_PARK in r for by in sim.entry_reason_overrides.values() for r in by.values())


# ── 조건 루프 경로 ────────────────────────────────────────────────────────────

def _loop_frames(a_path, n=None):
    n = n or len(a_path)
    idx = pd.bdate_range("2024-01-01", periods=n)
    px = pd.DataFrame({"A": list(map(float, a_path))}, index=idx)
    ents = pd.DataFrame(False, index=idx, columns=["A"])
    ents.iloc[0, 0] = True
    exts = pd.DataFrame(False, index=idx, columns=["A"])
    return idx, px, ents, exts


def _held(pf, row):
    return float(pf.asset_value(group_by=False).iloc[row]["A"]) > 0


def test_min_holding_days_defers_stop_loss():
    path = [100, 80, 80, 80, 80, 80, 80, 80]        # 2일째 -20% → 손절 조건
    idx, px, ents, exts = _loop_frames(path)
    base = {"max_positions": 1, "init_cash": _CASH, "stop_loss_pct": 10, "entry_signal_driven": True}
    pf = Simulator().run(px, px, ents, exts, base, _OPTS)
    assert not _held(pf, 1)                               # 최소 보유 없음 → 즉시 손절
    pf2 = Simulator().run(px, px, ents, exts, {**base, "min_holding_days": 4}, _OPTS)
    assert _held(pf2, 3) and not _held(pf2, 4)            # 4거래일 지난 뒤 손절


def test_stop_cooldown_blocks_reentry():
    path = [100, 80, 80, 80, 80, 80, 80, 80, 80, 80]
    idx, px, _, exts = _loop_frames(path)
    ents = pd.DataFrame(True, index=idx, columns=["A"])      # 매일 재진입 신호
    base = {"max_positions": 1, "init_cash": _CASH, "stop_loss_pct": 10, "entry_signal_driven": True}
    pf = Simulator().run(px, px, ents, exts, base, _OPTS)
    assert _held(pf, 2)                                    # 손절 다음 날 바로 재매수
    pf2 = Simulator().run(px, px, ents, exts, {**base, "stop_cooldown_days": 5}, _OPTS)
    assert not _held(pf2, 3) and _held(pf2, 6)


def test_trailing_stop_activation_threshold():
    path = [100, 104, 100, 100, 100]                     # 고점 +4%, 그 뒤 -3.8% 하락
    idx, px, ents, exts = _loop_frames(path)
    base = {"max_positions": 1, "init_cash": _CASH, "trailing_stop_pct": 3, "entry_signal_driven": True}
    assert not _held(Simulator().run(px, px, ents, exts, base, _OPTS), 3)
    pf2 = Simulator().run(px, px, ents, exts, {**base, "trailing_stop_activation_pct": 5}, _OPTS)
    assert _held(pf2, 3)                                   # +5% 전이라 트레일링 미작동


def test_partial_take_profit_sells_part_of_position():
    path = [100, 112, 112, 112, 112]
    idx, px, ents, exts = _loop_frames(path)
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True,
            "partial_take_profits": [{"profit_pct": 10, "sell_pct": 50}]}
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, risk, _OPTS)
    w1 = _weights_at(pf, 1)["A"]
    assert 0.45 <= w1 <= 0.55 and sim.partial_tp_events == 1
    reasons = {r for by in sim.exit_reason_overrides.values() for r in by.values()}
    assert any(tr.PARTIAL_TAKE_PROFIT in r for r in reasons)


def test_entry_tranches_fill_on_price_ladder():
    path = [100, 100, 94, 94, 88, 88]
    idx, px, ents, exts = _loop_frames(path)
    low = px.copy()
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True,
            "entry_tranches": {"count": 3, "step_pct": 5}}
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, risk, _OPTS, low_df=low, high_df=px)
    assert _weights_at(pf, 0)["A"] == pytest.approx(1 / 3, abs=0.02)
    assert _weights_at(pf, 2)["A"] > 0.6 and _weights_at(pf, 4)["A"] > 0.95
    assert sim.tranche_fills == 2
    assert any(tr.TRANCHE_BUY in r for by in sim.entry_reason_overrides.values() for r in by.values())


def test_entry_limit_fills_only_when_low_touches_limit():
    # next_open: 신호 행 i의 체결가는 그날 시가. 지정가 = 전일 종가 × 0.97.
    idx = pd.bdate_range("2024-01-01", periods=5)
    close = pd.DataFrame({"A": [100.0, 100.0, 100.0, 100.0, 100.0]}, index=idx)
    open_ = close.copy()
    low = pd.DataFrame({"A": [100.0, 99.0, 96.0, 100.0, 100.0]}, index=idx)
    ents = pd.DataFrame({"A": [False, True, True, False, False]}, index=idx)
    exts = pd.DataFrame(False, index=idx, columns=["A"])
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True, "entry_limit_pct": 3}
    pf = Simulator().run(close, open_, ents, exts, risk, _NEXT, low_df=low, high_df=close)
    assert not _held(pf, 1) and _held(pf, 2)
    fill = float(pf.orders.records_readable.iloc[0]["Price"])
    assert fill == pytest.approx(97.0)


def test_exit_limit_defers_unfilled_signal_exit_to_next_day_market():
    idx = pd.bdate_range("2024-01-01", periods=6)
    close = pd.DataFrame({"A": [100.0] * 6}, index=idx)
    high = pd.DataFrame({"A": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]}, index=idx)
    ents = pd.DataFrame({"A": [True, False, False, False, False, False]}, index=idx)
    exts = pd.DataFrame({"A": [False, False, True, False, False, False]}, index=idx)
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True, "exit_limit_pct": 2}
    pf = Simulator().run(close, close, ents, exts, risk, _NEXT, high_df=high, low_df=close)
    assert _held(pf, 2) and not _held(pf, 3)              # 미체결 → 다음 날 시장가
    high2 = high.copy()
    high2.iloc[2, 0] = 103.0
    pf2 = Simulator().run(close, close, ents, exts, risk, _NEXT, high_df=high2, low_df=close)
    assert not _held(pf2, 2)
    sells = pf2.orders.records_readable[pf2.orders.records_readable["Side"] == "Sell"]
    assert float(sells.iloc[0]["Price"]) == pytest.approx(102.0)


def test_atr_sizing_uses_risk_budget_and_falls_back_without_atr():
    idx, px, ents, exts = _loop_frames([100.0] * 6)
    size = pd.DataFrame({"A": [np.nan, 0.02, 0.02, 0.02, 0.02, 0.02]}, index=idx)
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True,
            "position_sizing": {"method": "atr_risk", "risk_per_trade_pct": 1, "atr_multiple": 2}}
    sim = Simulator()
    pf = sim.run(px, px, ents, exts, risk, _OPTS, size_df=size)
    assert _weights_at(pf, 0)["A"] == pytest.approx(1.0, abs=0.01) and sim.sizing_fallbacks == 1
    ents2 = ents.copy()
    ents2.iloc[0, 0] = False
    ents2.iloc[1, 0] = True
    pf2 = Simulator().run(px, px, ents2, exts, risk, _OPTS, size_df=size)
    assert _weights_at(pf2, 1)["A"] == pytest.approx(0.25, abs=0.01)   # 1% ÷ (2 × 2%)


def test_kelly_weight_needs_history_and_positive_edge():
    assert _kelly_weight([0.1] * 5, [-0.05] * 5, 0.5) is None
    assert _kelly_weight([0.1] * 12, [-0.1] * 8, 0.5) == pytest.approx((0.6 - 0.4) * 0.5)
    assert _kelly_weight([0.05] * 10, [-0.1] * 10, 0.5) is None      # 켈리 0 이하


def test_impact_slippage_matrix_scales_with_order_size():
    idx, px, ents, exts = _loop_frames([100.0] * 4)
    risk = {"max_positions": 1, "init_cash": _CASH, "entry_signal_driven": True}
    pf = Simulator().run(px, px, ents, exts, risk, _OPTS)
    adv = np.full((4, 1), _CASH * 4.0)      # 주문 = 평균 거래대금의 1/4 → √0.25 = 0.5
    m = impact_slippage_matrix(pf, adv, 0.001, 0.1, (4, 1))
    assert m[0, 0] == pytest.approx(0.001 + 0.05) and m[1, 0] == pytest.approx(0.001)
    sim = Simulator()
    pf2 = sim.run(px, px, ents, exts, risk, {**_OPTS, "slippage_rate": 0.001, "slippage_model": "volume_impact",
                                            "slippage_impact_coeff": 0.1},
                  adv_df=pd.DataFrame(adv, index=idx, columns=["A"]))
    assert sim.impact_slippage["max"] == pytest.approx(0.051)
    assert float(pf2.value().iloc[-1]) < float(pf.value().iloc[-1])


def test_exec_price_series_avg_and_atr_panel():
    pdf = pd.DataFrame({"open": [10.0, 12.0], "high": [12.0, 14.0], "low": [8.0, 10.0], "close": [10.0, 12.0]})
    assert list(exec_price_series(pdf, "next_open", "avg")) == [10.0, 12.0]
    assert list(exec_price_series(pdf, "next_open")) == [10.0, 12.0]
    assert list(exec_price_series(pdf, "same_close", "avg")) == [10.0, 12.0]
    idx = pd.bdate_range("2024-01-01", periods=4)
    hi = pd.DataFrame({"A": [11.0, 12.0, 13.0, 14.0]}, index=idx)
    lo = pd.DataFrame({"A": [9.0, 10.0, 11.0, 12.0]}, index=idx)
    cl = pd.DataFrame({"A": [10.0, 11.0, 12.0, 13.0]}, index=idx)
    atr = atr_pct_panel(hi, lo, cl, 2)
    assert np.isnan(atr.iloc[0, 0]) and atr.iloc[2, 0] == pytest.approx(2.0 / 12.0)


# ── 부가 실행 경로의 비중 방식 배선(2026-09-23 수리) ──────────────────────────

def _alloc_universe(data_dir, dates):
    """변동성이 뚜렷이 다른 4종목 — 최소 분산 비중이 동일가중과 다른 답을 내도록."""
    import polars as pl

    def write(symbol, prices):
        pl.from_dicts([
            {"date": d.strftime("%Y-%m-%d"), "open": float(p), "high": float(p + 1),
             "low": float(p - 1), "close": float(p), "volume": 5_000_000.0}
            for d, p in zip(dates, prices)
        ]).write_parquet(f"{data_dir}/{symbol}.parquet")

    rng = np.random.default_rng(7)
    for k, (sym, sigma, drift) in enumerate((
            ("ALC_CALM_A", 0.004, 0.0012), ("ALC_CALM_B", 0.005, 0.0010),
            ("ALC_WILD_C", 0.030, 0.0009), ("ALC_WILD_D", 0.035, 0.0008))):
        write(sym, list(100 * np.cumprod(1 + rng.normal(drift, sigma, len(dates)))))
    return ["ALC_CALM_A", "ALC_CALM_B", "ALC_WILD_C", "ALC_WILD_D"]


def test_allocation_reaches_rebalance_comparison_and_quantile_groups():
    """비중 방식(v16.28)은 부가 실행(리밸런싱 6주기 비교·분위 그룹)에도 같은 기준으로 적용된다.

    종전에는 본 결과만 최소 분산으로 돌고 비교표·그룹은 동일가중이라, 같은 주기인데 표의 CAGR이
    본 결과와 달랐다(2026-09-23 발견·수리). 적용 횟수 고지는 본 실행 것만 세야 한다.
    """
    import os

    from backtest_engine import BacktestEngine

    dates = pd.date_range(start="2023-01-02", periods=420, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = _alloc_universe(data_dir, dates)
    req = {
        "symbols": symbols, "entry": {"conditions": []}, "exit": {"conditions": []},
        "risk": {"position_size_pct": 25, "max_positions": 2, "ranking_metric": "return",
                 "ranking_lookback_days": 20, "rebalancing_period": "monthly",
                 "allocation_type": "min_variance", "allocation_lookback_days": 60,
                 "liquidity_multiplier": 0, "init_cash": 10_000_000.0},
        "options": {"execution_type": "same_close"},
    }
    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest(req)

    rows = {r["period"]: r for r in (result.get("rebalanceComparison") or {}).get("periods", [])}
    assert "monthly" in rows, "리밸런싱 비교표에 현재 주기가 없다"
    # 비교표 값은 소수 2자리 반올림(summarize_portfolio) — 같은 값이면 그 안에서 만난다.
    assert rows["monthly"]["cagr"] == pytest.approx(result["cagr"], abs=0.011), (
        "같은 주기인데 비교표 CAGR이 본 결과와 다르다 — 부가 실행에 비중 방식이 전달되지 않음")

    applied = [w for w in (result.get("warnings") or []) if "최소 분산" in w and "리밸런싱일마다" in w]
    assert applied, "비중 방식 적용 고지가 없다"
    # 고지 횟수는 본 실행(월간 리밸런싱일 수)만 — 비교표 6주기가 더해지면 몇 배로 부푼다.
    import re
    counted = int(re.search(r"\((\d+)회", applied[0]).group(1))
    assert counted <= 15, f"적용 횟수가 본 실행 범위를 넘었다: {counted}"
