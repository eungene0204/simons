from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from schemas import (
    BacktestRequest, BacktestResponse,
    MonteCarloRequest, MonteCarloResponse,
    OptimizationRequest, OptimizationResponse,
    VirtualMarketStepRequest, VirtualMarketStepResponse,
    WalkForwardRequest, WalkForwardResponse,
)
from backtest_engine import BacktestEngine
from engine.virtual_market import VirtualMarketEngine
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uvicorn
import time
import asyncio
import numpy as np

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
vm_engine = VirtualMarketEngine()

recent_executions = {}
EXECUTION_CACHE_TTL = 2  # seconds — 더블클릭 방지만, 의도적 재실행은 허용

@app.post("/backtest", response_model=BacktestResponse)
def run_backtest(http_req: Request, request: BacktestRequest):
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

@app.post("/optimize", response_model=OptimizationResponse)
def optimize_strategy(request: OptimizationRequest):
    print(f"\n[DEBUG] BACKEND: Received optimize request. Goal: {request.user_prompt}", flush=True)
    try:
        from ai.local_optimization_agent import LocalOptimizationAgent
        agent = LocalOptimizationAgent(engine)
        
        result = agent.run_optimization_loop(
            base_request=request.base_strategy.model_dump(),
            user_prompt=request.user_prompt,
            ranges=request.ranges,
            target_metric=request.target_metric,
            n_trials=request.n_trials
        )
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))
            
        return result
        
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        print(f"[DEBUG] OPTIMIZE ERROR:\n{err_msg}")
        raise HTTPException(status_code=500, detail=f"Optimization error: {repr(e)}")

@app.post("/monte-carlo", response_model=MonteCarloResponse)
def monte_carlo_simulation(request: MonteCarloRequest):
    print(f"\n[DEBUG] MONTE-CARLO: n={request.n_simulations}, block={request.block_size}, equity_len={len(request.equity)}", flush=True)
    try:
        from engine.monte_carlo import run_monte_carlo
        result = run_monte_carlo(
            equity=request.equity,
            initial_capital=request.initial_capital,
            n_simulations=request.n_simulations,
            block_size=request.block_size,
        )
        return result
    except Exception as e:
        import traceback
        print(f"[DEBUG] MONTE-CARLO ERROR:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Monte Carlo error: {repr(e)}")


@app.post("/walk-forward", response_model=WalkForwardResponse)
def walk_forward_analysis(request: WalkForwardRequest):
    print(f"\n[DEBUG] BACKEND: Walk-Forward Analysis request. splits={request.n_splits}, train={request.train_pct}, anchor={request.anchor}", flush=True)
    try:
        from engine.walk_forward import WalkForwardAnalyzer
        analyzer = WalkForwardAnalyzer(engine)
        result = analyzer.analyze(
            base_request=request.base_strategy.model_dump(),
            ranges=request.ranges,
            n_splits=request.n_splits,
            train_pct=request.train_pct,
            anchor=request.anchor,
            target_metric=request.target_metric,
            n_trials=request.n_trials,
        )
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[DEBUG] WALK-FORWARD ERROR:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Walk-forward error: {repr(e)}")


@app.post("/virtual-market/step", response_model=VirtualMarketStepResponse)
def virtual_market_step(request: VirtualMarketStepRequest):
    print(f"\n[DEBUG] VIRTUAL-MARKET: step for {request.symbols} on {request.virtual_date}", flush=True)
    try:
        result = vm_engine.step(
            symbols=request.symbols,
            base_prices=request.base_prices,
            entry_conditions=request.entry_conditions,
            exit_conditions=request.exit_conditions,
            virtual_date=request.virtual_date,
            scenario=request.scenario,
            history_days=request.history_days,
        )
        for sig in result["signals"]:
            if sig.get("entry_signal") or sig.get("exit_signal"):
                print(f"  SIGNAL: {sig['symbol']} entry={sig['entry_signal']} exit={sig['exit_signal']} close={sig['close']}", flush=True)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Virtual market error: {str(e)}")


@app.get("/stock/{symbol}/ohlcv")
def get_stock_ohlcv(symbol: str, limit: int = 1260):
    try:
        df = engine.loader.load_symbol_data(symbol)  # polars DataFrame
        df_tail = df.tail(limit)

        candles = []
        for row in df_tail.iter_rows(named=True):
            date_val = row["date"]
            date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
            candles.append({
                "date": date_str,
                "open": int(row["open"]),
                "high": int(row["high"]),
                "low": int(row["low"]),
                "close": int(row["close"]),
                "volume": int(row["volume"]),
            })

        last_close = int(df_tail["close"][-1])

        # 30일 연율화 변동성 (호가창 GBM 파라미터용)
        closes = df.tail(32)["close"].to_numpy().astype(float)
        if len(closes) >= 2:
            returns = np.diff(closes) / closes[:-1]
            sigma = float(np.std(returns) * np.sqrt(252))
        else:
            sigma = 0.3

        return {"candles": candles, "lastClose": last_close, "sigma": sigma}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Data for {symbol} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 알려진 주요 종목 검증용 (코드: (이름 일부, 시장))
