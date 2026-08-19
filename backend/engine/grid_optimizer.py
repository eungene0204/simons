import contextlib
import copy
import itertools
import math
from typing import Any, Callable, Dict, List, Optional

# 낮을수록 좋은 목표 지표 — 그리드·베이지안이 방향 판정을 공유한다.
MINIMIZE_METRICS = ("maxDrawdown", "mdd")


def optimization_session(engine):
    """최적화 한 번(=같은 날짜 범위의 백테스트 반복) 동안 엔진의 Phase1 산출물 캐시를 켠다.

    BacktestEngine이면 ``optimization_session()``, 테스트용 스텁 엔진처럼 없으면 no-op.
    결과는 캐시 유무와 무관하게 동일하다(engine/prep_cache.py 계약).
    """
    session = getattr(engine, "optimization_session", None)
    return session() if callable(session) else contextlib.nullcontext()


def is_minimize_metric(target_metric: str) -> bool:
    return target_metric in MINIMIZE_METRICS


def target_sort_value(target_metric: str, value: Any) -> float:
    """최적화 목표값을 정렬·비교 가능한 실수로 바꾼다.

    profitFactor는 손실 거래가 0건이면 엔진이 None(=∞, 0.0='이익 없음'과 구분)을 돌려준다.
    최대화 목표에서 ∞는 최상값이므로 +inf로 취급한다. 그 밖의 None·NaN·비수치는
    '최악'(최대화 -inf, 최소화 +inf)으로 둔다 — None을 정렬 키에 그대로 쓰면
    `'<' not supported between float and NoneType`로 창 전체가 죽는다(2026-08-19 감사).
    """
    worst = math.inf if is_minimize_metric(target_metric) else -math.inf
    if value is None:
        return math.inf if target_metric == "profitFactor" and not is_minimize_metric(target_metric) else worst
    try:
        f = float(value)
    except (TypeError, ValueError):
        return worst
    return worst if math.isnan(f) else f

# 그리드 탐색 하나가 매 워크포워드 윈도우마다 반복되므로 조합 폭주를 막기 위한 상한.
# 프론트엔드 예상 조합 수 안내(estimateGridChoiceCount)와 동일한 취지의 안전장치다.
MAX_GRID_COMBINATIONS = 500
MAX_VALUES_PER_PARAMETER = 50

# 같은 조건 블록 안에서 앞 파라미터 < 뒤 파라미터를 강제하는 의미 제약.
# 그리드·베이지안 최적화가 공유한다 (예: 단기MA >= 장기MA 조합은 의미가 없다).
PARAM_ORDER_CONSTRAINTS = [
    ("shortMA", "longMA"),
    ("fastPeriod", "slowPeriod"),
    ("shortPeriod", "longPeriod"),
]


def satisfies_param_order_constraints(params: Dict[str, Any]) -> bool:
    """
    파라미터 조합이 의미 제약(PARAM_ORDER_CONSTRAINTS)을 만족하면 True.
    "entry.conditions.0.params.shortMA" → prefix="entry.conditions.0.params", key="shortMA"
    처럼 같은 조건 prefix 안의 쌍에만 적용한다.
    """
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
            except ValueError:
                raise KeyError(f"Cannot traverse list index '{key}': not an integer")
            if idx < 0 or idx >= len(current):
                raise KeyError(f"Cannot traverse list index {idx}: out of range (len={len(current)})")
            current = current[idx]
            continue

        if key not in current:
            current[key] = {}
        current = current[key]

    final_key = keys[-1]
    if isinstance(current, list):
        try:
            idx = int(final_key)
        except ValueError:
            raise KeyError(f"Cannot set list index '{final_key}': not an integer")
        if idx < 0 or idx >= len(current):
            raise KeyError(f"Cannot set list index {idx}: out of range (len={len(current)})")
        current[idx] = value
    else:
        current[final_key] = value

def expand_range_spec(spec: Any) -> List[Any]:
    """
    파라미터 하나의 range 스펙을 실제 값 리스트로 변환한다.
    지원 형식:
      - 값 리스트 그대로 (categorical)
      - {"type": "number", "min", "max", "step"} → min..max를 step 간격으로 전개
    """
    if isinstance(spec, dict) and spec.get("type") == "number":
        lo, hi, step = spec["min"], spec["max"], spec.get("step", 1)
        if not step or step <= 0 or hi < lo:
            return [lo]
        is_int_step = isinstance(step, int) and isinstance(lo, int) and isinstance(hi, int)
        values = []
        current = lo
        while current <= hi + (1e-9 if not is_int_step else 0):
            values.append(int(round(current)) if is_int_step else round(current, 6))
            if len(values) >= MAX_VALUES_PER_PARAMETER:
                break
            current += step
        return values or [lo]
    if isinstance(spec, list):
        return spec
    return [spec]


