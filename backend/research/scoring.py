"""
Composite scoring for strategy candidates.

설계 문서 Step 3 의 수식을 그대로 구현. Scale mismatch를 방지하기 위해 각 항목은
bounded tanh 변환 후 가중 합산. Robustness 가중치가 returns 가중치보다 크다
(robustness > raw returns).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ScoreWeights:
    cagr: float = 0.20
    sharpe: float = 0.25
    profit_factor: float = 0.15
    mdd_penalty: float = 0.20
    robustness: float = 0.20

    def __post_init__(self) -> None:
        total = self.cagr + self.sharpe + self.profit_factor + self.mdd_penalty + self.robustness
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"ScoreWeights must sum to 1.0 (got {total})")


def _tanh(x: float) -> float:
    return math.tanh(x)


def _safe(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def composite_score(
    metrics: Dict[str, Any],
    robustness: float,
    weights: Optional[ScoreWeights] = None,
) -> float:
    """Map mixed-scale metrics to a single [-1, 1] score.

    metrics expects: cagr, sharpe, profitFactor, maxDrawdown (all in decimal, e.g. 0.15 = 15%)
    robustness expects: [0, 1] — compute via robustness_score().
    """
    w = weights or ScoreWeights()

    s_cagr = _tanh(_safe(metrics.get("cagr")) / 0.20)
    s_sharpe = _tanh(_safe(metrics.get("sharpe")) / 1.5)
    s_pf = _tanh((_safe(metrics.get("profitFactor"), 1.0) - 1.0) / 1.0)
    s_mdd = -_tanh(_safe(metrics.get("maxDrawdown")) / 0.25)  # penalty (negative contribution when MDD > 0)
    s_robust = 2.0 * _clip(robustness) - 1.0  # map [0,1] → [-1,1] for consistent scale

    return (
        w.cagr * s_cagr
        + w.sharpe * s_sharpe
        + w.profit_factor * s_pf
        + w.mdd_penalty * s_mdd
        + w.robustness * s_robust
    )


def robustness_score(
    wfe: float,
    is_sharpe: float,
    oos_sharpe: float,
    mc_cagr_p05: float,
    mc_cagr_median: float,
    holdout_passed: bool,
    regime_consistency: float,
) -> float:
    """Blend 5 orthogonal robustness dimensions to [0, 1]."""
    sharpe_ratio = oos_sharpe / is_sharpe if is_sharpe > 1e-6 else 0.0
    mc_stability = mc_cagr_p05 / mc_cagr_median if mc_cagr_median > 1e-6 else 0.0

    return _clip(
        0.30 * _clip(wfe)
        + 0.25 * _clip(sharpe_ratio)
        + 0.20 * _clip(mc_stability)
        + 0.15 * (1.0 if holdout_passed else 0.0)
        + 0.10 * _clip(regime_consistency)
    )


def deflated_sharpe(sharpe: float, n_trials: int, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Bailey-López de Prado deflated Sharpe (approximation).

    Accounts for multiple-testing bias + non-normality. If DSR < 0 the strategy
    is likely a noise artifact and should be rejected.
    """
    sharpe = _safe(sharpe)
    if n_trials <= 1:
        return sharpe

    # Expected max under null of n_trials i.i.d. Sharpes (Gumbel approximation)
    euler = 0.5772156649
    e_max = (1.0 - euler) * _inv_cdf(1.0 - 1.0 / n_trials) + euler * _inv_cdf(
        1.0 - 1.0 / (n_trials * math.e)
    )

    denom = math.sqrt(max(1e-9, 1.0 - skew * sharpe + ((kurt - 1.0) / 4.0) * sharpe * sharpe))
    return (sharpe - e_max) / denom


def _inv_cdf(p: float) -> float:
    """Approximate normal inverse CDF (Beasley-Springer-Moro) for deflated Sharpe."""
    p = _clip(p, 1e-9, 1.0 - 1e-9)
    # Abramowitz-Stegun rational approximation
    a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924]
    b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857]
    c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878]
    d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
        )
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )


def regime_consistency(equity: list, dates: list) -> float:
    """Rough regime-split CAGR consistency: split equity in 4 equal time quartiles,
    compute period return for each, return worst/best ratio in [0,1].

    1.0 = all quartiles equally profitable; 0.0 = one quartile dominates.
    """
    import numpy as np

    if not equity or len(equity) < 40:
        return 0.0
    eq = np.asarray(equity, dtype=float)
    n = len(eq)
    splits = np.array_split(eq, 4)
    period_returns = []
    for s in splits:
        if len(s) < 2 or s[0] <= 0:
            continue
        period_returns.append(s[-1] / s[0] - 1.0)
    if len(period_returns) < 2:
        return 0.0
    arr = np.asarray(period_returns)
    # shift to positive domain then take worst/best ratio
    offset = abs(arr.min()) + 1e-6 if arr.min() < 0 else 0
    shifted = arr + offset
    if shifted.max() < 1e-9:
        return 0.0
    return float(max(0.0, min(1.0, shifted.min() / shifted.max())))
