from fastapi import FastAPI, HTTPException, Request
from schemas import BacktestRequest, BacktestResponse
from backtest_engine import BacktestEngine
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uvicorn
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = BacktestEngine()

recent_executions = {}
EXECUTION_CACHE_TTL = 2  # seconds — 더블클릭 방지만, 의도적 재실행은 허용

@app.post("/backtest", response_model=BacktestResponse)
async def run_backtest(http_req: Request, request: BacktestRequest):
    trace_id = http_req.headers.get("x-trace-id")
    current_time = time.time()
    
    if trace_id:
        if trace_id in recent_executions:
            if current_time - recent_executions[trace_id] < EXECUTION_CACHE_TTL:
                print(f"[DEBUG] BACKEND: Rejecting duplicate request with trace ID: {trace_id}", flush=True)
                raise HTTPException(status_code=429, detail="Duplicate request detected.")
        recent_executions[trace_id] = current_time
        
        # Cleanup old trace ids
        keys_to_remove = [k for k, v in recent_executions.items() if current_time - v >= EXECUTION_CACHE_TTL]
        for k in keys_to_remove:
            del recent_executions[k]

    print(f"\n[DEBUG] BACKEND: Received backtest request for symbols: {request.symbols}", flush=True)
    # The debug file logging was removed as it was accessing properties that no longer exist (entry.logic).
    try:
        # Convert Pydantic to dict for engine
        start_time = time.time()
        result = engine.run_backtest(request.model_dump())
        end_time = time.time()
        result['executionTime'] = end_time - start_time

        print(f"[DEBUG] [{datetime.now().isoformat()}] BACKEND: Backtest Success. Total Return: {result.get('totalReturn', 0):.2f}%", flush=True)
        print(f"[DEBUG] CAGR: {result.get('cagr', 0):.2f}%, PF: {result.get('profitFactor', 0):.2f}, Win Rate: {result.get('winRate', 0):.2f}%, Trades: {result.get('trades', 0)}", flush=True)
        signals = result.get('signals', [])
        print(f"[DEBUG] Found {len(signals)} total signals.", flush=True)
        print(f"[DEBUG] Found {len(signals)} total signals.", flush=True)
        for i, s in enumerate(signals[:20]):
            print(f"  Signal {i}: {s['symbol']} on {s['date']} ({s['type']})", flush=True)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engine error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