def normalize_ranges(ranges: Dict[str, Any]) -> Dict[str, List[Any]]:
    """모든 파라미터의 range 스펙을 값 리스트 형태로 통일한다."""
    return {path: expand_range_spec(spec) for path, spec in ranges.items()}


def generate_permutations(ranges: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """
    Given a dict of parameter paths and their possible values,
    returns a list of dictionaries with all permutations.
    """
    if not ranges:
        return [{}]

    normalized = normalize_ranges(ranges)
    keys = list(normalized.keys())
    values_lists = [normalized[k] for k in keys]

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
        
    def optimize(self, base_request: Dict[str, Any], ranges: Dict[str, List[Any]], target_metric: str = "cagr", progress_callback: Optional[Callable[[int, int, Optional[Dict[str, Any]]], None]] = None, should_cancel: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
        """
        Runs the backtest for all permutations defined in `ranges`.
        Returns the top results sorted by `target_metric`.

        should_cancel: 협조적 취소 훅 — 조합마다 확인해 True면 즉시 중단한다.
        전 조합이 같은 날짜 범위를 쓰므로 엔진의 Phase1 캐시 세션을 열고 돈다.
        """
        with optimization_session(self.engine):
            return self._optimize(base_request, ranges, target_metric, progress_callback, should_cancel)

    def _optimize(self, base_request, ranges, target_metric, progress_callback, should_cancel) -> Dict[str, Any]:
        permutations = generate_permutations(ranges)
        if len(permutations) > MAX_GRID_COMBINATIONS:
            return {
                "status": "error",
                "message": f"조합 수({len(permutations)}개)가 상한({MAX_GRID_COMBINATIONS}개)을 초과했습니다. 파라미터 범위나 step을 조정해 주세요.",
            }

        # 의미 없는 조합(단기MA >= 장기MA 등)은 실행 전에 걸러낸다.
        permutations = [p for p in permutations if satisfies_param_order_constraints(p)]
        if not permutations:
            return {
                "status": "error",
                "message": "파라미터 순서 제약(예: 단기 < 장기)을 만족하는 조합이 없습니다. 범위를 조정해 주세요.",
            }

        results = []
        total = len(permutations)

        for i, perm in enumerate(permutations):
            # 협조적 취소: 조합(=백테스트 1회) 단위로 확인해 창 전체를 기다리지 않고 멈춘다.
            if should_cancel is not None and should_cancel():
                print(f"[Optimizer] cancelled at combination {i}/{total}", flush=True)
                return {"status": "cancelled", "message": f"그리드 탐색 {i}/{total} 조합에서 취소되었습니다."}

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

                # 창 하나의 전수 탐색이 수 분간 침묵하지 않도록 조합마다 진행률(+단계별 소요)을 보고한다.
                if progress_callback is not None:
                    try:
                        timing = res.get("timing") if isinstance(res.get("timing"), dict) else None
                        progress_callback(i + 1, total, timing)
                    except Exception:
                        pass

                # Extract the target metric
                metric_val = res.get(target_metric, 0)

                results.append({
                    "iteration": i + 1,
                    "parameters": perm,
                    "metrics": {
                        "cagr": res.get("cagr"),
                        "maxDrawdown": res.get("maxDrawdown") or res.get("mdd"),
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
            except Exception as e:
                print(f"[Optimizer] Backtest failed for perm {perm}: {e}")
                error_target = 999999.0 if target_metric == "maxDrawdown" else -999999.0
                results.append({
                    "iteration": i + 1,
                    "parameters": perm,
                    "error": str(e),
                    "target_value": error_target
                })

        # 전 조합이 실패하면 best_metrics가 None이 되어 호출부(walk_forward)가
        # 'NoneType' AttributeError로 죽는다 — 원인 메시지를 담아 명시적으로 실패시킨다.
        if results and all("error" in r for r in results):
            return {
                "status": "error",
                "message": f"모든 파라미터 조합의 백테스트가 실패했습니다: {results[0]['error']}",
            }

        # Sort results by the target metric descending (assuming higher is better, except for perhaps MDD)
        # Standardize sorting: higher is better for returns, win rate, sharpe. Lower is better for MDD.
        # target_value가 None(손익비 ∞)·NaN이어도 정렬이 죽지 않게 target_sort_value로 변환한다.
        reverse_sort = not is_minimize_metric(target_metric)
        results.sort(key=lambda x: target_sort_value(target_metric, x.get("target_value")), reverse=reverse_sort)
        
        return {
            "total_iterations": len(permutations),
            "target_metric": target_metric,
            "best_parameters": results[0]["parameters"] if results else None,
            "best_metrics": results[0]["metrics"] if results and "metrics" in results[0] else None,
            "top_results": results[:5], # Return top 5
            "all_results": results
        }
