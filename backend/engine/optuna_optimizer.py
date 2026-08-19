import copy
import itertools
import optuna
import logging
from typing import Any, Callable, Dict, Optional
from optuna.trial import TrialState

# Suppress excessively verbose optuna logs unless error
optuna.logging.set_verbosity(optuna.logging.WARNING)

from engine.grid_optimizer import (
    optimization_session,
    set_nested_value,
    satisfies_param_order_constraints,
    is_minimize_metric,
    target_sort_value,
)


class OptunaOptimizer:
    def __init__(self, engine):
        """
        engine: an instance of BacktestEngine
        """
        self.engine = engine

    def _define_search_space(self, trial: optuna.Trial, ranges: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts parameter ranges into Optuna suggest calls.
        Supports two formats:
          - dict with {type: "number", min, max, step} → suggest_int/suggest_float
          - list of values → suggest_categorical
        """
        params = {}
        for path, spec in ranges.items():
            if isinstance(spec, dict) and spec.get("type") == "number":
                lo, hi, step = spec["min"], spec["max"], spec.get("step", 1)
                # Use suggest_int for integer steps, suggest_float otherwise
                if isinstance(step, int) and isinstance(lo, int) and isinstance(hi, int):
                    params[path] = trial.suggest_int(path, lo, hi, step=step)
                else:
                    params[path] = trial.suggest_float(path, float(lo), float(hi), step=float(step))
            elif isinstance(spec, list) and len(spec) > 0:
                params[path] = trial.suggest_categorical(path, spec)
        return params

    def _check_constraints(self, params: Dict[str, Any]) -> bool:
        """
        Returns True if params satisfy semantic ordering constraints.
        e.g., shortMA must be < longMA within the same condition block.
        """
        return satisfies_param_order_constraints(params)

    def _warm_cache(self, base_request: Dict[str, Any]):
        """Pre-load symbol data into DataLoader cache before optimization loop.

        Phase1 프로세스 풀이 켜져 있으면 데이터는 워커가 들고 있으므로 부모 캐시 예열은 낭비다.
        """
        if getattr(self.engine, "phase1_pool_active", False):
            return
        symbols = base_request.get('symbols') or [base_request.get('symbol')]
        if not symbols or symbols == [None]:
            return
        for sym in symbols:
            try:
                self.engine.loader.load_symbol_data(sym)
            except Exception:
                pass

    def _categorical_trial_grid(self, ranges: Dict[str, Any], limit: int) -> list[Dict[str, Any]]:
        """Return deterministic categorical combinations when the space is small enough."""
        if limit <= 0 or not ranges:
            return []

        categorical_items = []
        for path, spec in ranges.items():
            if not (isinstance(spec, list) and len(spec) > 0):
                return []
            categorical_items.append((path, spec))

        combinations = []
        paths = [path for path, _ in categorical_items]
        value_lists = [values for _, values in categorical_items]
        for values in itertools.product(*value_lists):
            combinations.append(dict(zip(paths, values)))
            if len(combinations) >= limit:
                break
        return combinations

    def _holdout_validate(self, base_request: Dict[str, Any], best_params: Dict[str, Any]) -> Dict[str, Any] | None:
        """단일 홀드아웃(70/30) 검증 — 최적 파라미터로 전체 구간 1회 + 후반 30% 구간 1회를 더 돌린다.

        워크포워드(창을 굴리며 재학습)가 아니라 한 번 나누는 홀드아웃이다. 예전 이름
        `_walk_forward_validate`는 오명이었고, 워크포워드 분석(engine/walk_forward.py)이
        창마다 이 함수를 무조건 호출해 결과도 안 쓰는 백테스트를 창당 2회씩 낭비했다
        (2026-08-19 감사) — 그래서 optimize(holdout_validation=True)일 때만 실행한다.
        결과는 /optimize 리포트(ai/local_optimization_agent.py)의 '과적합 검증' 절에서만 쓴다.
        """
        req = copy.deepcopy(base_request)
        for path, value in best_params.items():
            set_nested_value(req, path, value)

        try:
            # 1. Full-period run to get actual date range
            full_result = self.engine.run_backtest(req)
            dates = full_result.get("dates", [])

            if len(dates) < 30:
                return None

            # 2. Split at 70% point
            split_idx = int(len(dates) * 0.7)
            split_date = dates[split_idx]

            # 3. Run on out-of-sample period (last 30%)
            oos_req = copy.deepcopy(req)
            oos_req['startDate'] = split_date
            oos_req['period'] = 'full'  # Override period to use explicit startDate
            oos_result = self.engine.run_backtest(oos_req)

            return {
                "full_period": f"{dates[0]} ~ {dates[-1]}",
                "oos_period": f"{split_date} ~ {dates[-1]}",
                "full_metrics": {
                    "cagr": full_result.get("cagr"),
                    "totalReturn": full_result.get("totalReturn"),
                    "maxDrawdown": full_result.get("maxDrawdown"),
                    "profitFactor": full_result.get("profitFactor"),
                    "winRate": full_result.get("winRate"),
                    "trades": full_result.get("trades"),
                },
                "oos_metrics": {
                    "cagr": oos_result.get("cagr"),
                    "totalReturn": oos_result.get("totalReturn"),
                    "maxDrawdown": oos_result.get("maxDrawdown"),
                    "profitFactor": oos_result.get("profitFactor"),
                    "winRate": oos_result.get("winRate"),
                    "trades": oos_result.get("trades"),
                }
            }
        except Exception as e:
            print(f"[OptunaOptimizer] Holdout validation failed: {e}")
            return None

    def optimize(
        self,
        base_request: Dict[str, Any],
        ranges: Dict[str, Any],
        target_metric: str = "cagr",
        n_trials: int = 50,
        progress_callback: Optional[Callable[[int, int, Optional[Dict[str, Any]]], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
        holdout_validation: bool = False,
    ) -> Dict[str, Any]:
        """
        Runs Bayesian optimization using Optuna to find the best parameters.
        Returns the top results sorted by `target_metric`.

        should_cancel: 협조적 취소 훅 — 시도(trial)마다 확인해 True면 study를 중단한다.
        holdout_validation: True면 최적 파라미터로 70/30 홀드아웃 검증(백테스트 2회 추가)을 덧붙인다.
            기본 False — 워크포워드처럼 결과를 쓰지 않는 호출부가 비용만 치르지 않게 한다.
        전 시도가 같은 날짜 범위를 쓰므로 엔진의 Phase1 캐시 세션을 열고 돈다.
        """
        with optimization_session(self.engine):
            return self._optimize(base_request, ranges, target_metric, n_trials,
                                  progress_callback, should_cancel, holdout_validation)

    def _optimize(self, base_request, ranges, target_metric, n_trials,
                  progress_callback, should_cancel, holdout_validation) -> Dict[str, Any]:
        if should_cancel is not None and should_cancel():
            return {"status": "cancelled", "message": "최적화 시작 전에 취소되었습니다."}
        # Pre-load all symbol data into memory before trial loop
        self._warm_cache(base_request)

        results_history = []
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 10
        last_timing: Dict[str, Any] = {}  # 최근 백테스트 단계별 소요 시간 (진행 모달 표시용)

        # Determine whether to maximize or minimize
        # Standard: higher is better for returns, win rate, sharpe. Lower is better for MDD.
        direction = "minimize" if is_minimize_metric(target_metric) else "maximize"

        def objective(trial: optuna.Trial):
            nonlocal consecutive_failures

            # 1. Suggest parameters for this trial
            perm = self._define_search_space(trial, ranges)

            # 2. Validate semantic constraints (e.g., shortMA < longMA)
            if not self._check_constraints(perm):
                raise optuna.exceptions.TrialPruned()

            # 3. Mutate request
            req = copy.deepcopy(base_request)
            for path, value in perm.items():
                try:
                    set_nested_value(req, path, value)
                except Exception as e:
                    print(f"[OptunaOptimizer] Failed to set path {path} to {value}: {e}")
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        raise RuntimeError(f"Aborting: {MAX_CONSECUTIVE_FAILURES} consecutive trial failures")
                    raise optuna.exceptions.TrialPruned()

            # 4. Run backtest
            try:
                res = self.engine.run_backtest(req)
                consecutive_failures = 0
                metric_val = res.get(target_metric, 0)
                if isinstance(res.get("timing"), dict):
                    last_timing.clear()
                    last_timing.update(res["timing"])

                # Keep track of detailed results for reporting
                results_history.append({
                    "iteration": trial.number,
                    "parameters": perm,
                    "metrics": {
                        "cagr": res.get("cagr"),
                        "maxDrawdown": res.get("maxDrawdown"),
                        "totalProfit": res.get("totalProfit"),
                        "totalReturn": res.get("totalReturn"),
                        "profitFactor": res.get("profitFactor"),
                        "sharpe": res.get("sharpe"),
                        "winRate": res.get("winRate"),
                        "calmar": res.get("calmar"),
                        "expectancy": res.get("expectancy"),
                        "trades": res.get("trades")
                    },
                    "target_value": metric_val
                })

                # 손익비 ∞(손실 거래 0건 → 엔진이 None)는 최대화에서 최상값 +inf로 보고한다.
                # None을 그대로 돌려주면 optuna가 "cast to float" 실패로 시도를 FAIL 처리해
                # 무손실 조합이 절대 1등이 될 수 없었다(2026-08-19 감사). 그 밖의 비수치는 시도 폐기.
                objective_value = target_sort_value(target_metric, metric_val)
                if objective_value in (float("inf"), float("-inf")) and not (
                    target_metric == "profitFactor" and metric_val is None
                ):
                    raise optuna.exceptions.TrialPruned()
                return objective_value

            except optuna.exceptions.TrialPruned:
                raise
            except Exception as e:
                print(f"[OptunaOptimizer] Trial {trial.number} failed: {e}")
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise RuntimeError(f"Aborting: {MAX_CONSECUTIVE_FAILURES} consecutive trial failures")
                raise optuna.exceptions.TrialPruned()

        # Create Optuna study. Enqueue small categorical spaces so short runs
        # cover deterministic candidates before the seeded sampler takes over.
        sampler = optuna.samplers.TPESampler(seed=42)
        study = optuna.create_study(direction=direction, sampler=sampler)
        for params in self._categorical_trial_grid(ranges, n_trials):
            study.enqueue_trial(params)

        # 창 하나의 최적화가 수 분간 침묵하지 않도록 시도(trial)마다 진행률을 보고한다.
        callbacks = []
        if progress_callback is not None:
            def _report(study: "optuna.Study", trial: "optuna.trial.FrozenTrial"):
                try:
                    progress_callback(len(study.trials), n_trials, dict(last_timing) or None)
                except Exception:
                    pass
            callbacks.append(_report)

        # 협조적 취소: 시도(=백테스트 1회)가 끝날 때마다 확인해 창 전체를 기다리지 않고 멈춘다.
        if should_cancel is not None:
            def _cancel_check(study: "optuna.Study", trial: "optuna.trial.FrozenTrial"):
                if should_cancel():
                    study.stop()
            callbacks.append(_cancel_check)

        try:
            study.optimize(objective, n_trials=n_trials, callbacks=callbacks or None)
        except RuntimeError as e:
            print(f"[OptunaOptimizer] Early abort: {e}")
            if not results_history:
                return {
                    "status": "error",
                    "message": str(e)
                }

        if should_cancel is not None and should_cancel():
            print(f"[OptunaOptimizer] cancelled after {len(study.trials)}/{n_trials} trials", flush=True)
            return {"status": "cancelled", "message": f"베이지안 최적화 {len(study.trials)}/{n_trials} 시도에서 취소되었습니다."}

        # Sort history to find top 5 (target_value None=손익비 ∞·NaN도 정렬이 죽지 않게 변환)
        reverse_sort = not is_minimize_metric(target_metric)
        results_history.sort(
            key=lambda x: target_sort_value(target_metric, x.get("target_value")),
            reverse=reverse_sort
        )

        if len(study.trials) == 0 or not results_history:
            return {
                "status": "error",
                "message": "All optimization trials failed."
            }

        best_trial = study.best_trial

        # Find the matching result entry for best_trial
        best_metrics = results_history[0]["metrics"]
        for entry in results_history:
            if entry["iteration"] == best_trial.number:
                best_metrics = entry["metrics"]
                break

        # Calculate parameter importances if possible (requires > 1 valid trial)
        importances = {}
        try:
            completed = [t for t in study.trials if t.state == TrialState.COMPLETE]
            if len(completed) > 1:
                importances = optuna.importance.get_param_importances(study)
        except Exception:
            pass

        # 단일 홀드아웃 검증(옵트인) — 백테스트 2회가 더 든다
        holdout = self._holdout_validate(base_request, best_trial.params) if holdout_validation else None

        return {
            "total_iterations": len(study.trials),
            "target_metric": target_metric,
            "best_parameters": best_trial.params,
            "best_metrics": best_metrics,
            "top_results": results_history[:5],
            "all_results": results_history,
            "param_importances": importances,
            "holdout_validation": holdout,
        }
