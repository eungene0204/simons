from fastapi import FastAPI, HTTPException
from schemas import BacktestRequest, BacktestResponse
from backtest_engine import BacktestEngine
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = BacktestEngine()

@app.post("/backtest", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest):
    print(f"\n[DEBUG] BACKEND: Received backtest request for symbols: {request.symbols}")
    print(f"[DEBUG] Request Data: {request.model_dump_json(indent=2)}")
    try:
        # Convert Pydantic to dict for engine
        result = engine.run_backtest(request.model_dump())
        print(f"[DEBUG] [{datetime.now().isoformat()}] BACKEND: Backtest Success. Total Return: {result.get('totalReturn', 0):.2f}%")
        signals = result.get('signals', [])
        print(f"[DEBUG] Found {len(signals)} total signals.")
        for i, s in enumerate(signals[:20]):
            print(f"  Signal {i}: {s['symbol']} on {s['date']} ({s['type']})")
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engine error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
