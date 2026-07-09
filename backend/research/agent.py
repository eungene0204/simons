"""
StrategyResearchAgent — orchestrator for the full research pipeline.

State machine:
    PENDING → GENERATING → PRESCREEN → ROBUSTNESS → OPTIMIZING
           → HOLDOUT_VAL → COMPLETED  (promotion is explicit user action)
           → FAILED / CANCELLED on error/abort

This module does NOT instantiate its own backtest engine. All heavy work
reuses the injected BacktestEngine, WalkForwardAnalyzer, OptunaOptimizer,
and VirtualTrader infrastructure.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import db as appdb  # 모듈 db와 conn 파라미터 db 이름 충돌 회피

from engine.optuna_optimizer import OptunaOptimizer

from research.events import EventEmitter
from research.generator import Candidate, CandidateGenerator
from research.prescreen import Prescreener, PrescreenResult
from research.promoter import Promoter
from research.robustness import RobustnessResult, RobustnessValidator
from research.safeguards import (
    AIModelLeakGuard,
    CircuitBreakerTripped,
    HoldoutGuard,
    HoldoutViolation,
    PrescreenGates,
)
from research.scoring import (
    ScoreWeights,
    composite_score,
    deflated_sharpe,
    robustness_score,
)
from research.search_space import get_search_space, space_cardinality

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    holdout_start: str                     # ISO date, locked at run creation
    seed: int = 42
    templates: Sequence[str] = field(default_factory=lambda: ["momentum", "mean_reversion"])
    universes: Sequence[Sequence[str]] = field(default_factory=lambda: [["KOSPI200"]])
    max_candidates: int = 100
    prescreen_sample_symbols: int = 50
    prescreen_top_k: int = 20
    optimize_top_k: int = 5
    optuna_trials: int = 50
    wfa_splits: int = 5
    wfa_trials: int = 20
    mc_iterations: int = 1000
    mc_block_size: int = 21
    ai_training_cutoff: Optional[str] = None
    weights: ScoreWeights = field(default_factory=ScoreWeights)
    prescreen_gates: PrescreenGates = field(default_factory=PrescreenGates)
    benchmark_cagr: float = 0.05
    years_prescreen: float = 3.0


class StrategyResearchAgent:
    def __init__(
        self,
        engine: Any,  # BacktestEngine
        db,
        config: AgentConfig,
        run_id: str,
    ):
        self.engine = engine
        self.db = db
        self.config = config
        self.run_id = run_id

        self.holdout = HoldoutGuard(config.holdout_start)
        self.ai_guard = (
            AIModelLeakGuard(config.ai_training_cutoff)
            if config.ai_training_cutoff
            else None
        )
        self.generator = CandidateGenerator(
            templates=config.templates,
            universes=config.universes,
            seed=config.seed,
        )
        self.prescreener = Prescreener(
            engine=engine,
            gates=config.prescreen_gates,
            holdout=self.holdout,
            ai_guard=self.ai_guard,
            sample_symbols=config.prescreen_sample_symbols,
            sample_seed=config.seed,
        )
        self.validator = RobustnessValidator(
            engine=engine,
            holdout=self.holdout,
            ai_guard=self.ai_guard,
            n_splits=config.wfa_splits,
            wfa_trials=config.wfa_trials,
            mc_iterations=config.mc_iterations,
            mc_block_size=config.mc_block_size,
            seed=config.seed,
        )
        self.optimizer = OptunaOptimizer(engine)
        self.promoter = Promoter(db)
        self.events = EventEmitter(db, run_id)

    # ─────────────────────────────────────────────────────────
    # Public entry
    # ─────────────────────────────────────────────────────────

    def run(self) -> None:
        t0 = time.time()
        try:
            candidates = self._generate()
            survivors = self._prescreen(candidates)
            robust = self._validate_robustness(survivors)
            optimized = self._optimize(robust)
            finals = self._holdout_validate(optimized)
            self._finalize(finals)
            self._set_status("COMPLETED")
            self.events.emit("run_completed", {"elapsed_sec": time.time() - t0})
        except CircuitBreakerTripped as e:
            self._fail(f"circuit_breaker: {e}")
        except HoldoutViolation as e:
            self._fail(f"holdout_violation: {e}")
        except Exception as e:  # noqa: BLE001
            logger.exception("[Agent] unexpected failure")
            self._fail(f"internal: {e}")

    # ─────────────────────────────────────────────────────────
    # Stage 1 — GENERATE
    # ─────────────────────────────────────────────────────────

    def _generate(self) -> List[Candidate]:
        self._set_status("GENERATING")
        self.events.emit("stage_start", {"stage": "GENERATING"})
        candidates = self.generator.generate(max_n=self.config.max_candidates)
        self._persist_candidates(candidates)
        self._update_run_counts(total=len(candidates))
        self.events.emit("generated", {"count": len(candidates)})
        return candidates

    def _persist_candidates(self, candidates: List[Candidate]) -> None:
        now = appdb.now()
        for c in candidates:
            try:
                self.db.execute(
                    """
                    INSERT INTO "ResearchCandidate"
                      (id, "runId", "dslHash", "dslJson", template, stage, "createdAt")
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        f"cand_{uuid.uuid4().hex[:16]}",
                        self.run_id,
                        c.dsl_hash,
                        json.dumps(c.parsed_dsl, ensure_ascii=False),
                        c.template,
                        "GENERATED",
                        now,
                    ),
                )
            except appdb.Error as e:
                logger.warning(f"[Agent] candidate persist skipped: {e}")
        self.db.commit()

    # ─────────────────────────────────────────────────────────
    # Stage 2 — PRESCREEN
    # ─────────────────────────────────────────────────────────

    def _prescreen(self, candidates: List[Candidate]) -> List[PrescreenResult]:
        self._set_status("PRESCREEN")
        self.events.emit("stage_start", {"stage": "PRESCREEN", "count": len(candidates)})
        results = self.prescreener.screen(candidates)

        for r in results:
            self._update_candidate(
                r.candidate.dsl_hash,
                stage="PRESCREEN_PASSED" if r.passed else "REJECTED",
                prescreenMetrics=json.dumps(r.metrics, ensure_ascii=False, default=str),
                rejectionReason=None if r.passed else r.reason,
            )
            self.events.emit(
                "prescreen",
                {"hash": r.candidate.dsl_hash[:8], "passed": r.passed, "reason": r.reason},
                candidate_id=r.candidate.dsl_hash,
            )

        survivors = [r for r in results if r.passed]
        survivors.sort(
            key=lambda r: self._provisional_score(r.metrics),
            reverse=True,
        )
        return survivors[: self.config.prescreen_top_k]

    @staticmethod
    def _provisional_score(m: Dict[str, Any]) -> float:
        return composite_score(m, robustness=0.5)

    # ─────────────────────────────────────────────────────────
    # Stage 3 — ROBUSTNESS
    # ─────────────────────────────────────────────────────────

    def _validate_robustness(self, survivors: List[PrescreenResult]) -> List[RobustnessResult]:
        self._set_status("ROBUSTNESS")
        self.events.emit("stage_start", {"stage": "ROBUSTNESS", "count": len(survivors)})
        cands = [s.candidate for s in survivors]
        results = self.validator.validate(cands)

        for r in results:
            self._update_candidate(
                r.candidate.dsl_hash,
                stage="ROBUSTNESS_PASSED" if r.passed else "REJECTED",
                wfaResult=json.dumps(_trim_wfa(r.wfa), ensure_ascii=False, default=str),
                mcResult=json.dumps(r.mc, ensure_ascii=False, default=str),
                robustnessScore=r.robustness_score,
                rejectionReason=None if r.passed else r.reason,
            )
            self.events.emit(
                "robustness",
                {
                    "hash": r.candidate.dsl_hash[:8],
                    "passed": r.passed,
                    "robustness": r.robustness_score,
                    "reason": r.reason,
                },
                candidate_id=r.candidate.dsl_hash,
            )

        passed = [r for r in results if r.passed]
        passed.sort(key=lambda r: r.robustness_score, reverse=True)
        return passed[: self.config.optimize_top_k]

    # ─────────────────────────────────────────────────────────
    # Stage 4 — OPTIMIZE
    # ─────────────────────────────────────────────────────────

    def _optimize(self, top: List[RobustnessResult]) -> List[Dict[str, Any]]:
        self._set_status("OPTIMIZING")
        self.events.emit("stage_start", {"stage": "OPTIMIZING", "count": len(top)})
        results: List[Dict[str, Any]] = []

        for rr in top:
            ranges = get_search_space(rr.candidate.template)
            if not ranges:
                self.events.emit(
                    "optimize_skipped",
                    {"hash": rr.candidate.dsl_hash[:8], "reason": "no search space"},
                    candidate_id=rr.candidate.dsl_hash,
                )
                results.append(
                    {
                        "robust": rr,
                        "request": self.holdout.clamp(rr.candidate.backtest_request),
                        "optuna": None,
                    }
                )
                continue

            # Cap trials by sqrt(space cardinality) to prevent overfit
            n_trials = min(
                self.config.optuna_trials,
                max(10, int(space_cardinality(ranges) ** 0.5)),
            )
            base_req = self.holdout.clamp(rr.candidate.backtest_request)

            try:
                optuna_res = self.optimizer.optimize(
                    base_request=base_req,
                    ranges=ranges,
                    target_metric="sharpe",
                    n_trials=n_trials,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[Agent] optuna failed for {rr.candidate.dsl_hash[:8]}: {e}")
                self.events.emit(
                    "optimize_error",
                    {"hash": rr.candidate.dsl_hash[:8], "error": str(e)},
                    candidate_id=rr.candidate.dsl_hash,
                )
                results.append({"robust": rr, "request": base_req, "optuna": None})
                continue

            best_params = optuna_res.get("best_parameters") or {}
            best_req = _apply_params(base_req, best_params)

            self._update_candidate(
                rr.candidate.dsl_hash,
                stage="OPTIMIZED",
                optunaBest=json.dumps(
                    {"params": best_params, "metrics": optuna_res.get("best_metrics")},
                    ensure_ascii=False,
                    default=str,
                ),
            )
            self.events.emit(
                "optimized",
                {
                    "hash": rr.candidate.dsl_hash[:8],
                    "params": best_params,
                    "metrics": optuna_res.get("best_metrics"),
                    "n_trials": n_trials,
                },
                candidate_id=rr.candidate.dsl_hash,
            )
            results.append({"robust": rr, "request": best_req, "optuna": optuna_res})

        return results

    # ─────────────────────────────────────────────────────────
    # Stage 5 — HOLDOUT_VAL (one-shot, locked)
    # ─────────────────────────────────────────────────────────

    def _holdout_validate(self, optimized: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        self._set_status("HOLDOUT_VAL")
        self.events.emit("stage_start", {"stage": "HOLDOUT_VAL", "count": len(optimized)})
        finals: List[Dict[str, Any]] = []

        for entry in optimized:
            rr: RobustnessResult = entry["robust"]
            req = self.holdout.build_holdout_request(entry["request"])

            try:
                holdout_bt = self.engine.run_backtest(req)
            except Exception as e:  # noqa: BLE001
                self._update_candidate(
                    rr.candidate.dsl_hash,
                    stage="REJECTED",
                    rejectionReason=f"holdout_error: {e}",
                )
                self.events.emit(
                    "holdout_error",
                    {"hash": rr.candidate.dsl_hash[:8], "error": str(e)},
                    candidate_id=rr.candidate.dsl_hash,
                )
                continue

            holdout_metrics = {
                "cagr": holdout_bt.get("cagr"),
                "sharpe": holdout_bt.get("sharpe"),
                "profitFactor": holdout_bt.get("profitFactor"),
                "maxDrawdown": holdout_bt.get("maxDrawdown"),
                "trades": holdout_bt.get("trades"),
                "totalReturn": holdout_bt.get("totalReturn"),
            }

            passed = self._holdout_passes(rr.base_metrics, holdout_metrics)
            entry["holdout_metrics"] = holdout_metrics
            entry["holdout_passed"] = passed

            # Recompute full robustness incl. holdout_passed flag + deflated sharpe
            is_sharpe = float(rr.base_metrics.get("sharpe") or 0.0)
            agg = (rr.wfa or {}).get("aggregate") or {}
            oos_sharpe = float(agg.get("avg_oos_sharpe") or 0.0)
            mc = rr.mc or {}
            mc_cagr = (mc.get("cagr") or {}) if isinstance(mc, dict) else {}
            full_robust = robustness_score(
                wfe=float((rr.wfa or {}).get("walk_forward_efficiency") or 0.0),
                is_sharpe=is_sharpe,
                oos_sharpe=oos_sharpe,
                mc_cagr_p05=float(mc_cagr.get("p05") or 0.0),
                mc_cagr_median=float(mc_cagr.get("median") or 0.0),
                holdout_passed=passed,
                regime_consistency=rr.regime_consistency,
            )
            final_score = composite_score(
                rr.base_metrics,
                robustness=full_robust,
                weights=self.config.weights,
            )
            dsr = deflated_sharpe(
                is_sharpe,
                n_trials=max(1, self.config.optuna_trials),
            )

            entry["composite_score"] = final_score
            entry["robustness_score"] = full_robust
            entry["deflated_sharpe"] = dsr

            if not passed or dsr < 0:
                reason = f"holdout_failed (passed={passed}, dsr={dsr:.2f})"
                self._update_candidate(
                    rr.candidate.dsl_hash,
                    stage="REJECTED",
                    holdoutMetrics=json.dumps(holdout_metrics, ensure_ascii=False, default=str),
                    compositeScore=final_score,
                    robustnessScore=full_robust,
                    deflatedSharpe=dsr,
                    rejectionReason=reason,
                )
                self.events.emit(
                    "holdout_rejected",
                    {"hash": rr.candidate.dsl_hash[:8], "reason": reason},
                    candidate_id=rr.candidate.dsl_hash,
                )
                continue

            self._update_candidate(
                rr.candidate.dsl_hash,
                stage="APPROVED",
                holdoutMetrics=json.dumps(holdout_metrics, ensure_ascii=False, default=str),
                compositeScore=final_score,
                robustnessScore=full_robust,
                deflatedSharpe=dsr,
            )
            self.events.emit(
                "holdout_passed",
                {
                    "hash": rr.candidate.dsl_hash[:8],
                    "score": final_score,
                    "robustness": full_robust,
                    "dsr": dsr,
                    "metrics": holdout_metrics,
                },
                candidate_id=rr.candidate.dsl_hash,
            )
            finals.append(entry)

        finals.sort(key=lambda e: e.get("composite_score", 0.0), reverse=True)
        return finals

    @staticmethod
    def _holdout_passes(base: Dict[str, Any], holdout: Dict[str, Any]) -> bool:
        h_sharpe = float(holdout.get("sharpe") or 0.0)
        h_cagr = float(holdout.get("cagr") or 0.0)
        b_cagr = float(base.get("cagr") or 0.0)
        if h_sharpe < 0.3:
            return False
        if (h_cagr > 0) != (b_cagr > 0):
            return False  # sign flip = regime-specific
        return True

    # ─────────────────────────────────────────────────────────
    # Stage 6 — FINALIZE (mark run, DO NOT auto-promote)
    # ─────────────────────────────────────────────────────────

    def _finalize(self, finals: List[Dict[str, Any]]) -> None:
        self.events.emit(
            "finalized",
            {
                "approved": len(finals),
                "top_hashes": [
                    f["robust"].candidate.dsl_hash[:8] for f in finals[:5]
                ],
            },
        )

    # ─────────────────────────────────────────────────────────
    # Infrastructure
    # ─────────────────────────────────────────────────────────

    def _set_status(self, status: str) -> None:
        self.events.transition(status)

    def _fail(self, message: str) -> None:
        now = appdb.now()
        self.db.execute(
            'UPDATE "ResearchRun" SET status = \'FAILED\', "errorMessage" = ?, "finishedAt" = ? WHERE id = ?',
            (message, now, self.run_id),
        )
        self.db.commit()
        self.events.emit("run_failed", {"message": message}, level="ERROR")

    def _update_run_counts(self, total: Optional[int] = None) -> None:
        if total is not None:
            self.db.execute(
                'UPDATE "ResearchRun" SET "totalCandidates" = ? WHERE id = ?',
                (total, self.run_id),
            )
            self.db.commit()

    def _update_candidate(self, dsl_hash: str, **fields: Any) -> None:
        if not fields:
            return
        cols = ", ".join(f'"{k}" = ?' for k in fields.keys())
        values = list(fields.values()) + [self.run_id, dsl_hash]
        try:
            self.db.execute(
                f'UPDATE "ResearchCandidate" SET {cols} WHERE "runId" = ? AND "dslHash" = ?',
                values,
            )
            self.db.commit()
        except appdb.Error as e:
            logger.warning(f"[Agent] candidate update failed: {e}")


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────


def _apply_params(request: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    from engine.grid_optimizer import set_nested_value

    req = copy.deepcopy(request)
    for path, value in params.items():
        try:
            set_nested_value(req, path, value)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[Agent] apply param {path}={value}: {e}")
    return req


def _trim_wfa(wfa: Dict[str, Any]) -> Dict[str, Any]:
    """Remove bulky equity arrays from WFA result before DB persistence."""
    if not isinstance(wfa, dict):
        return {}
    trimmed = {
        k: v
        for k, v in wfa.items()
        if k not in ("combined_equity", "combined_dates")
    }
    if "windows" in trimmed and isinstance(trimmed["windows"], list):
        trimmed["windows"] = [
            {k: v for k, v in w.items() if k not in ("oos_equity", "oos_dates")}
            for w in trimmed["windows"]
        ]
    return trimmed
