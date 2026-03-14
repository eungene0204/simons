import copy
import optuna
import logging
from typing import Dict, Any
from optuna.trial import TrialState

# Suppress excessively verbose optuna logs unless error
optuna.logging.set_verbosity(optuna.logging.WARNING)

from engine.grid_optimizer import set_nested_value

# Semantic ordering constraints: first param must be < second param
# when both belong to the same condition block
PARAM_ORDER_CONSTRAINTS = [
    ("shortMA", "longMA"),
    ("fastPeriod", "slowPeriod"),
]


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
        # Group params by their condition prefix
        # "entry.conditions.0.params.shortMA" → prefix="entry.conditions.0.params", key="shortMA"
        by_prefix: Dict[str, Dict[str, Any]] = {}
        for path, value in params.items():
            parts = path.rsplit('.', 1)
            if len(parts) == 2:
                prefix, key = parts
                by_prefix.setdefault(prefix, {})[key] = value

        for group in by_prefix.values():
            for small_key, large_key in PARAM_ORDER_CONSTRAINTS:
                if small_key in group and large_key in group:
                    s_val, l_val = group[small_key], group[large_key]
                    if isinstance(s_val, (int, float)) and isinstance(l_val, (int, float)):
                        if s_val >= l_val:
                            return False
        return True

    def _warm_cache(self, base_request: Dict[str, Any]):
        """Pre-load symbol data into DataLoader cache before optimization loop."""
        symbols = base_request.get('symbols') or [base_request.get('symbol')]
        if not symbols or symbols == [None]:
            return
        for sym in symbols:
            try:
                self.engine.loader.load_symbol_data(sym)
            except Exception:
                pass

    def _walk_forward_validate(self, base_request: Dict[str, Any], best_params: Dict[str, Any]) -> Dict[str, Any] | None:
        """
        Run best params on the full period to get dates, then on the latter 30%
        as out-of-sample validation to detect overfitting.
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
            print(f"[OptunaOptimizer] Walk-forward validation failed: {e}")
            return None

    def optimize(self, base_request: Dict[str, Any], ranges: Dict[str, Any], target_metric: str = "cagr", n_trials: int = 50) -> Dict[str, Any]:
        """
        Runs Bayesian optimization using Optuna to find the best parameters.
        Returns the top results sorted by `target_metric`.
        """
        # Pre-load all symbol data into memory before trial loop
        self._warm_cache(base_request)

        results_history = []
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 10

        # Determine whether to maximize or minimize
        # Standard: higher is better for returns, win rate, sharpe. Lower is better for MDD.
        direction = "minimize" if target_metric in ["maxDrawdown", "mdd"] else "maximize"

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
                        "trades": res.get("trades")
                    },
                    "target_value": metric_val
                })

                return metric_val

            except Exception as e:
                print(f"[OptunaOptimizer] Trial {trial.number} failed: {e}")
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise RuntimeError(f"Aborting: {MAX_CONSECUTIVE_FAILURES} consecutive trial failures")
                raise optuna.exceptions.TrialPruned()

        # Create Optuna study
        study = optuna.create_study(direction=direction)
        try:
            study.optimize(objective, n_trials=n_trials)
        except RuntimeError as e:
            print(f"[OptunaOptimizer] Early abort: {e}")
            if not results_history:
                return {
                    "status": "error",
                    "message": str(e)
                }

        # Sort history to find top 5
        reverse_sort = target_metric not in ["maxDrawdown", "mdd"]
        default_val = -999999.0 if reverse_sort else 999999.0
        results_history.sort(
            key=lambda x: x.get("target_value") if x.get("target_value") is not None else default_val,
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

        # Walk-forward validation: detect overfitting
        walk_forward = self._walk_forward_validate(base_request, best_trial.params)

        return {
            "total_iterations": len(study.trials),
            "target_metric": target_metric,
            "best_parameters": best_trial.params,
            "best_metrics": best_metrics,
            "top_results": results_history[:5],
            "all_results": results_history,
            "param_importances": importances,
            "walk_forward": walk_forward
        }
