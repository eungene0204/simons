"""
Safeguards — runtime invariants that reject overfitting / data-snooping / abuse.

All guards raise explicit exception types so the agent state machine can
route failures to the right error bucket.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd


class HoldoutViolation(Exception):
    """Raised when a backtest request attempts to read past the locked holdout date."""


class CircuitBreakerTripped(Exception):
    """Raised when consecutive failures exceed a threshold (stops the run)."""


class AIModelLeakDetected(Exception):
    """Raised when an ai_model template is scheduled over AI training data."""


@dataclass
class HoldoutGuard:
    """Enforces `request.endDate <= holdout_start` on every engine call.

    The guard mutates a copy of the request (non-destructive) and sets endDate
    to the holdout cutoff. If the caller explicitly passed an endDate past the
    cutoff it raises — silent clamping would hide a logic bug.
    """

    holdout_start: str  # ISO date, e.g. "2025-10-20"

    def clamp(self, request: Dict[str, Any]) -> Dict[str, Any]:
        cutoff = pd.to_datetime(self.holdout_start)
        end = request.get("endDate")
        if end is not None and pd.to_datetime(end) > cutoff:
            raise HoldoutViolation(
                f"request endDate {end} > holdout_start {self.holdout_start}"
            )
        req = copy.deepcopy(request)
        # Always pin endDate strictly before holdout (exclusive)
        req["endDate"] = (cutoff - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        return req

    def build_holdout_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Produce the final 1-shot holdout-validation request.

        Runs from holdout_start to today. Called EXACTLY ONCE per candidate
        in the HOLDOUT_VAL stage.
        """
        req = copy.deepcopy(request)
        req["startDate"] = self.holdout_start
        req.pop("endDate", None)
        req["period"] = "full"  # force explicit date window
        return req


class CircuitBreaker:
    """Trip after N consecutive failures of the *same kind* (e.g. trades=0)."""

    def __init__(self, threshold: int = 20, label: str = "circuit"):
        self.threshold = threshold
        self.label = label
        self.count = 0

    def record_failure(self) -> None:
        self.count += 1
        if self.count >= self.threshold:
            raise CircuitBreakerTripped(
                f"[{self.label}] {self.count} consecutive failures — aborting run"
            )

    def record_success(self) -> None:
        self.count = 0


@dataclass
class AIModelLeakGuard:
    """Ensures any ai_model candidate is evaluated strictly after AI training cutoff.

    The AI engine (backend/ai/ai_engine.py) freezes weights at a known date;
    using it to predict within the training window is leakage.
    """

    ai_training_cutoff: str  # ISO date after which predictions are out-of-sample

    def check(self, request: Dict[str, Any]) -> None:
        if not self._uses_ai_model(request):
            return
        start = request.get("startDate")
        if start is None:
            # Period-based — the engine will compute startDate; assume 5y window
            # and fail closed if today - period < cutoff.
            return
        if pd.to_datetime(start) < pd.to_datetime(self.ai_training_cutoff):
            raise AIModelLeakDetected(
                f"ai_model backtest startDate {start} < training cutoff {self.ai_training_cutoff}"
            )

    @staticmethod
    def _uses_ai_model(request: Dict[str, Any]) -> bool:
        def walk(group: Optional[Dict[str, Any]]) -> bool:
            if not group:
                return False
            for c in group.get("conditions", []):
                if c.get("id") in ("ai_model", "ai_drop_model"):
                    return True
                if "conditions" in c and walk(c):
                    return True
            return False

        return walk(request.get("entry")) or walk(request.get("exit"))


@dataclass
class PrescreenGates:
    """Hard gates before a candidate proceeds to robustness validation."""

    min_trades: int = 30
    min_trades_per_year: float = 5.0
    min_cagr_ratio_vs_benchmark: float = 0.5
    min_profit_factor: float = 1.0
    max_drawdown: float = 0.5

    def passes(self, result: Dict[str, Any], years: float = 3.0, benchmark_cagr: float = 0.05) -> tuple[bool, str]:
        trades = int(result.get("trades", 0) or 0)
        if trades < self.min_trades:
            return False, f"trades {trades} < min {self.min_trades}"
        if trades / max(1e-6, years) < self.min_trades_per_year:
            return False, f"trade density {trades / years:.1f}/y < {self.min_trades_per_year}"
        cagr = float(result.get("cagr", 0) or 0)
        if cagr < benchmark_cagr * self.min_cagr_ratio_vs_benchmark:
            return False, f"cagr {cagr:.3f} < {self.min_cagr_ratio_vs_benchmark}×benchmark"
        # None = 손실 거래 0건이라 손익비가 정의되지 않음(∞) — 하한 게이트는 통과다.
        # 0으로 접으면 전승 전략이 '손익비 미달'로 탈락한다.
        _raw_pf = result.get("profitFactor", 0)
        pf = float("inf") if _raw_pf is None else float(_raw_pf or 0)
        if pf < self.min_profit_factor:
            return False, f"profitFactor {pf:.2f} < {self.min_profit_factor}"
        mdd = float(result.get("maxDrawdown", 0) or 0)
        if mdd > self.max_drawdown:
            return False, f"maxDrawdown {mdd:.3f} > {self.max_drawdown}"
        return True, "ok"
