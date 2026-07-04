import pytest
from engine.grid_optimizer import (
    StrategyOptimizer,
    expand_range_spec,
    generate_permutations,
    normalize_ranges,
    MAX_GRID_COMBINATIONS,
)


class DummyEngine:
    """period 값에 비례하는 더미 백테스트 결과를 반환."""
    def run_backtest(self, req):
        period = 14
        try:
            period = req["entry"]["conditions"][0]["params"]["period"]
        except (KeyError, IndexError, TypeError):
            pass

        return {
            "cagr": float(period) * 1.5,
            "maxDrawdown": 100.0 - float(period),
            "winRate": 0.5,
            "profitFactor": 1.2,
            "sharpe": 1.0,
            "trades": 50,
        }


def _base_request():
    return {
        "symbols": ["005930"],
        "entry": {
            "conditions": [
                {"id": "rsi_cross", "params": {"period": 14, "threshold": 30}}
            ]
        },
    }


# ===========================================================================
# 1. expand_range_spec — 리스트 / {type, min, max, step} 두 형식 모두 지원
# ===========================================================================

class TestExpandRangeSpec:
    def test_list_spec_passthrough(self):
        assert expand_range_spec([10, 14, 20]) == [10, 14, 20]

    def test_number_spec_integer_step(self):
        spec = {"type": "number", "min": 10, "max": 20, "step": 5}
        assert expand_range_spec(spec) == [10, 15, 20]

    def test_number_spec_float_step(self):
        spec = {"type": "number", "min": 1.0, "max": 2.0, "step": 0.5}
        assert expand_range_spec(spec) == [1.0, 1.5, 2.0]

    def test_number_spec_invalid_step_falls_back_to_min(self):
        spec = {"type": "number", "min": 10, "max": 20, "step": 0}
        assert expand_range_spec(spec) == [10]

    def test_number_spec_caps_value_count(self):
        spec = {"type": "number", "min": 0, "max": 100000, "step": 1}
        values = expand_range_spec(spec)
        assert len(values) <= 50


# ===========================================================================
# 2. generate_permutations — {type,min,max,step} 스펙도 조합에 포함되는지
# ===========================================================================

class TestGeneratePermutations:
    def test_list_ranges(self):
        ranges = {"a": [1, 2], "b": [10, 20]}
        perms = generate_permutations(ranges)
        assert len(perms) == 4
        assert {"a": 1, "b": 10} in perms

    def test_number_spec_ranges(self):
        ranges = {
            "entry.conditions.0.params.period": {"type": "number", "min": 10, "max": 20, "step": 5},
        }
        perms = generate_permutations(ranges)
        assert perms == [
            {"entry.conditions.0.params.period": 10},
            {"entry.conditions.0.params.period": 15},
            {"entry.conditions.0.params.period": 20},
        ]

    def test_empty_ranges_returns_single_empty_permutation(self):
        assert generate_permutations({}) == [{}]

    def test_normalize_ranges_mixed_shapes(self):
        ranges = {
            "a": [1, 2],
            "b": {"type": "number", "min": 0, "max": 10, "step": 5},
        }
        normalized = normalize_ranges(ranges)
        assert normalized == {"a": [1, 2], "b": [0, 5, 10]}


# ===========================================================================
# 3. StrategyOptimizer — 그리드 탐색 실행 및 상한 가드
# ===========================================================================

class TestStrategyOptimizer:
    def test_finds_best_parameters(self):
        engine = DummyEngine()
        optimizer = StrategyOptimizer(engine)
        ranges = {"entry.conditions.0.params.period": [10, 14, 20]}
        result = optimizer.optimize(_base_request(), ranges, target_metric="cagr")

        assert result["total_iterations"] == 3
        assert result["best_parameters"]["entry.conditions.0.params.period"] == 20
        assert result["best_metrics"]["cagr"] == 30.0

    def test_minimizes_maxDrawdown_when_requested(self):
        engine = DummyEngine()
        optimizer = StrategyOptimizer(engine)
        ranges = {"entry.conditions.0.params.period": [10, 14, 20]}
        result = optimizer.optimize(_base_request(), ranges, target_metric="maxDrawdown")

        # maxDrawdown = 100 - period → period=20이 최솟값(80)
        assert result["best_parameters"]["entry.conditions.0.params.period"] == 20
        assert result["best_metrics"]["maxDrawdown"] == 80.0

    def test_number_spec_range_is_expanded_before_running(self):
        engine = DummyEngine()
        optimizer = StrategyOptimizer(engine)
        ranges = {
            "entry.conditions.0.params.period": {"type": "number", "min": 10, "max": 20, "step": 5},
        }
        result = optimizer.optimize(_base_request(), ranges, target_metric="cagr")

        assert result["total_iterations"] == 3
        assert result["best_parameters"]["entry.conditions.0.params.period"] == 20

    def test_exceeds_combination_cap_returns_error(self):
        engine = DummyEngine()
        optimizer = StrategyOptimizer(engine)
        # 두 파라미터 각각 30개 값 → 30*30=900 조합, MAX_GRID_COMBINATIONS(500) 초과
        ranges = {
            "a": {"type": "number", "min": 0, "max": 29, "step": 1},
            "b": {"type": "number", "min": 0, "max": 29, "step": 1},
        }
        assert 30 * 30 > MAX_GRID_COMBINATIONS
        result = optimizer.optimize(_base_request(), ranges, target_metric="cagr")

        assert result["status"] == "error"
        assert "상한" in result["message"]
