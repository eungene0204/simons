"""리밸런싱 기간별 결과 비교(FR-BT-064) — 백테스트 결과에 동봉되는 6주기 재시뮬레이션.

- 결정론 부분: 주기 순회·행 단위 실패 격리·현재 주기·보유 상한 없음 플래그.
- 엔진 통합: run_backtest 결과에 rebalanceComparison이 실리고, 메인 결과와 같은 주기의 행은
  메인 지표와 일치한다(같은 입력·같은 시뮬레이터이므로).
"""

import os

import pytest

pytest.importorskip("vectorbt")
pytest.importorskip("polars")
pytest.importorskip("stockstats")

import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from engine.rebalance_comparison import (  # noqa: E402
    REBALANCE_PERIODS,
    assemble_comparison,
    periods_to_simulate,
    simulate_period_rows,
    rebalance_applies,
    run_rebalance_period_comparison,
)


# ── 결정론(가짜 시뮬레이션) ──────────────────────────────────────────────────

def test_runs_every_period_and_isolates_failures():
    seen = []

    def run_sim(rp):
        seen.append(rp["rebalancing_period"])
        if rp["rebalancing_period"] == "weekly":
            raise RuntimeError("boom-weekly")
        return {"period": rp["rebalancing_period"]}

    def summarize(pf, init_cash):
        return {"cagr": 1.0, "trades": 3}

    out = run_rebalance_period_comparison(run_sim, {"max_positions": 5, "rebalancing_period": "monthly"}, 1_000_000, summarize=summarize)
    assert seen == list(REBALANCE_PERIODS)
    rows = {r["period"]: r for r in out["periods"]}
    assert rows["weekly"]["error"] == "boom-weekly"
    assert rows["monthly"] == {"period": "monthly", "cagr": 1.0, "trades": 3, "error": None}
    assert out["currentPeriod"] == "monthly"
    assert out["positionCapAbsent"] is False


def test_position_cap_absent_flag_and_original_risk_untouched():
    risk = {"max_positions": None, "rebalancing_period": "none"}
    out = run_rebalance_period_comparison(lambda rp: None, risk, 1.0, summarize=lambda pf, c: {})
    assert out["positionCapAbsent"] is True
    assert out["currentPeriod"] == "none"
    assert risk["rebalancing_period"] == "none"  # 원본 risk_params 불변


def test_rebalance_applies_requires_position_cap():
    assert rebalance_applies({"max_positions": 10})
    assert rebalance_applies({"max_positions_pct": 20})
    assert not rebalance_applies({"max_positions": None})
    assert not rebalance_applies({"max_positions": 10, "skip_position_setting": True})


# ── 엔진 통합 ────────────────────────────────────────────────────────────────

def _write_series(data_dir: str, symbol: str, prices, dates) -> None:
    rows = [
        {"date": d.strftime("%Y-%m-%d"), "open": float(p), "high": float(p + 1), "low": float(p - 1),
         "close": float(p), "volume": 5_000_000.0}
        for d, p in zip(dates, prices)
    ]
    pl.from_dicts(rows).write_parquet(f"{data_dir}/{symbol}.parquet")


def test_engine_attaches_rebalance_comparison_matching_main_result():
    from backtest_engine import BacktestEngine

    dates = pd.date_range(start="2024-01-01", periods=120, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    _write_series(data_dir, "RBC_UP_A", [100 + 2 * i for i in range(120)], dates)
    _write_series(data_dir, "RBC_UP_B", [100 + 1 * i for i in range(120)], dates)
    _write_series(data_dir, "RBC_FLAT", [100.0 for _ in range(120)], dates)
    _write_series(data_dir, "RBC_DOWN", [220 - 1 * i for i in range(120)], dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RBC_UP_A", "RBC_UP_B", "RBC_FLAT", "RBC_DOWN"],
        "entry": {"conditions": []},  # 순수 랭킹(선정=진입) — 리밸런싱 주기가 회전을 결정
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50, "max_positions": 2,
            "ranking_metric": "return", "ranking_lookback_days": 5,
            "rebalancing_period": "monthly", "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }
    result = engine.run_backtest(req)

    cmp = result.get("rebalanceComparison")
    assert cmp is not None, "백테스트 결과에 rebalanceComparison이 실려야 한다"
    assert [r["period"] for r in cmp["periods"]] == list(REBALANCE_PERIODS)
    assert cmp["currentPeriod"] == "monthly"
    assert cmp["positionCapAbsent"] is False
    assert all(r["error"] is None for r in cmp["periods"])

    # 메인 결과와 같은 주기(monthly) 행은 같은 입력·같은 시뮬레이터라 메인 지표와 일치한다.
    monthly = next(r for r in cmp["periods"] if r["period"] == "monthly")
    assert monthly["trades"] == result["trades"]
    assert monthly["cagr"] == pytest.approx(result["cagr"], abs=0.02)
    assert monthly["mdd"] == pytest.approx(result["maxDrawdown"], abs=0.02)
    # 매일 리밸런싱은 월간보다 회전이 잦다(거래 수 ≥).
    daily = next(r for r in cmp["periods"] if r["period"] == "daily")
    assert daily["trades"] >= monthly["trades"]
    assert result["timing"]["rebalanceComparison"] >= 0


def test_position_cap_absent_simulates_once_and_replicates_six_rows():
    """보유 상한이 없으면 시뮬레이터 rebalance_mode가 어떤 주기에서도 False라 6번이 같다 —
    한 번만 돌리고 복제해도 결과가 동일하고 시간은 1/6이다."""
    risk = {"max_positions": None, "rebalancing_period": "none"}
    assert periods_to_simulate(risk) == ("daily",)
    assert len(periods_to_simulate({"max_positions": 3})) == 6
    calls = []
    out = run_rebalance_period_comparison(lambda rp: calls.append(rp["rebalancing_period"]) or object(),
                                          risk, 1.0, summarize=lambda pf, c: {"cagr": 1.2})
    assert calls == ["daily"]
    assert [r["period"] for r in out["periods"]] == list(REBALANCE_PERIODS)
    assert all(r["cagr"] == 1.2 and r["error"] is None for r in out["periods"])
    assert out["positionCapAbsent"] is True


def test_assemble_comparison_orders_rows_by_period_and_marks_missing():
    rows = simulate_period_rows(lambda rp: object(), {"max_positions": 2}, 1.0, ("monthly", "daily"),
                                summarize=lambda pf, c: {"cagr": 0.0})
    out = assemble_comparison(rows, {"max_positions": 2})
    assert [r["period"] for r in out["periods"]] == list(REBALANCE_PERIODS)
    assert out["periods"][0]["error"] is None            # daily 있음
    assert out["periods"][3]["error"] == "결과 없음"      # quarterly 없음
