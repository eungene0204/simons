"""Monte Carlo simulation engine for backtest results.

Strategy:
  - Extract daily log-returns from the equity curve.
  - Block-bootstrap (block_size days) to preserve autocorrelation.
  - Reconstruct N equity paths and compute statistics.
"""
import numpy as np
from typing import List, Dict, Any


def run_monte_carlo(
    equity: List[float],
    initial_capital: float,
    n_simulations: int = 1000,
    block_size: int = 20,
    seed: int | None = 42,
) -> Dict[str, Any]:
    """
    Run Monte Carlo simulation via block-bootstrap of daily returns.

    Args:
        equity: Equity curve from backtest (length T).
        initial_capital: Starting capital.
        n_simulations: Number of simulation paths.
        block_size: Block size for block-bootstrap (days).
        seed: Random seed for reproducibility.

    Returns dict with:
        n_simulations, n_days,
        percentile_paths: {"5", "25", "50", "75", "95"} — List[float] of length T
        final_return_pct: {"1","5","10","25","50","75","90","95","99"} — percentile of final return %
        final_return_distribution: List[float] — all N final return % values (for histogram)
        mdd_distribution: List[float] — all N MDD % values
        mdd_percentiles: {"5","25","50","75","95"}
        prob_profit: float — P(final return > 0)
        prob_beat_zero: float (same as prob_profit)
        sharpe_percentiles: {"5","25","50","75","95"}
    """
    equity_arr = np.array(equity, dtype=np.float64)
    T = len(equity_arr)
    if T < 2:
        raise ValueError("equity curve too short for Monte Carlo")

    # Daily log-returns
    log_returns = np.log(equity_arr[1:] / equity_arr[:-1])  # shape (T-1,)
    n_returns = len(log_returns)

    rng = np.random.default_rng(seed)

    # Build blocks
    n_blocks_needed = int(np.ceil(n_returns / block_size))
    all_paths = np.empty((n_simulations, T), dtype=np.float64)
    all_paths[:, 0] = initial_capital

    # Vectorised block-bootstrap
    # Start indices for each block draw
    max_start = n_returns - block_size + 1
    if max_start <= 0:
        # fallback: IID bootstrap if series too short for blocks
        block_size = 1
        max_start = n_returns

    starts = rng.integers(0, max_start, size=(n_simulations, n_blocks_needed))

    for sim_i in range(n_simulations):
        sampled = []
        for b in range(n_blocks_needed):
            s = starts[sim_i, b]
            sampled.append(log_returns[s : s + block_size])
        sampled_returns = np.concatenate(sampled)[:n_returns]
        # Reconstruct equity path
        cum = np.cumsum(sampled_returns)
        path = initial_capital * np.exp(np.concatenate([[0.0], cum]))
        all_paths[sim_i, :] = path[:T]

    # Final returns (%)
    final_returns_pct = (all_paths[:, -1] / initial_capital - 1.0) * 100.0

    # MDD per path
    def _mdd(path: np.ndarray) -> float:
        peak = np.maximum.accumulate(path)
        dd = (path - peak) / peak
        return float(dd.min() * 100.0)  # negative value

    mdd_arr = np.array([_mdd(all_paths[i]) for i in range(n_simulations)])

    # Sharpe per path (annualised, assumes 252 trading days)
    def _sharpe(path: np.ndarray) -> float:
        r = np.diff(np.log(path))
        if r.std() == 0:
            return 0.0
        return float(r.mean() / r.std() * np.sqrt(252))

    sharpe_arr = np.array([_sharpe(all_paths[i]) for i in range(n_simulations)])

    # Percentile paths
    pct_levels = [5, 25, 50, 75, 95]
    percentile_paths: Dict[str, List[float]] = {}
    for p in pct_levels:
        percentile_paths[str(p)] = np.percentile(all_paths, p, axis=0).tolist()

    def _pct_dict(arr: np.ndarray, levels=None) -> Dict[str, float]:
        if levels is None:
            levels = [1, 5, 10, 25, 50, 75, 90, 95, 99]
        return {str(l): float(np.percentile(arr, l)) for l in levels}

    prob_profit = float(np.mean(final_returns_pct > 0))

    return {
        "n_simulations": n_simulations,
        "n_days": T,
        "percentile_paths": percentile_paths,
        "final_return_pct": _pct_dict(final_returns_pct),
        "final_return_distribution": final_returns_pct.tolist(),
        "mdd_distribution": mdd_arr.tolist(),
        "mdd_percentiles": _pct_dict(mdd_arr, [5, 25, 50, 75, 95]),
        "sharpe_percentiles": _pct_dict(sharpe_arr, [5, 25, 50, 75, 95]),
        "prob_profit": prob_profit,
    }
