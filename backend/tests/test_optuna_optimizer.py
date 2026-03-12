import pytest
from unittest.mock import MagicMock
from engine.optuna_optimizer import OptunaOptimizer, set_nested_value
from ai.local_optimization_agent import LocalOptimizationAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class DummyEngine:
    """period 값에 비례하는 더미 백테스트 결과를 반환."""
    def __init__(self, fail_until=0):
        self.call_count = 0
        self.fail_until = fail_until  # 처음 N번은 강제 실패

    def run_backtest(self, req):
        self.call_count += 1
        if self.call_count <= self.fail_until:
            raise RuntimeError("Simulated backtest failure")

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


class AlwaysFailEngine:
    """항상 예외를 발생시키는 엔진."""
    def run_backtest(self, req):
        raise RuntimeError("Engine always fails")


def _base_request():
    return {
        "symbols": ["005930"],
        "entry": {
            "conditions": [
                {"id": "rsi_cross", "params": {"period": 14, "threshold": 30}}
            ]
        },
    }


def _ranges():
    return {
        "entry.conditions.0.params.period": [10, 14, 20],
        "entry.conditions.0.params.threshold": [25, 30],
    }


# ===========================================================================
# 1. set_nested_value — 에러를 명시적으로 raise 하는지 검증
# ===========================================================================

class TestSetNestedValue:
    def test_basic_dict_path(self):
        d = {"a": {"b": 1}}
        set_nested_value(d, "a.b", 2)
        assert d["a"]["b"] == 2

    def test_list_index_path(self):
        d = {"items": [{"val": 0}, {"val": 1}]}
        set_nested_value(d, "items.1.val", 99)
        assert d["items"][1]["val"] == 99

    def test_invalid_list_index_in_middle_raises(self):
        """리스트 중간 경로에서 잘못된 인덱스 → KeyError."""
        d = {"items": [{"val": 0}]}
        with pytest.raises(KeyError, match="Cannot traverse list index"):
            set_nested_value(d, "items.5.val", 99)

    def test_non_numeric_list_index_in_middle_raises(self):
        """리스트에 문자열 인덱스 접근 → KeyError."""
        d = {"items": [{"val": 0}]}
        with pytest.raises(KeyError, match="Cannot traverse list index"):
            set_nested_value(d, "items.abc.val", 99)

    def test_invalid_final_list_index_raises(self):
        """최종 키가 리스트이고 인덱스가 범위 밖 → KeyError."""
        d = {"items": [10, 20]}
        with pytest.raises(KeyError, match="Cannot set list index"):
            set_nested_value(d, "items.5", 99)

    def test_non_numeric_final_list_index_raises(self):
        """최종 키가 리스트이고 문자열 인덱스 → KeyError."""
        d = {"items": [10, 20]}
        with pytest.raises(KeyError, match="Cannot set list index"):
            set_nested_value(d, "items.abc", 99)

    def test_creates_intermediate_dicts(self):
        d = {}
        set_nested_value(d, "a.b.c", 42)
        assert d["a"]["b"]["c"] == 42


# ===========================================================================
# 2. OptunaOptimizer — metrics 키 통일 (maxDrawdown)
# ===========================================================================

class TestOptunaOptimizerMetricsKey:
    def test_metrics_use_maxDrawdown_key(self):
        """결과 metrics에 'mdd' 대신 'maxDrawdown' 키가 사용되는지 검증."""
        engine = DummyEngine()
        optimizer = OptunaOptimizer(engine)
        result = optimizer.optimize(_base_request(), _ranges(), target_metric="cagr", n_trials=6)

        for entry in result["top_results"]:
            assert "maxDrawdown" in entry["metrics"], "metrics에 'maxDrawdown' 키가 없음"
            assert "mdd" not in entry["metrics"], "metrics에 'mdd' 키가 남아 있음"

        assert "maxDrawdown" in result["best_metrics"]


# ===========================================================================
# 3. OptunaOptimizer — best_trial과 best_metrics 정합성
# ===========================================================================

class TestOptunaOptimizerBestTrialConsistency:
    def test_best_metrics_matches_best_parameters(self):
        """best_parameters의 period로 계산한 기대 cagr과 best_metrics.cagr이 일치."""
        engine = DummyEngine()
        optimizer = OptunaOptimizer(engine)
        result = optimizer.optimize(_base_request(), _ranges(), target_metric="cagr", n_trials=10)

        best_period = result["best_parameters"]["entry.conditions.0.params.period"]
        expected_cagr = float(best_period) * 1.5
        assert result["best_metrics"]["cagr"] == expected_cagr


# ===========================================================================
# 4. OptunaOptimizer — 연속 실패 시 early abort
# ===========================================================================