_KNOWN_STOCKS = {
    "000100": ("유한양행", "KOSPI"),
    "005930": ("삼성전자", "KOSPI"),
    "000660": ("SK하이닉스", "KOSPI"),
    "035420": ("NAVER", "KOSPI"),
    "005380": ("현대자동차", "KOSPI"),
    "068270": ("셀트리온", "KOSPI"),
    "035720": ("카카오", "KOSPI"),
    "207940": ("삼성바이오로직스", "KOSPI"),
    "323410": ("카카오뱅크", "KOSPI"),
    "373220": ("LG에너지솔루션", "KOSPI"),
}


@app.post("/sync-stocks")
def sync_stocks():
    """FDR을 사용해서 korea-stocks.json을 최신·정확한 데이터로 업데이트한다.
    잘못된 KRX 직접 API 방식(krx-stocks.ts) 대신 이 endpoint를 사용할 것.
    """
    try:
        import FinanceDataReader as fdr
        import json
        from pathlib import Path
        from engine.sector_mapper import get_sector_from_industry

        stocks: list[dict] = []
        fetch_errors: list[str] = []

        def _fetch_kind(market_type: str, market_label: str) -> list[dict]:
            import requests, io, pandas as pd
            r = requests.get(
                "https://kind.krx.co.kr/corpgeneral/corpList.do",
                params={"method": "download", "searchType": "13", "marketType": market_type},
                timeout=15,
            )
            r.encoding = "euc-kr"
            df = pd.read_html(io.StringIO(r.text))[0]
            result = []
            for _, row in df.iterrows():
                symbol = str(row.get("종목코드", "")).strip().zfill(6)
                name = str(row.get("회사명", "")).strip()
                industry = str(row.get("업종", "") or "").strip()
                if not symbol or not name:
                    continue
                sector = get_sector_from_industry(symbol, industry, name)
                result.append({"symbol": symbol, "name": name, "market": market_label,
                                "sector": sector, "industry": industry})
            return result

        # 1순위: KRX KIND 공식 사이트 (올바른 이름-코드 매핑)
        try:
            kospi = _fetch_kind("stockMkt", "KOSPI")
            kosdaq = _fetch_kind("kosdaqMkt", "KOSDAQ")
            stocks = kospi + kosdaq
            print(f"[INFO] KRX KIND: KOSPI={len(kospi)}, KOSDAQ={len(kosdaq)}", flush=True)
        except Exception as e:
            fetch_errors.append(f"KRX KIND: {e}")
            print(f"[WARN] KRX KIND 실패, FDR fallback 시도: {e}", flush=True)

        # 2순위: FinanceDataReader StockListing (fallback)
        if not stocks:
            for market in ("KOSPI", "KOSDAQ"):
                try:
                    df = fdr.StockListing(market)
                    for _, row in df.iterrows():
                        symbol = str(row.get("Code", "")).strip().zfill(6)
                        name = str(row.get("Name", "")).strip()
                        industry = str(row.get("Industry", "") or "").strip()
                        if not symbol or not name:
                            continue
                        sector = get_sector_from_industry(symbol, industry, name)
                        stocks.append({"symbol": symbol, "name": name, "market": market,
                                       "sector": sector, "industry": industry})
                except Exception as e:
                    fetch_errors.append(f"FDR {market}: {e}")

        if not stocks:
            raise HTTPException(
                status_code=503,
                detail=f"FDR에서 종목 데이터를 가져올 수 없습니다: {fetch_errors}",
            )

        # 주요 종목 검증
        stock_map = {s["symbol"]: s for s in stocks}
        validation_warnings: list[str] = []
        for code, (expected_name_part, expected_market) in _KNOWN_STOCKS.items():
            entry = stock_map.get(code)
            if entry is None:
                validation_warnings.append(f"{code} ({expected_name_part}) 누락")
            elif entry["market"] != expected_market:
                validation_warnings.append(
                    f"{code} 시장 오류: expected={expected_market}, got={entry['market']}"
                )
            elif expected_name_part not in entry["name"]:
                validation_warnings.append(
                    f"{code} 이름 불일치: expected≈{expected_name_part}, got={entry['name']}"
                )

        if validation_warnings:
            print(f"[WARN] sync-stocks validation: {validation_warnings}", flush=True)

        # Atomic write (tmp → rename)
        base_path = Path(__file__).resolve().parent.parent
        stocks_path = base_path / "data" / "korea-stocks.json"
        tmp_path = stocks_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(stocks, f, ensure_ascii=False, indent=2)
        tmp_path.rename(stocks_path)

        kospi_cnt = sum(1 for s in stocks if s["market"] == "KOSPI")
        kosdaq_cnt = sum(1 for s in stocks if s["market"] == "KOSDAQ")
        print(f"[INFO] sync-stocks: {len(stocks)} stocks saved (KOSPI={kospi_cnt}, KOSDAQ={kosdaq_cnt})", flush=True)

        return {
            "success": True,
            "count": len(stocks),
            "kospi": kospi_cnt,
            "kosdaq": kosdaq_cnt,
            "validation_warnings": validation_warnings,
            "fetch_errors": fetch_errors,
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ERROR] sync-stocks: {traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=500, detail=f"sync-stocks 실패: {e}")



