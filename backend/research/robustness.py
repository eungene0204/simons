"""
RobustnessValidator — combines Walk-Forward Analysis + Monte Carlo bootstrap.

기존 WalkForwardAnalyzer (engine/walk_forward.py)와 MonteCarloSimulator
(engine/monte_carlo.py)을 조합해 candidate별 robustness 패키지를 산출한다.

Gating:
- walk_forward_efficiency >= 0.5
- MC CAGR 5%-ile > 0
- MC MDD 95%-ile < 0.5
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.monte_carlo import MonteCarloSimulator
from engine.walk_forward import WalkForwardAnalyzer
from research.generator import Candidate
from research.safeguards import AIModelLeakGuard, HoldoutGuard
from research.scoring import regime_consistency as regime_consistency_score
from research.scoring import robustness_score
from research.search_space import get_search_space

logger = logging.getLogger(__name__)


@dataclass
class RobustnessResult:
    candidate: Candidate
    passed: bool
    reason: str
    wfa: Dict[str, Any] = field(default_factory=dict)
    mc: Dict[str, Any] = field(default_factory=dict)
    robustness_score: float = 0.0
    regime_consistency: float = 0.0
    base_metrics: Dict[str, Any] = field(default_factory=dict)


class RobustnessValidator:
    def __init__(
        self,
        engine: Any,  # BacktestEngine
        holdout: HoldoutGuard,
        ai_guard: Optional[AIModelLeakGuard] = None,
        n_splits: int = 5,
        train_pct: float = 0.7,
        wfa_trials: int = 20,
        mc_iterations: int = 1000,
        mc_block_size: int = 21,
        min_wfe: float = 0.5,
        min_mc_cagr_p05: float = 0.0,
        max_mc_mdd_p95: float = 0.5,
        seed: int = 42,
    ):
        self.engine = engine
        self.holdout = holdout
        self.ai_guard = ai_guard
        self.n_splits = n_splits
        self.train_pct = train_pct
        self.wfa_trials = wfa_trials
        self.mc_iterations = mc_iterations
        self.mc_block_size = mc_block_size
        self.min_wfe = min_wfe
        self.min_mc_cagr_p05 = min_mc_cagr_p05
        self.max_mc_mdd_p95 = max_mc_mdd_p95
        self.seed = seed

        self.wfa = WalkForwardAnalyzer(engine)
        self.mc = MonteCarloSimulator()

    def validate(self, candidates: List[Candidate]) -> List[RobustnessResult]:
        results: List[RobustnessResult] = []
        for cand in candidates:
            results.append(self._validate_one(cand))
        return results

    def _validate_one(self, cand: Candidate) -> RobustnessResult:
        base_req = self.holdout.clamp(cand.backtest_request)
        if self.ai_guard is not None:
            try:
                self.ai_guard.check(base_req)
            except Exception as e:
                return RobustnessResult(cand, False, f"ai_guard: {e}")

        # 1. Base backtest for Monte Carlo input + regime consistency
        try:
            base_bt = self.engine.run_backtest(base_req)
        except Exception as e:
            return RobustnessResult(cand, False, f"base_backtest_error: {e}")

        base_metrics = {
            "cagr": base_bt.get("cagr"),
            "sharpe": base_bt.get("sharpe"),
            "profitFactor": base_bt.get("profitFactor"),
            "maxDrawdown": base_bt.get("maxDrawdown"),
            "trades": base_bt.get("trades"),
        }

        # 2. Monte Carlo on base equity curve
        mc_res = self.mc.run(
            base_bt,
            n_iterations=self.mc_iterations,
            block_size=self.mc_block_size,
            seed=self.seed,
        )

        # 3. Walk-Forward Analysis with template-specific search space
        ranges = get_search_space(cand.template)
        if ranges:
            try:
                wfa_res = self.wfa.analyze(
                    base_request=base_req,
                    ranges=ranges,
                    n_splits=self.n_splits,
                    train_pct=self.train_pct,
                    anchor=False,
                    target_metric="sharpe",
                    n_trials=self.wfa_trials,
                )
            except Exception as e:
                logger.warning(f"[Robustness] WFA failed: {e}")
                wfa_res = {"status": "error", "message": str(e)}
        else:
            wfa_res = {"status": "skipped", "message": "no search space"}

        # 4. Aggregate & gate
        wfe = float(wfa_res.get("walk_forward_efficiency") or 0.0)
        agg = wfa_res.get("aggregate") or {}
        oos_sharpe = float(agg.get("avg_oos_sharpe") or 0.0)
        is_sharpe = float(base_bt.get("sharpe") or 0.0)

        regime = regime_consistency_score(base_bt.get("equity") or [], base_bt.get("dates") or [])

        if mc_res.get("status") == "ok":
            mc_cagr_p05 = float(mc_res["cagr"]["p05"])
            mc_mdd_p95 = float(mc_res["mdd"]["p95"])
            mc_cagr_median = float(mc_res["cagr"]["median"])
        else:
            mc_cagr_p05 = 0.0
            mc_mdd_p95 = 1.0
            mc_cagr_median = 0.0

        rscore = robustness_score(
            wfe=wfe,
            is_sharpe=is_sharpe,
            oos_sharpe=oos_sharpe,
            mc_cagr_p05=mc_cagr_p05,
            mc_cagr_median=mc_cagr_median,
            holdout_passed=False,  # not yet evaluated — added later in HOLDOUT_VAL stage
            regime_consistency=regime,
        )

        reason = "ok"
        passed = True
        if wfe < self.min_wfe:
            passed, reason = False, f"wfe {wfe:.2f} < {self.min_wfe}"
        elif mc_cagr_p05 < self.min_mc_cagr_p05:
            passed, reason = False, f"mc_cagr_p05 {mc_cagr_p05:.3f} < {self.min_mc_cagr_p05}"
        elif mc_mdd_p95 > self.max_mc_mdd_p95:
            passed, reason = False, f"mc_mdd_p95 {mc_mdd_p95:.3f} > {self.max_mc_mdd_p95}"

        return RobustnessResult(
            candidate=cand,
            passed=passed,
            reason=reason,
            wfa=wfa_res,
            mc=mc_res,
            robustness_score=rscore,
            regime_consistency=regime,
            base_metrics=base_metrics,
        )
