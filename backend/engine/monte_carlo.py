"""
Monte Carlo block-bootstrap simulator for strategy robustness.

주어진 백테스트 결과의 일별 returns 시계열을 block bootstrap으로 재샘플링하여
CAGR/Sharpe/MDD 분포를 추정한다. trade-level이 아닌 **equity return-level** 블록을
사용해 자기상관을 보존한다.

사용:
    mc = MonteCarloSimulator()
    dist = mc.run(backtest_result, n_iterations=1000, block_size=21)
    # dist = {"cagr": {"median","5","95"}, "sharpe": {...}, "mdd": {...}}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from engine.result_handler import KRX_TRADING_DAYS_PER_YEAR


def _backtest_years(backtest_result: Dict[str, Any], bar_count: int) -> float:
    """연수 — 백테스트 엔진(ResultHandler.time_base)과 같은 달력 기준.

    dates(첫 봉~마지막 봉 경과일 ÷ 365.25)로 세고, 날짜가 없으면 봉수 ÷ KRX 거래일(246).
    예전의 봉수 ÷ 252는 연수를 ~2% 적게 잡아 CAGR을 엔진보다 높게 계산했다.
    """
    fallback = max(1e-6, bar_count / KRX_TRADING_DAYS_PER_YEAR)
    dates = backtest_result.get("dates") or []
    if len(dates) < 2:
        return fallback
    try:
        first = np.datetime64(str(dates[0])[:10])
        last = np.datetime64(str(dates[-1])[:10])
    except (ValueError, TypeError):
        return fallback
    span_days = float((last - first) / np.timedelta64(1, "D"))
    if span_days <= 0:
        return fallback
    return span_days / 365.25


class MonteCarloSimulator:
    """Block-bootstrap MC on equity-curve returns (preserves autocorrelation)."""

    def run(
        self,
        backtest_result: Dict[str, Any],
        n_iterations: int = 1000,
        block_size: int = 21,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        equity = backtest_result.get("equity") or []
        if len(equity) < block_size * 3:
            return {
                "status": "error",
                "message": f"equity curve too short: {len(equity)} < {block_size * 3}",
            }

        equity_arr = np.asarray(equity, dtype=np.float64)
        equity_arr = equity_arr[equity_arr > 0]
        if len(equity_arr) < block_size * 3:
            return {"status": "error", "message": "insufficient positive equity points"}

        returns = np.diff(np.log(equity_arr))
        n = len(returns)
        n_blocks = int(np.ceil(n / block_size))

        rng = np.random.default_rng(seed)
        cagrs: List[float] = []
        sharpes: List[float] = []
        mdds: List[float] = []

        initial_equity = float(backtest_result.get("initialCapital") or equity_arr[0])
        years = _backtest_years(backtest_result, len(equity_arr))

        max_starts = n - block_size + 1
        for _ in range(n_iterations):
            starts = rng.integers(0, max_starts, size=n_blocks)
            sampled = np.concatenate([returns[s : s + block_size] for s in starts])[:n]

            log_equity = np.concatenate(([np.log(initial_equity)], np.log(initial_equity) + np.cumsum(sampled)))
            eq = np.exp(log_equity)

            cagr = (eq[-1] / eq[0]) ** (1 / years) - 1 if eq[-1] > 0 else -1.0
            running_max = np.maximum.accumulate(eq)
            dd = (eq - running_max) / running_max
            mdd = float(-dd.min())

            std = sampled.std(ddof=1)
            sharpe = (sampled.mean() / std) * np.sqrt(KRX_TRADING_DAYS_PER_YEAR) if std > 1e-12 else 0.0

            cagrs.append(cagr)
            sharpes.append(float(sharpe))
            mdds.append(mdd)

        def summarize(xs: List[float]) -> Dict[str, float]:
            arr = np.asarray(xs)
            return {
                "median": float(np.median(arr)),
                "mean": float(arr.mean()),
                "p05": float(np.percentile(arr, 5)),
                "p25": float(np.percentile(arr, 25)),
                "p75": float(np.percentile(arr, 75)),
                "p95": float(np.percentile(arr, 95)),
                "std": float(arr.std(ddof=1)),
            }

        return {
            "status": "ok",
            "n_iterations": n_iterations,
            "block_size": block_size,
            "cagr": summarize(cagrs),
            "sharpe": summarize(sharpes),
            "mdd": summarize(mdds),
            "prob_positive_cagr": float(np.mean(np.asarray(cagrs) > 0)),
            "prob_mdd_over_30pct": float(np.mean(np.asarray(mdds) > 0.30)),
        }
