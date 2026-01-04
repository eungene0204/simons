from fastapi import FastAPI, HTTPException
from schemas import BacktestRequest, BacktestResponse
from backtest_engine import BacktestEngine
import uvicorn

app = FastAPI()
engine = BacktestEngine()

@app.post("/backtest", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest):
    try:
        # Convert Pydantic to dict for engine
        result = engine.run_backtest(request.dict())
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engine error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
