import pytest
from engine.grid_optimizer import StrategyOptimizer, set_nested_value, generate_permutations

class DummyEngine:
    def __init__(self):
        self.calls = []

    def run_backtest(self, req):
        self.calls.append(req)
        # Return dummy metrics based on length of params to verify sorting
        # Let's say we prefer higher period values for dummy CAGR
        cagr = 0.0
        try:
            period = req['entry']['conditions'][0]['params']['period']
            cagr = float(period) * 1.5
        except:
            pass
            
        return {
            "cagr": cagr,
            "maxDrawdown": 10.0,
            "winRate": 0.5,
            "profitFactor": 1.1,
            "sharpe": 1.0,
            "trades": 100
        }

def test_set_nested_value():
    req = {"entry": {"conditions": [{"params": {"period": 10}}]}}
    set_nested_value(req, "entry.conditions.0.params.period", 20)
    assert req["entry"]["conditions"][0]["params"]["period"] == 20

    # Test creating new paths
    req2 = {}
    set_nested_value(req2, "risk.stop_loss_pct", 5.0)
    assert req2["risk"]["stop_loss_pct"] == 5.0

def test_generate_permutations():
    ranges = {
        "param1": [1, 2],
        "param2": ["a", "b"]
    }
    perms = generate_permutations(ranges)
    assert len(perms) == 4
    assert {"param1": 1, "param2": "a"} in perms
    assert {"param1": 2, "param2": "b"} in perms

def test_strategy_optimizer():
    engine = DummyEngine()
    optimizer = StrategyOptimizer(engine)
    
    base_req = {
        "symbols": ["AAPL"],
        "entry": {
            "conditions": [
                {
                    "id": "rsi_cross",
                    "params": {"period": 14, "threshold": 30}
                }
            ]
        }
    }
    
    ranges = {
        "entry.conditions.0.params.period": [10, 14, 20],
        "entry.conditions.0.params.threshold": [25, 30]
    }
    
    result = optimizer.optimize(base_req, ranges, target_metric="cagr")
    
    # 3 periods * 2 thresholds = 6 permutations
    assert result["total_iterations"] == 6
    assert len(engine.calls) == 6
    
    # Check if the mutations were applied
    periods_tested = [call["entry"]["conditions"][0]["params"]["period"] for call in engine.calls]
    assert 10 in periods_tested
    assert 20 in periods_tested
    
    # Check sorting: highest cagr should be period 20, which gives 20 * 1.5 = 30.0
    best_cagr = result["best_metrics"]["cagr"]
    assert best_cagr == 30.0
    assert result["best_parameters"]["entry.conditions.0.params.period"] == 20