class TestOptunaOptimizerConsecutiveFailures:
    def test_all_trials_fail_returns_error(self):
        """모든 trial 실패 → status='error' 반환."""
        engine = AlwaysFailEngine()
        optimizer = OptunaOptimizer(engine)
        result = optimizer.optimize(_base_request(), _ranges(), target_metric="cagr", n_trials=15)
        assert result["status"] == "error"

    def test_partial_failure_then_recovery(self):
        """처음 3번 실패 후 회복 → 정상 결과 반환."""
        engine = DummyEngine(fail_until=3)
        optimizer = OptunaOptimizer(engine)
        result = optimizer.optimize(_base_request(), _ranges(), target_metric="cagr", n_trials=10)

        assert "status" not in result or result.get("status") != "error"
        assert len(result["top_results"]) > 0


# ===========================================================================
# 5. OptunaOptimizer — maxDrawdown minimize 방향 검증
# ===========================================================================

class TestOptunaOptimizerDirection:
    def test_maxDrawdown_minimized(self):
        """target_metric='maxDrawdown' → 낮은 값이 best."""
        engine = DummyEngine()
        optimizer = OptunaOptimizer(engine)
        result = optimizer.optimize(_base_request(), _ranges(), target_metric="maxDrawdown", n_trials=10)

        # DummyEngine: maxDrawdown = 100 - period, period=20 → mdd=80 (최솟값)
        assert result["best_parameters"]["entry.conditions.0.params.period"] == 20
        assert result["best_metrics"]["maxDrawdown"] == 80.0


# ===========================================================================
# 6. LocalOptimizationAgent — write_report: 빈 top_results 방어
# ===========================================================================

class TestLocalOptimizationAgentReport:
    def test_write_report_empty_top_results(self):
        """top_results가 빈 리스트일 때 크래시 없이 안내 메시지 반환."""
        engine = DummyEngine()
        agent = LocalOptimizationAgent(engine)
        result = agent.write_report(
            user_prompt="test",
            best_params={},
            top_results=[],
            target_metric="cagr",
            importances={},
            total_trials=0,
        )
        assert isinstance(result, str)
        assert "최적화 결과가 없습니다" in result

    def test_write_report_uses_maxDrawdown_key(self):
        """report에서 maxDrawdown 키를 올바르게 읽는지 검증."""
        engine = DummyEngine()
        agent = LocalOptimizationAgent(engine)
        top_results = [
            {
                "metrics": {
                    "cagr": 15.0,
                    "maxDrawdown": -12.5,
                    "winRate": 0.6,
                    "trades": 30,
                }
            }
        ]
        result = agent.write_report(
            user_prompt="MDD 최소화",
            best_params={"period": 14},
            top_results=top_results,
            target_metric="maxDrawdown",
            importances={},
            total_trials=10,
        )
        assert "-12.50%" in result
        assert "15.00%" in result

    def test_write_report_normal(self):
        """정상적인 top_results → 보고서에 핵심 지표 포함."""
        engine = DummyEngine()
        agent = LocalOptimizationAgent(engine)
        top_results = [
            {
                "metrics": {
                    "cagr": 25.0,
                    "maxDrawdown": -8.0,
                    "winRate": 0.55,
                    "trades": 100,
                }
            }
        ]
        result = agent.write_report(
            user_prompt="수익률 극대화",
            best_params={"entry.conditions.0.params.period": 20},
            top_results=top_results,
            target_metric="cagr",
            importances={"entry.conditions.0.params.period": 0.8},
            total_trials=50,
        )
        assert "25.00%" in result
        assert "Period" in result
        assert "80.0% 기여도" in result


# ===========================================================================
# 7. LocalOptimizationAgent — run_optimization_loop 빈 ranges 방어
# ===========================================================================

class TestLocalOptimizationAgentLoop:
    def test_empty_ranges_returns_error(self):
        engine = DummyEngine()
        agent = LocalOptimizationAgent(engine)
        result = agent.run_optimization_loop(
            base_request=_base_request(),
            user_prompt="test",
            ranges={},
            target_metric="cagr",
            n_trials=5,
        )
        assert result["status"] == "error"

    def test_full_loop_success(self):
        """정상 루프 → status='success', report 포함."""
        engine = DummyEngine()
        agent = LocalOptimizationAgent(engine)
        result = agent.run_optimization_loop(
            base_request=_base_request(),
            user_prompt="CAGR 극대화",
            ranges=_ranges(),
            target_metric="cagr",
            n_trials=10,
        )
        assert result["status"] == "success"
        assert "report" in result
        assert len(result["report"]) > 0
        assert "maxDrawdown" in result["best_metrics"]
