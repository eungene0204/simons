import pytest
import time
import os
import sys
import asyncio
from fastapi import Request, HTTPException

# Ensure backend directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import run_backtest, recent_executions
from schemas import BacktestRequest

async def _run_test_prevent_double_execution():
    # Clear cache before test
    recent_executions.clear()
    
    req_body = {
        "symbols": ["VALIDATION_STOCK"],
        "entry": {
            "logic": "AND",
            "conditions": [{"id": "price", "type": "indicator", "params": {"value": 50, "operator": ">"}}]
        },
        "exit": {"logic": "AND", "conditions": []},
        "risk": {"position_size_pct": 100}
    }
    
    trace_id = f"test_trace_{time.time()}"
    
    class MockRequest:
        def __init__(self, trace_id):
            self.headers = {"x-trace-id": trace_id}
            
    mock_req = MockRequest(trace_id)
    payload = BacktestRequest(**req_body)
    
    # First request should pass
    try:
        res1 = await run_backtest(mock_req, payload)
        assert res1 is not None
    except Exception as e:
        # It's fine if the engine errors out since we're just testing the idempotency
        if isinstance(e, HTTPException) and e.status_code == 429:
            pytest.fail("First request should not be rate-limited.")
            
    # Second request with same trace ID within TTL should return 429
    with pytest.raises(HTTPException) as exc_info:
        await run_backtest(mock_req, payload)
        
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "Duplicate request detected."

def test_prevent_double_execution():
    asyncio.run(_run_test_prevent_double_execution())