# ─── NL Strategy Parser ───────────────────────────────────────────────────────

class NLParseRequest(BaseModel):
    prompt: str
    backend: str = "mlx"  # "mlx" | "ollama"
    model: Optional[str] = None  # None = 기본값 사용

class NLParseResponse(BaseModel):
    parsed: dict
    backtest_request: dict
    symbol_count: int

_nl_parsers: dict = {}  # backend → NLStrategyParser (lazy singleton)

@app.post("/strategy/parse", response_model=NLParseResponse)
def parse_nl_strategy(request: NLParseRequest):
    """자연어 전략 설명을 ParsedStrategy + BacktestRequest로 변환"""
    print(f"\n[NL-PARSE] prompt='{request.prompt}', backend={request.backend}", flush=True)
    try:
        from engine.nl_parser import NLStrategyParser
        from engine.strategy_converter import to_backtest_request

        backend = request.backend
        if backend not in _nl_parsers:
            kwargs = {"backend": backend}
            if request.model:
                if backend == "mlx":
                    kwargs["model"] = request.model
                else:
                    kwargs["ollama_model"] = request.model
            _nl_parsers[backend] = NLStrategyParser(**kwargs)

        parser = _nl_parsers[backend]
        parsed = parser.parse(request.prompt)
        backtest_req = to_backtest_request(parsed)

        print(f"[NL-PARSE] filters={len(parsed.fundamental_filters)}, entry={len(parsed.entry_signals)}, symbols={len(backtest_req['symbols'])}", flush=True)

        return {
            "parsed": parsed.model_dump(),
            "backtest_request": backtest_req,
            "symbol_count": len(backtest_req["symbols"]),
        }
    except Exception as e:
        import traceback
        print(f"[NL-PARSE ERROR]\n{traceback.format_exc()}", flush=True)
        raise HTTPException(status_code=500, detail=f"NL parse error: {repr(e)}")


@app.post("/strategy/backtest-stream")
async def backtest_stream(request: BacktestRequest):
    """백테스트 진행 상황을 SSE로 스트리밍"""
    from fastapi.responses import StreamingResponse
    import threading, json
    from datetime import datetime

    result_holder: dict = {}
    error_holder: dict = {}

    def run_bt():
        try:
            result_holder["data"] = engine.run_backtest(request.model_dump())
        except Exception as exc:
            error_holder["error"] = str(exc)

    thread = threading.Thread(target=run_bt, daemon=True)

    async def generate():
        symbol_count = len(request.symbols)
        period = request.period or "5y"
        period_years = {"1y": 1, "3y": 3, "5y": 5, "full": 10}.get(period, 5)
        end_year = datetime.now().year
        start_year = end_year - period_years

        def emit(msg: str) -> str:
            return f"data: {json.dumps({'type': 'status', 'message': msg})}\n\n"

        # 백테스트 스레드 시작
        thread.start()

        # ── Step 1: 종목 데이터 로딩
        yield emit(f"{symbol_count:,}개 종목 데이터 로딩 중...")
        await asyncio.sleep(0.4)

        # ── Step 2: 재무 필터 정보
        filter_descs = []
        for c in request.entry.conditions:
            if c.type == "filter":
                op = c.params.get("operator", "")
                val = c.params.get("value", "")
                filter_descs.append(f"{c.id.upper()} {op} {val}")
        if filter_descs:
            yield emit(f"재무 필터 적용 중... ({', '.join(filter_descs[:4])})")
            await asyncio.sleep(0.5)

        # ── Step 3: 연도별 시뮬레이션
        time_per_year = 1.5

        for year in range(start_year, end_year):
            if not thread.is_alive():
                break
            yield emit(f"{year}년 시뮬레이션 중...")
            # time_per_year 동안 100ms 단위로 스레드 완료 체크
            elapsed = 0.0
            while thread.is_alive() and elapsed < time_per_year:
                await asyncio.sleep(0.1)
                elapsed += 0.1

        # ── Step 4: 집계 & 완료 대기
        if thread.is_alive():
            yield emit("거래 내역 집계 중...")
            await asyncio.sleep(0.3)
        if thread.is_alive():
            yield emit("성과 지표 계산 중...")
            thread.join(timeout=120)

        thread.join()

        # ── 결과 전송
        if "error" in error_holder:
            yield f"data: {json.dumps({'type': 'error', 'message': error_holder['error']})}\n\n"
        elif "data" in result_holder:
            yield emit("분석 완료!")
            await asyncio.sleep(0.3)
            yield f"data: {json.dumps({'type': 'result', 'data': result_holder['data']})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
