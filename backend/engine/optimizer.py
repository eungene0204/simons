import copy
import itertools
from typing import Dict, Any, List

def set_nested_value(d: Dict[str, Any], path: str, value: Any):
    """
    Sets a value in a nested dictionary using a dot-separated path.
    Example: set_nested_value(req, "entry.conditions.0.params.period", 14)
    """
    keys = path.split('.')
    current = d
    for i, key in enumerate(keys[:-1]):
        # Handle list indices
        if isinstance(current, list):
            try:
                idx = int(key)
                current = current[idx]
                continue
            except ValueError:
                pass
                
        if key not in current:
            current[key] = {}
        current = current[key]
        
    final_key = keys[-1]
    if isinstance(current, list):
        try:
            current[int(final_key)] = value
        except ValueError:
            pass
    else:
        current[final_key] = value

def generate_permutations(ranges: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """
    Given a dict of parameter paths and their possible values,
    returns a list of dictionaries with all permutations.
    """
    if not ranges:
        return [{}]
        
    keys = list(ranges.keys())
    values_lists = [ranges[k] for k in keys]
    
    permutations = []
    for combination in itertools.product(*values_lists):
        perm = dict(zip(keys, combination))
        permutations.append(perm)
        
    return permutations

class StrategyOptimizer:
    def __init__(self, engine):
        """
        engine: an instance of BacktestEngine
        """
        self.engine = engine
        
    def optimize(self, base_request: Dict[str, Any], ranges: Dict[str, List[Any]], target_metric: str = "cagr") -> Dict[str, Any]:
        """
        Runs the backtest for all permutations defined in `ranges`.
        Returns the top results sorted by `target_metric`.
        """
        permutations = generate_permutations(ranges)
        results = []
        
        for i, perm in enumerate(permutations):
            # Create a deep copy of the base request to mutate
            req = copy.deepcopy(base_request)
            
            # Apply all parameter overrides for this permutation
            for path, value in perm.items():
                try:
                    set_nested_value(req, path, value)
                except Exception as e:
                    print(f"[Optimizer] Failed to set path {path} to {value}: {e}")
            
            try:
                # Run backtest
                res = self.engine.run_backtest(req)
                
                # Extract the target metric
                metric_val = res.get(target_metric, 0)
                
                results.append({
                    "iteration": i + 1,
                    "parameters": perm,
                    "metrics": {
                        "cagr": res.get("cagr"),
                        "mdd": res.get("maxDrawdown"),
                        "winRate": res.get("winRate"),
                        "profitFactor": res.get("profitFactor"),
                        "sharpe": res.get("sharpe"),
                        "trades": res.get("trades")
                    },
                    "target_value": metric_val
                })
            except Exception as e:
                print(f"[Optimizer] Backtest failed for perm {perm}: {e}")
                error_target = 999999.0 if target_metric == "maxDrawdown" else -999999.0
                results.append({
                    "iteration": i + 1,
                    "parameters": perm,
                    "error": str(e),
                    "target_value": error_target
                })

        # Sort results by the target metric descending (assuming higher is better, except for perhaps MDD)
        # Standardize sorting: higher is better for returns, win rate, sharpe. Lower is better for MDD.
        reverse_sort = target_metric != "maxDrawdown"
        
        results.sort(key=lambda x: x.get("target_value", -999999.0) if reverse_sort else x.get("target_value", 999999.0), reverse=reverse_sort)
        
        return {
            "total_iterations": len(permutations),
            "target_metric": target_metric,
            "best_parameters": results[0]["parameters"] if results else None,
            "best_metrics": results[0]["metrics"] if results and "metrics" in results[0] else None,
            "top_results": results[:5], # Return top 5
            "all_results": results
        }
