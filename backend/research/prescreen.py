"""
Prescreener — cheap 1-shot backtest per candidate with hard gates.

비용 최소화를 위해 최소 유니버스 샘플 + 3년 구간만 사용. BacktestEngine 재사용.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from research.generator import Candidate
from research.safeguards import (
    AIModelLeakGuard,
    CircuitBreaker,
    HoldoutGuard,
    PrescreenGates,
)

logger = logging.getLogger(__name__)


@dataclass
class PrescreenResult:
    candidate: Candidate
    passed: bool
    reason: str
    metrics: Dict[str, Any]


class Prescreener:
    def __init__(
        self,
        engine: Any,  # BacktestEngine
        gates: PrescreenGates,
        holdout: HoldoutGuard,
        ai_guard: Optional[AIModelLeakGuard] = None,
        sample_symbols: Optional[int] = 50,
        sample_seed: int = 42,
    ):
        self.engine = engine
        self.gates = gates
        self.holdout = holdout
        self.ai_guard = ai_guard
        self.sample_symbols = sample_symbols
        self.sample_seed = sample_seed

    def screen(self, candidates: List[Candidate]) -> List[PrescreenResult]:
        breaker = CircuitBreaker(threshold=20, label="prescreen_zero_trades")
        results: List[PrescreenResult] = []

        for cand in candidates:
            req = self._prepare(cand.backtest_request)
            try:
                if self.ai_guard is not None:
                    self.ai_guard.check(req)
                bt = self.engine.run_backtest(req)
            except Exception as e:
                logger.warning(f"[Prescreen] {cand.dsl_hash[:8]} backtest error: {e}")
                results.append(PrescreenResult(cand, False, f"backtest_error: {e}", {}))
                breaker.record_failure()
                continue

            metrics = {
                "cagr": bt.get("cagr"),
                "sharpe": bt.get("sharpe"),
                "profitFactor": bt.get("profitFactor"),
                "maxDrawdown": bt.get("maxDrawdown"),
                "trades": bt.get("trades"),
                "totalReturn": bt.get("totalReturn"),
            }
            passed, reason = self.gates.passes(bt)
            if bt.get("trades", 0) == 0:
                breaker.record_failure()
            else:
                breaker.record_success()
            results.append(PrescreenResult(cand, passed, reason, metrics))

        return results

    def _prepare(self, base_request: Dict[str, Any]) -> Dict[str, Any]:
        req = self.holdout.clamp(base_request)

        if self.sample_symbols and len(req.get("symbols", [])) > self.sample_symbols:
            rng = random.Random(self.sample_seed)
            req["symbols"] = sorted(rng.sample(req["symbols"], self.sample_symbols))
        return req
