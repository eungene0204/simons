import copy
import optuna
import logging
from typing import Dict, Any, List, Optional
from optuna.trial import TrialState

# Suppress excessively verbose optuna logs unless error
optuna.logging.set_verbosity(optuna.logging.WARNING)

def set_nested_value(d: Dict[str, Any], path: str, value: Any):
    """
    Sets a value in a nested dictionary using a dot-separated path.
    Example: set_nested_value(req, 'entry.conditions.0.params.period', 14)
    """
    keys = path.split('.')
    current = d
    for i, key in enumerate(keys[:-1]):
        if isinstance(current, list):
            try:
                idx = int(key)
                current = current[idx]
                continue
            except (ValueError, IndexError) as e:
                raise KeyError(f"Cannot traverse list index '{key}' at path '{path}': {e}")

        if key not in current:
            current[key] = {}
        current = current[key]
        
    final_key = keys[-1]
    if isinstance(current, list):
        try:
            current[int(final_key)] = value
        except (ValueError, IndexError) as e:
            raise KeyError(f"Cannot set list index '{final_key}' at path '{path}': {e}")
    else:
        current[final_key] = value


class OptunaOptimizer:
    def __init__(self, engine):
        """
        engine: an instance of BacktestEngine
        """
        self.engine = engine
        
    def _define_search_space(self, trial: optuna.Trial, ranges: Dict[str, List[Any]]) -> Dict[str, Any]:
        """
        Converts the discrete lists of possible values into Optuna suggest options.
        Since we don't strictly know if they are categorical or numerical ranges from the old schema, 
        we treat them as categorical choices for safe backward compatibility.
        """
        params = {}
        for path, values in ranges.items():
            if not values:
                continue
            
            # If values is a list of numbers, we could use suggest_int or suggest_float,
            # but suggest_categorical is safest for arbitrary step lists (e.g. [10, 14, 20])
            params[path] = trial.suggest_categorical(path, values)
            
        return params

    def optimize(self, base_request: Dict[str, Any], ranges: Dict[str, List[Any]], target_metric: str = "cagr", n_trials: int = 50) -> Dict[str, Any]:
        """
        Runs Bayesian optimization using Optuna to find the best parameters.
        Returns the top results sorted by `target_metric`.
        """
        
        results_history = []
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 10

        # Determine whether to maximize or minimize
        # Standard: higher is better for returns, win rate, sharpe. Lower is better for MDD.
        direction = "minimize" if target_metric == "maxDrawdown" else "maximize"

        def objective(trial: optuna.Trial):
            nonlocal consecutive_failures

            # 1. Suggest parameters for this trial
            perm = self._define_search_space(trial, ranges)

            # 2. Mutate request
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

            # 3. Run backtest
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
                        "winRate": res.get("winRate"),
                        "profitFactor": res.get("profitFactor"),
                        "sharpe": res.get("sharpe"),
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
        reverse_sort = target_metric != "maxDrawdown"
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

        return {
            "total_iterations": len(study.trials),
            "target_metric": target_metric,
            "best_parameters": best_trial.params,
            "best_metrics": best_metrics,
            "top_results": results_history[:5],
            "all_results": results_history,
            "param_importances": importances
        }
