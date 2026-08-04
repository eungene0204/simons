from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# 네이티브 스레드풀 가드 — polars/numpy/XGBoost가 스레드풀을 초기화하기 전(아래 무거운
# import 이전)에 반드시 설정해야 한다. 워크포워드처럼 백테스트를 백그라운드 스레드에서
# 대량 실행하면 polars rayon latch 데드락이나 OpenMP 중복 로드 segfault로 워커가 죽어
# 스트림이 끊기고 클라이언트는 "network error"만 보게 된다. 프로덕션 docker-compose는
# 이 값을 걸어두지만 로컬 dev:backend 런처엔 없어, 여기서 기본값으로 보강한다.
# (shell/.env가 이미 지정했으면 그 값을 존중 — setdefault)
os.environ.setdefault("POLARS_MAX_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from schemas import (
    BacktestRequest, BacktestResponse,
    OptimizationRequest, OptimizationResponse,
    WalkForwardRequest, WalkForwardResponse,
)
from backtest_engine import BacktestEngine
from engine.market_data import market_data_provider, delisted_store
from engine.dart_client import fetch_recent_delisting_notices
from engine.listing_status import (
    ListingStatus, sync_from_delisted_store, sync_from_dart_notices,
    get_stocks_by_status, update_stock_listing_status, write_audit_log,
)
from engine.live_signal_utils import prepare_signal_dataframe
from engine.virtual_trader import VirtualTrader
from engine.vi_utils import build_vi_display
from nl_cache import nl_cache_key
from stream_progress import build_backtest_stream_status, simulation_phase_label
from engine.watchdog import (
    BacktestTimeoutError,
    backtest_timeout_s,
    run_with_timeout as watchdog_run_with_timeout,
    timeout_message as backtest_timeout_message,
    walk_forward_timeout_message,
    walk_forward_timeout_s,
)
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import uvicorn
import time
import asyncio
import threading
import numpy as np
import requests
import json
import re
from urllib.parse import unquote
from fastapi.responses import StreamingResponse
from market_cap import normalize_market_cap

# 외부 API 호출에 사용하는 공용 requests.Session — keep-alive로 TLS handshake 비용 제거.
_http_session = requests.Session()
_http_session_adapter = requests.adapters.HTTPAdapter(
    pool_connections=20, pool_maxsize=50, max_retries=0
)
_http_session.mount("https://", _http_session_adapter)
_http_session.mount("http://", _http_session_adapter)

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    preload_nl_parser()
    preload_summarize_model()
    await startup()
    log_universe_status_on_startup()

    # news_v2 — best-effort scheduler bootstrap. Disabled if NEWSV2_ENABLED=false
    # or if APScheduler isn't installed.
    try:
        from news_v2.config import get_settings
        if get_settings().enabled:
            # fresh postgres/sqlite 스키마 초기화(idempotent) — alembic 없음, create_all이 단일 소스
            from news_v2.db import init_models
            await init_models()
        from news_v2.scheduler import start_scheduler, stop_scheduler
        start_scheduler()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("news_v2 scheduler startup skipped: %s", e)
        stop_scheduler = lambda: None  # noqa: E731

    yield

    try:
        stop_scheduler()
    except Exception:
        pass
    await shutdown()

app = FastAPI(lifespan=lifespan)

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

# Strategy Research Agent routes (premium gated)
from api.research_routes import router as research_router
app.include_router(research_router)

# News Impact AI Agent routes
from api.news_routes import router as news_router
app.include_router(news_router)

# Context-aware Strategy Advisor Agent routes
from api.advisor_routes import router as advisor_router
app.include_router(advisor_router)

from api.coach_routes import router as coach_router
app.include_router(coach_router)

from api.intent_routes import router as intent_router
app.include_router(intent_router)

# 단일 종목 연구 프로파일(FR-STR-068b)
from api.stock_profile_routes import router as stock_profile_router
app.include_router(stock_profile_router)

# news_v2 — pre-fetch & cache architecture
try:
    from news_v2.api import router as news_v2_router
    app.include_router(news_v2_router)
except Exception as _e:
    import logging
    logging.getLogger(__name__).warning("news_v2 router not mounted: %s", _e)

app.state.backtest_engine = engine

# VBT Numba JIT 사전 워밍업 — 첫 백테스트 요청에서 ~4s JIT 컴파일 패널티 제거
# from_signals(2.0s) + winning_streak(1.2s) + pnl.mean(0.2s) + profit_factor(0.1s)
# + total_return/per-col(0.16s) + annualized_return(0.12s) + losing_streak(0.17s) = ~3.9s
def _warmup_vbt():
    try:
        import vectorbt as vbt
        import pandas as pd
        import numpy as np
        dates = pd.date_range("2020-01-01", periods=30, freq="D")
        _d = pd.DataFrame({"A": np.linspace(100, 110, 30), "B": np.linspace(100, 90, 30)}, index=dates)
        _e = pd.DataFrame({"A": [False]*30, "B": [False]*30}, index=dates)
        _x = pd.DataFrame({"A": [False]*30, "B": [False]*30}, index=dates)
        _e.iloc[2] = True; _e.iloc[15] = True; _x.iloc[10] = True; _x.iloc[25] = True
        _pf = vbt.Portfolio.from_signals(
            close=_d, price=_d, entries=_e, exits=_x,
            size=0.5, size_type="Percent", init_cash=1_000_000,
            fees=0.0015, slippage=0.002, freq="D",
            allow_partial=False, direction="longonly",
            accumulate=False, group_by=True, cash_sharing=True,
        )
        # result_handler.py가 사용하는 모든 VBT 메서드 JIT 워밍업
        _pf.trades.records_readable
        _pf.trades.winning.pnl.mean()
        _pf.trades.losing.pnl.mean()
        _pf.trades.winning_streak.max()
        _pf.trades.losing_streak.max()
        _pf.trades.profit_factor()
        _pf.total_return()
        _pf.total_return(group_by=False)
        _pf.trades.count(group_by=False)
        _pf.trades.win_rate(group_by=False)
        _pf.total_profit(group_by=False)
        _pf.annualized_return(group_by=False)
        _pf.max_drawdown(group_by=False)
        _pf.benchmark_returns()
        _pf.returns(group_by=True)
        _pf.max_drawdown()
        _pf.value()
        _pf.total_profit()
        print("[STARTUP] VBT JIT warmup complete (all result_handler methods)", flush=True)
    except Exception as e:
        print(f"[STARTUP] VBT warmup failed (non-fatal): {e}", flush=True)

_warmup_vbt()

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
        req_dict = request.model_dump()
        # 워치독: 엔진이 행에 빠져도 요청은 제한 시간 안에 반드시 끝난다.
        result = watchdog_run_with_timeout(lambda: engine.run_backtest(req_dict))
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
    except BacktestTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Engine error: {str(e)}")

@app.post("/admin/clear-cache")
def clear_data_cache():
    """DataLoader 인메모리 캐시를 비웁니다. 파케이트 파일 업데이트 후 서버 재시작 없이 반영할 때 사용."""
    engine.loader.clear_cache()
    print("[ADMIN] DataLoader cache cleared.", flush=True)
    return {"status": "ok", "message": "DataLoader cache cleared"}

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
            method=request.method,
            is_bars=request.is_bars,
            oos_bars=request.oos_bars,
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


@app.post("/walk-forward/stream")
async def walk_forward_stream(request: WalkForwardRequest):
    """워크포워드 분석을 SSE로 스트리밍 — 창 단위 진행률 + 협조적 취소.

    이벤트: {type: progress|result|error, ...} + 종료 시 'data: [DONE]'.
    클라이언트가 연결을 끊으면 취소 플래그를 세워 다음 창 경계에서 중단한다.
    """
    import threading
    import queue as _queue

    progress_q: _queue.Queue = _queue.Queue()
    result_holder: dict = {}
    error_holder: dict = {}
    cancel_event = threading.Event()

    def run_wfa():
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
                method=request.method,
                is_bars=request.is_bars,
                oos_bars=request.oos_bars,
                progress_callback=progress_q.put,
                should_cancel=cancel_event.is_set,
            )
            result_holder["data"] = result
        except Exception as exc:
            import traceback
            print(f"[WFA-STREAM] ERROR:\n{traceback.format_exc()}", flush=True)
            error_holder["error"] = str(exc)

    thread = threading.Thread(target=run_wfa, daemon=True)

    async def generate():
        thread.start()
        # 워크포워드 전체는 창×시도 횟수만큼 백테스트를 반복하므로 단일 백테스트
        # 제한(BACKTEST_TIMEOUT_S)보다 넉넉한 전용 제한을 쓴다. Next 프록시의
        # 안전망 타임아웃은 반드시 이 값보다 커야 사용자에게 "연결 끊김" 대신
        # 이 친절한 타임아웃 메시지가 전달된다.
        deadline = time.monotonic() + walk_forward_timeout_s()
        # 한 창의 IS 최적화(수십 회 백테스트)는 진행 이벤트 없이 오래 걸릴 수 있다.
        # 이 침묵 구간에 바이트가 흐르지 않으면 Next 프록시의 undici bodyTimeout(기본 ~300s)이
        # 스트림을 끊어 클라이언트가 "network error"만 보게 된다. 주기적 keep-alive 주석으로 방지.
        HEARTBEAT_INTERVAL_S = 15.0
        last_emit = time.monotonic()

        def drain_progress():
            events = []
            while True:
                try:
                    events.append(progress_q.get_nowait())
                except _queue.Empty:
                    return events

        try:
            while thread.is_alive():
                emitted = False
                for payload in drain_progress():
                    yield f"data: {json.dumps({'type': 'progress', **payload}, ensure_ascii=False)}\n\n"
                    emitted = True
                if emitted:
                    last_emit = time.monotonic()
                elif time.monotonic() - last_emit >= HEARTBEAT_INTERVAL_S:
                    # SSE 주석(: 로 시작) — 클라이언트 파서가 무시하지만 연결은 살아있게 한다.
                    yield ": keep-alive\n\n"
                    last_emit = time.monotonic()
                if time.monotonic() >= deadline:
                    cancel_event.set()
                    yield f"data: {json.dumps({'type': 'error', 'message': walk_forward_timeout_message(walk_forward_timeout_s())})}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                await asyncio.sleep(0.2)

            thread.join()
            for payload in drain_progress():
                yield f"data: {json.dumps({'type': 'progress', **payload}, ensure_ascii=False)}\n\n"

            if "error" in error_holder:
                yield f"data: {json.dumps({'type': 'error', 'message': error_holder['error']}, ensure_ascii=False)}\n\n"
            elif "data" in result_holder:
                result = result_holder["data"]
                if result.get("status") in ("error", "cancelled"):
                    yield f"data: {json.dumps({'type': 'error', 'message': result.get('message', '워크포워드 분석 실패')}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'result', 'data': result}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            # 클라이언트 연결 종료(GeneratorExit 포함) 시 다음 창 경계에서 협조적 취소
            cancel_event.set()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



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


# ─────────────────────────────────────────────
# KRX 실제 시세 API
# ─────────────────────────────────────────────

@app.get("/market/health")
async def market_health():
    """전체 데이터 provider 상태 확인 (KIS, Naver, yfinance, pykrx, KRX API)"""
    return market_data_provider.get_health()


@app.get("/market/price/{symbol}")
async def market_price(symbol: str):
    """단일 종목 현재가 조회 (다중 provider 폴백 체인)"""
    result = await market_data_provider.get_price(symbol)
    if not result:
        raise HTTPException(status_code=404, detail=f"{symbol} 시세 없음")
    return result.to_dict()


@app.get("/market/stock-detail/{symbol}")
async def market_stock_detail(
    symbol: str,
    include_profile: bool = True,
    include_listing: bool = True,
    include_public_info: bool = True,
    company_name: Optional[str] = None,
):
    """
    KIS 상세 현재가 조회.
    시가총액/거래량 등 종목 매매 페이지용 실데이터를 우선 제공한다.
    """
    quote, app_key, app_secret, token = await _resolve_kis_orderbook_context(symbol)

    async def _fetch_public_info_or_none():
        if include_public_info:
            return await _run_blocking(_get_cached_public_company_info, symbol, company_name)
        return None

    async def _fetch_detail_if_configured():
        if app_key and app_secret and token:
            return await _run_blocking(
                _fetch_kis_stock_detail, symbol, app_key, app_secret, token, False
            )
        return None

    async def _fetch_debt_ratio_if_configured():
        if app_key and app_secret and token:
            return await _run_blocking(_fetch_kis_debt_ratio, symbol, app_key, app_secret, token)
        return None

    public_company_info, detail, debt_ratio = await asyncio.gather(
        _fetch_public_info_or_none(),
        _fetch_detail_if_configured(),
        _fetch_debt_ratio_if_configured(),
    )
    if detail and debt_ratio and debt_ratio > 0:
        detail = {**detail, "debtRatio": debt_ratio}
    listing_info = (
        (public_company_info or {}).get("listing")
        or (await _run_blocking(_get_cached_listing_info, symbol) if include_listing else None)
    )
    company_basic = (public_company_info or {}).get("companyBasic") or {}
    summary_financials = (public_company_info or {}).get("summaryFinancials") or {}

    if not detail and not listing_info and not company_basic and not summary_financials and not quote:
        raise HTTPException(status_code=503, detail="KIS 상세 시세를 조회할 수 없습니다")

    company_name = (
        (detail or {}).get("name")
        or company_basic.get("name")
        or getattr(quote, "name", None)
        or symbol
    )
    industry = str(company_basic.get("industry") or "").strip()
    sector = _resolve_investment_sector(symbol, company_name, industry)
    public_description = _build_public_company_overview(company_basic, listing_info)
    description = ""
    if not description:
        if public_description:
            description = public_description
        else:
            description = _build_company_intro(company_name, sector, industry)

    payload = {
        **(detail or {}),
        "symbol": symbol,
        "name": company_name,
        "currentPrice": (detail or {}).get("currentPrice") or quote.close,
        "volume": (detail or {}).get("volume") or quote.volume,
        "previousClose": (detail or {}).get("previousClose") or quote.prev_close,
        "debtRatio": (detail or {}).get("debtRatio") or summary_financials.get("debtRatio"),
        "description": description,
        "sector": sector,
        "industry": industry,
        "profileSource": (public_company_info or {}).get("source"),
        "listingDate": (listing_info or {}).get("listingDate"),
        "companyBasic": company_basic or None,
        "summaryFinancials": summary_financials or None,
    }
    if not payload.get("source"):
        payload["source"] = (
            (public_company_info or {}).get("source")
            or "quote_only"
        )

    return payload


@app.post("/market/prices")
async def market_prices(body: dict):
    """
    여러 종목 가격 일괄 조회 (다중 provider 폴백 체인)
    body: {"symbols": ["005930", "000660", ...]}
    반환: {symbol: {symbol, name, date, open, high, low, close, volume, source}}
    """
    symbols: list[str] = body.get("symbols", [])
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols 필드가 필요합니다")
    quotes = await market_data_provider.get_prices(symbols)
    return {sym: q.to_dict() for sym, q in quotes.items()}


@app.post("/market/delist/{symbol}")
async def mark_delisted(symbol: str):
    """상장폐지 종목 등록 — 이후 모든 시세 조회에서 즉시 건너뜀"""
    added = delisted_store.mark(symbol)
    market_data_provider.cache.invalidate(symbol)
    return {"symbol": symbol, "added": added, "delisted": delisted_store.all()}


@app.delete("/market/delist/{symbol}")
async def unmark_delisted(symbol: str):
    """상장폐지 해제"""
    removed = delisted_store.unmark(symbol)
    return {"symbol": symbol, "removed": removed, "delisted": delisted_store.all()}


@app.get("/market/delist")
async def list_delisted():
    """등록된 상장폐지 종목 목록"""
    return {"delisted": delisted_store.all()}


_CONFIRMED_DELIST_KEYWORDS = ["상장폐지결정", "상장폐지 결정", "정리매매", "상장폐지예고"]


@app.get("/market/dart/notices")
async def get_dart_delisting_notices(days: int = 7):
    """
    OpenDART에서 최근 N일간 상장폐지 관련 공시를 조회한다.
    상장폐지 결정·정리매매 확정 건은 자동으로 DelistedSymbolStore에 등록된다.
    거래정지·심사 중인 건은 notices에만 포함되고 자동 등록은 하지 않는다.
    Stock 테이블의 listingStatus도 함께 업데이트된다.
    """
    try:
        notices = fetch_recent_delisting_notices(days=days)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    newly_registered = []
    for notice in notices:
        code = notice["stock_code"]
        report_nm = notice["report_nm"]
        if not code:
            continue
        if any(kw in report_nm for kw in _CONFIRMED_DELIST_KEYWORDS):
            if delisted_store.mark(code):
                market_data_provider.cache.invalidate(code)
                newly_registered.append(code)

    # Stock 테이블 listingStatus 동기화
    changed = sync_from_dart_notices(notices)
    sync_from_delisted_store(set(delisted_store.all()))

    return {
        "days": days,
        "notices": notices,
        "newly_registered": newly_registered,
        "status_updated": changed,
    }


@app.get("/market/listing-status")
async def get_listing_status(symbols: str = ""):
    """심볼 목록(콤마 구분)의 listingStatus 반환. 비어 있으면 비정상 종목 전체 반환."""
    if symbols:
        sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
        results = {}
        for sym in sym_list:
            from engine.listing_status import get_stock_listing_status
            results[sym] = get_stock_listing_status(sym)
        return {"statuses": results}
    else:
        # 비정상 상태 종목 전체
        non_normal = []
        for st in [
            ListingStatus.WARNING, ListingStatus.RISK,
            ListingStatus.TRADING_SUSPENDED, ListingStatus.DELISTING_REVIEW,
            ListingStatus.DELISTING_SCHEDULED, ListingStatus.DELISTED,
        ]:
            non_normal.extend(get_stocks_by_status(st))
        return {"statuses": non_normal}


@app.post("/market/listing-status/sync")
async def sync_listing_status():
    """DelistedSymbolStore → Stock 테이블 listingStatus 동기화 (일배치 후 호출)"""
    count = sync_from_delisted_store(set(delisted_store.all()))
    return {"synced": count}


@app.post("/virtual-account/{account_id}/force-liquidate/{symbol}")
async def force_liquidate_position(account_id: str, symbol: str):
    """
    특정 보유 포지션 강제청산 — DELISTING_SCHEDULED / DELISTED 종목 대상.
    마지막 유효 시세로 청산하며 DelistingAuditLog에 기록한다.
    """
    import db as _appdb
    con = _appdb.connect()
    try:
        pos = con.execute(
            'SELECT * FROM "VirtualPosition" WHERE "accountId" = ? AND symbol = ?',
            (account_id, symbol)
        ).fetchone()
        if not pos:
            raise HTTPException(status_code=404, detail="보유 포지션 없음")

        pos = dict(pos)
        qty = pos["quantity"]
        avg_price = pos["avgPrice"]

        # 최근 시세 조회
        try:
            quote = await market_data_provider.get_price(symbol)
            price = quote.close if quote and quote.close > 0 else int(avg_price)
        except Exception:
            price = int(avg_price)

        # 청산 실행 (시장가)
        import math, uuid as _uuid
        fee_rate = 0.00015
        tax_rate = 0.002
        filled = int(price * (1 - 0.0005))  # 슬리피지
        fee = math.floor(filled * qty * fee_rate)
        tax = math.floor(filled * qty * tax_rate)
        proceeds = filled * qty - fee - tax
        pnl = (filled - avg_price) * qty - fee - tax
        now = _appdb.now()
        order_id = str(_uuid.uuid4())

        con.execute("""
            INSERT INTO "VirtualOrder" (id, "accountId", symbol, name, side, type, quantity, price,
                "filledPrice", fee, tax, "avgBuyPrice", "realizedPnl", status, "filledAt", "createdAt")
            VALUES (?, ?, ?, ?, 'SELL', 'MARKET', ?, ?, ?, ?, ?, ?, ?, 'FILLED', ?, ?)
        """, (order_id, account_id, symbol, pos.get("name") or symbol,
              qty, price, filled, fee, tax, avg_price, pnl, now, now))

        con.execute(
            'UPDATE "VirtualAccount" SET "currentCash" = "currentCash" + ?, "updatedAt" = ? WHERE id = ?',
            (proceeds, now, account_id)
        )
        con.execute(
            'DELETE FROM "VirtualPosition" WHERE "accountId" = ? AND symbol = ?',
            (account_id, symbol)
        )
        con.commit()
    finally:
        con.close()

    # 감사 로그
    write_audit_log(account_id, symbol, "AUTO_LIQUIDATE", None, None, qty, float(price),
                    "수동 강제청산 (API)")

    return {"success": True, "symbol": symbol, "quantity": qty, "price": price, "proceeds": proceeds}


def _tick_size(price: int) -> int:
    if price < 1000:
        return 1
    if price < 5000:
        return 5
    if price < 10000:
        return 10
    if price < 50000:
        return 50
    if price < 100000:
        return 100
    if price < 500000:
        return 500
    return 1000


def _to_int(value) -> int:
    if value in (None, "", "-"):
        return 0
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def _to_optional_int(value) -> Optional[int]:
    if value in (None, "", "-"):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return None


def _to_float(value) -> float:
    if value in (None, "", "-"):
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def _to_optional_float(value) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _first_nonzero_int(data: dict, *keys: str) -> int:
    for key in keys:
        value = _to_int(data.get(key))
        if value > 0:
            return value
    return 0


def _first_int_value(data: dict, *keys: str) -> Optional[int]:
    for key in keys:
        value = _to_optional_int(data.get(key))
        if value is not None:
            return value
    return None


def _first_nonzero_float(data: dict, *keys: str) -> float:
    for key in keys:
        value = _to_float(data.get(key))
        if value > 0:
            return value
    return 0.0


def _first_float_value(data: dict, *keys: str) -> Optional[float]:
    for key in keys:
        value = _to_optional_float(data.get(key))
        if value is not None:
            return value
    return None


def _first_nonempty_str(data: dict, *keys: str) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized and normalized != "-":
            return normalized
    return None


def _first_nonempty_from_dicts(*sources: Optional[dict], keys: tuple[str, ...]) -> Optional[str]:
    for source in sources:
        if not isinstance(source, dict):
            continue
        value = _first_nonempty_str(source, *keys)
        if value:
            return value
    return None


def _first_nonzero_entry(data: dict, *keys: str) -> tuple[Optional[str], int]:
    for key in keys:
        value = _to_int(data.get(key))
        if value > 0:
            return key, value
    return None, 0


def _extract_latest_debt_ratio(output: list[dict]) -> Optional[float]:
    if not isinstance(output, list) or not output:
        return None

    latest_period = ""
    latest_value: Optional[float] = None

    for row in output:
        if not isinstance(row, dict):
            continue

        period = str(row.get("stac_yymm", "") or "").strip()
        value = _to_float(row.get("lblt_rate"))
        if value <= 0:
            continue

        if period >= latest_period:
            latest_period = period
            latest_value = value

    return latest_value


_financial_ratio_cache: dict[str, tuple[Optional[float], float]] = {}
_FINANCIAL_RATIO_CACHE_TTL = 60.0 * 60.0 * 6.0
_company_profile_cache: dict[str, tuple[Optional[dict], float]] = {}
_COMPANY_PROFILE_CACHE_TTL = 60.0 * 60.0 * 6.0
_listing_info_cache: dict[str, tuple[Optional[dict], float]] = {}
_LISTING_INFO_CACHE_TTL = 60.0 * 60.0 * 24.0 * 30.0
_public_company_info_cache: dict[str, tuple[Optional[dict], float]] = {}
_PUBLIC_COMPANY_INFO_CACHE_TTL = 60.0 * 60.0 * 24.0 * 30.0
_PUBLIC_DATA_SERVICE_KEY_ENV_NAMES = (
    "PUBLIC_DATA_SERVICE_KEY",
    "DATA_GO_KR_SERVICE_KEY",
    "DATA_GO_SERVICE_KEY",
)


def _fetch_kis_debt_ratio(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[float]:
    cached = _financial_ratio_cache.get(symbol)
    if cached and cached[1] > time.time():
        return cached[0]

    debt_ratio: Optional[float] = None
    try:
        resp = _http_session.get(
            "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/finance/financial-ratio",
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": "FHKST66430300",
                "custtype": "P",
            },
            params={
                "FID_DIV_CLS_CODE": "0",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": symbol,
            },
            timeout=5,
        )
        if resp.status_code == 200:
            debt_ratio = _extract_latest_debt_ratio(resp.json().get("output", []))
    except Exception:
        debt_ratio = None

    _financial_ratio_cache[symbol] = (debt_ratio, time.time() + _FINANCIAL_RATIO_CACHE_TTL)
    return debt_ratio


def _summarize_company_description(text: Optional[str]) -> str:
    if not text:
        return ""

    normalized = re.sub(r"\s+", " ", str(text)).strip()
    if not normalized:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", normalized)
    brief = " ".join(sentence.strip() for sentence in sentences[:2] if sentence.strip())
    if len(brief) <= 320:
        return brief
    return brief[:317].rstrip() + "..."


def _clean_korean_company_name(name: Optional[str]) -> str:
    normalized = str(name or "").strip()
    normalized = re.sub(r"\s*\(주\)\s*", "", normalized)
    return normalized or "해당 기업"


def _normalize_company_name_for_match(name: Optional[str]) -> str:
    normalized = str(name or "").strip().lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("주식회사", "")
    normalized = normalized.replace("(주)", "")
    normalized = normalized.replace("㈜", "")
    normalized = re.sub(r"[().,]", "", normalized)
    return normalized


def _normalize_homepage_url(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if re.match(r"^[a-z][a-z0-9+.-]*://", normalized, re.IGNORECASE):
        return normalized
    return f"https://{normalized.lstrip('/')}"


def _translate_company_description(text: Optional[str], company_name: Optional[str]) -> str:
    if not text:
        return ""

    normalized = re.sub(r"\s+", " ", str(text)).strip()
    if not normalized:
        return ""
    if re.search(r"[가-힣]", normalized):
        return normalized

    display_name = _clean_korean_company_name(company_name)

    translations = [
        (
            re.compile(
                r"^.*? engages in the consumer electronics, information technology and mobile communications, and device solutions businesses worldwide\.?$",
                re.IGNORECASE,
            ),
            f"{display_name}는 전 세계에서 전자제품, 정보기술 및 모바일 커뮤니케이션, 디바이스 솔루션 사업을 영위합니다.",
        ),
        (
            re.compile(
                r"^.*? engages in consumer electronics and semiconductor businesses worldwide\.?$",
                re.IGNORECASE,
            ),
            f"{display_name}는 전 세계에서 전자제품 및 반도체 사업을 영위합니다.",
        ),
    ]
    for pattern, translated in translations:
        if pattern.match(normalized):
            return translated

    return normalized


def _build_company_intro(name: str, sector: Optional[str], industry: Optional[str]) -> str:
    normalized_name = str(name or "").strip() or "해당 기업"
    normalized_sector = str(sector or "").strip()
    normalized_industry = str(industry or "").strip()

    if normalized_sector and normalized_industry:
        return f"{normalized_name}는 {normalized_sector} 섹터의 {normalized_industry} 업종에 속한 상장사입니다."
    if normalized_industry:
        return f"{normalized_name}는 {normalized_industry} 업종에 속한 상장사입니다."
    if normalized_sector:
        return f"{normalized_name}는 {normalized_sector} 섹터에 속한 상장사입니다."
    return f"{normalized_name}는 국내 상장사입니다."


def _format_public_listing_date(value: Optional[str]) -> Optional[str]:
    normalized = _normalize_public_listing_date(value)
    if not normalized or len(normalized) != 8:
        return normalized
    return f"{normalized[:4]}년 {normalized[4:6]}월 {normalized[6:8]}일"


def _build_public_company_overview(
    company_basic: Optional[dict],
    listing_info: Optional[dict],
) -> str:
    if not isinstance(company_basic, dict):
        return ""

    display_name = (
        company_basic.get("disclosureName")
        or _clean_korean_company_name(company_basic.get("name"))
    )
    if not display_name:
        return ""

    main_business = str(company_basic.get("mainBusiness") or "").strip()
    industry = str(company_basic.get("industry") or "").strip()
    representative_name = str(company_basic.get("representativeName") or "").strip()
    address = str(company_basic.get("address") or "").strip()
    listing_date = _format_public_listing_date(
        (listing_info or {}).get("listingDate")
        or company_basic.get("exchangeListingDate")
        or company_basic.get("kosdaqListingDate")
        or company_basic.get("krxListingDate")
    )

    sentences = []
    if main_business:
        sentences.append(f"{display_name}의 주요 사업은 {main_business}입니다.")
    elif industry:
        sentences.append(f"{display_name}는 {industry} 업종에 속한 국내 상장사입니다.")
    else:
        sentences.append(f"{display_name}는 국내 상장사입니다.")

    if listing_date:
        sentences.append(f"상장일은 {listing_date}입니다.")
    if representative_name:
        sentences.append(f"대표자는 {representative_name}입니다.")
    if address:
        sentences.append(f"본사는 {address}에 있습니다.")

    return " ".join(sentences)


def _resolve_investment_sector(
    symbol: str,
    company_name: Optional[str],
    industry: Optional[str],
) -> str:
    # source of truth: data/ohlcv/{symbol}.parquet의 sector 컬럼.
    # (전 종목에 정확한 섹터를 백필해두었으므로, 매 요청마다 실시간 재계산하지 않고 이를 우선 사용한다.)
    parquet_sector = _read_sector_from_parquet(symbol)
    if parquet_sector:
        return parquet_sector

    normalized_industry = str(industry or "").strip()
    if not normalized_industry:
        return ""

    try:
        from engine.sector_mapper import get_sector_from_industry

        return str(
            get_sector_from_industry(symbol, normalized_industry, company_name or "") or ""
        ).strip()
    except Exception:
        return ""


_OHLCV_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "ohlcv")


def _read_sector_from_parquet(symbol: str) -> str:
    parquet_path = os.path.join(_OHLCV_DATA_DIR, f"{symbol}.parquet")
    if not os.path.exists(parquet_path):
        return ""
    try:
        import pandas as pd

        df = pd.read_parquet(parquet_path, columns=["sector"])
        if df.empty:
            return ""
        sector = df.iloc[-1].get("sector")
        return str(sector).strip() if pd.notna(sector) else ""
    except Exception:
        return ""


def _get_public_data_service_key() -> str:
    for env_name in _PUBLIC_DATA_SERVICE_KEY_ENV_NAMES:
        value = os.getenv(env_name, "").strip()
        if value:
            return value
    return ""


def _normalize_public_data_items(payload: Optional[dict]) -> List[dict]:
    if not isinstance(payload, dict):
        return []

    body = ((payload.get("response") or {}).get("body") or {})
    items = body.get("items")
    if isinstance(items, dict):
        items = items.get("item")

    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    if isinstance(items, dict):
        return [items]
    return []


def _fetch_public_data_items(url: str, params: dict) -> List[dict]:
    service_key = _get_public_data_service_key()
    if not service_key:
        return []

    candidate_keys = [service_key]
    decoded_key = unquote(service_key)
    if decoded_key != service_key:
        candidate_keys.append(decoded_key)

    for candidate_key in candidate_keys:
        try:
            resp = _http_session.get(
                url,
                params={
                    **params,
                    "serviceKey": candidate_key,
                    "resultType": "json",
                },
                timeout=5,
            )
            if resp.status_code != 200:
                continue

            payload = resp.json()
            result_code = str(((payload.get("response") or {}).get("header") or {}).get("resultCode", ""))
            if result_code not in {"00", "0"}:
                continue

            items = _normalize_public_data_items(payload)
            if items:
                return items
        except Exception:
            continue

    return []


def _fetch_listing_info_from_public_api(symbol: str) -> Optional[dict]:
    listed_items = _fetch_public_data_items(
        "https://apis.data.go.kr/1160100/service/GetKrxListedInfoService/getItemInfo",
        {
            "numOfRows": 10,
            "pageNo": 1,
            "likeSrtnCd": symbol,
        },
    )

    listed_item = next(
        (
            item
            for item in listed_items
            if str(item.get("srtnCd", "")).strip() == symbol
        ),
        None,
    )
    if not listed_item:
        return None

    crno = _first_nonempty_str(listed_item, "crno")
    if not crno:
        return None

    issuance_items = _fetch_public_data_items(
        "https://apis.data.go.kr/1160100/service/GetStocIssuInfoService/getItemBasiInfo",
        {
            "numOfRows": 10,
            "pageNo": 1,
            "crno": crno,
        },
    )

    issuance_item = next(
        (
            item
            for item in issuance_items
            if str(item.get("crno", "")).strip() == crno and _first_nonempty_str(item, "lstgDt")
        ),
        None,
    )
    if not issuance_item:
        return None

    listing_date = _first_nonempty_str(issuance_item, "lstgDt")
    if not listing_date:
        return None

    return {
        "listingDate": listing_date,
        "crno": crno,
        "isinCode": _first_nonempty_str(issuance_item, "isinCd"),
        "stockIssueCompanyName": _first_nonempty_str(issuance_item, "stckIssuCmpyNm"),
        "issuedShares": _first_nonzero_int(issuance_item, "issuStckCnt"),
        "parValue": _first_nonzero_int(issuance_item, "stckParPrc"),
        "delistingDate": _first_nonempty_str(issuance_item, "lstgAbolDt"),
        "source": "fsc_stock_issuance",
    }


def _normalize_company_basic(item: Optional[dict]) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    return {
        "crno": _first_nonempty_str(item, "crno"),
        "name": _first_nonempty_str(item, "corpNm", "enpPbanCmpyNm"),
        "englishName": _first_nonempty_str(item, "corpEnsnNm"),
        "disclosureName": _first_nonempty_str(item, "enpPbanCmpyNm"),
        "representativeName": _first_nonempty_str(item, "enpRprFnm"),
        "businessRegistrationNumber": _first_nonempty_str(item, "bzno"),
        "establishmentDate": _first_nonempty_str(item, "enpEstbDt"),
        "exchangeListingDate": _first_nonempty_str(item, "enpXchgLstgDt"),
        "kosdaqListingDate": _first_nonempty_str(item, "enpKosdaqLstgDt"),
        "krxListingDate": _first_nonempty_str(item, "enpKrxLstgDt"),
        "homepageUrl": _normalize_homepage_url(_first_nonempty_str(item, "enpHmpgUrl")),
        "industry": _first_nonempty_str(item, "sicNm"),
        "mainBusiness": _first_nonempty_str(item, "enpMainBizNm"),
        "employeeCount": _first_nonzero_int(item, "enpEmpeCnt"),
        "averageTenure": _first_nonempty_str(item, "empeAvgCnwkTermCtt"),
        "averageSalary": _first_nonzero_int(item, "enpPn1AvgSlryAmt"),
        "settlementMonth": _first_nonempty_str(item, "enpStacMm"),
        "address": _first_nonempty_str(item, "enpBsadr", "enpDtadr"),
        "phone": _first_nonempty_str(item, "enpTlno"),
        "source": "fsc_company_basic",
    }


def _merge_company_basic_items(items: List[dict]) -> Optional[dict]:
    normalized_items = [
        _normalize_company_basic(item)
        for item in items
        if isinstance(item, dict)
    ]
    normalized_items = [item for item in normalized_items if isinstance(item, dict)]
    if not normalized_items:
        return None

    merged = dict(normalized_items[0])
    for item in normalized_items[1:]:
        for key, value in item.items():
            if value in (None, "", 0):
                continue
            if merged.get(key) in (None, "", 0):
                merged[key] = value

    return merged


def _score_company_basic_item(item: dict, company_name: str) -> tuple[int, str]:
    normalized_query = _normalize_company_name_for_match(company_name)
    names = [
        _first_nonempty_str(item, "enpPbanCmpyNm") or "",
        _first_nonempty_str(item, "corpNm") or "",
        _first_nonempty_str(item, "corpEnsnNm") or "",
    ]
    normalized_names = [_normalize_company_name_for_match(name) for name in names]

    score = 0
    if normalized_query:
        if any(name == normalized_query for name in normalized_names):
            score += 300
        elif any(name.startswith(normalized_query) for name in normalized_names):
            score += 80
        elif any(normalized_query in name for name in normalized_names):
            score += 20
    if _first_nonempty_str(item, "enpPbanCmpyNm"):
        score += 40
    if _first_nonempty_str(item, "corpRegMrktDcdNm"):
        score += 50
    if _first_nonempty_str(item, "enpXchgLstgDt", "enpKosdaqLstgDt", "enpKrxLstgDt"):
        score += 40
    if _first_nonempty_str(item, "fssCorpUnqNo"):
        score += 30
    if _first_nonempty_str(item, "sicNm"):
        score += 35
    if _first_nonempty_str(item, "enpMainBizNm"):
        score += 25

    return score, _first_nonempty_str(item, "lastOpegDt", "fstOpegDt") or ""


def _fetch_company_basic_from_public_api(
    crno: Optional[str],
    company_name: Optional[str] = None,
) -> Optional[dict]:
    if not crno and not company_name:
        return None

    params = {
        "numOfRows": 100 if company_name and not crno else 10,
        "pageNo": 1,
    }
    if crno:
        params["crno"] = crno
    if company_name:
        params["corpNm"] = company_name

    items = _fetch_public_data_items(
        "https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2",
        params,
    )
    # 이름 검색 결과 없으면 한글 부분만 추출해서 재시도 (예: "SK하이닉스" → "하이닉스")
    if not items and company_name and not crno:
        korean_part = re.sub(r"[A-Za-z0-9&\s]+", "", company_name).strip()
        if korean_part and korean_part != company_name:
            items = _fetch_public_data_items(
                "https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2",
                {"numOfRows": 100, "pageNo": 1, "corpNm": korean_part},
            )

    item = next(
        (
            row
            for row in items
            if crno and str(row.get("crno", "")).strip() == crno
        ),
        None,
    )
    if not item and items:
        if company_name:
            item = sorted(
                items,
                key=lambda row: _score_company_basic_item(row, company_name),
                reverse=True,
            )[0]
        else:
            item = items[0]

    if not item:
        return None

    matching_items = [item]
    item_crno = _first_nonempty_str(item, "crno")
    normalized_name = _normalize_company_name_for_match(
        _first_nonempty_str(item, "enpPbanCmpyNm", "corpNm", "corpEnsnNm")
    )
    for row in items:
        if row is item or not isinstance(row, dict):
            continue
        if item_crno and _first_nonempty_str(row, "crno") == item_crno:
            matching_items.append(row)
            continue
        row_name = _normalize_company_name_for_match(
            _first_nonempty_str(row, "enpPbanCmpyNm", "corpNm", "corpEnsnNm")
        )
        if normalized_name and row_name == normalized_name:
            matching_items.append(row)

    return _merge_company_basic_items(matching_items)


def _normalize_summary_financials(item: Optional[dict]) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    return {
        "crno": _first_nonempty_str(item, "crno"),
        "baseDate": _first_nonempty_str(item, "basDt"),
        "businessYear": _first_nonempty_str(item, "bizYear"),
        "statementTypeCode": _first_nonempty_str(item, "fnclDcd"),
        "statementType": _first_nonempty_str(item, "fnclDcdNm"),
        "sales": _first_int_value(item, "enpSaleAmt"),
        "operatingProfit": _first_int_value(item, "enpBzopPft"),
        "comprehensiveIncome": _first_int_value(item, "iclsPalClcAmt"),
        "netIncome": _first_int_value(item, "enpCrtmNpf"),
        "totalAssets": _first_int_value(item, "enpTastAmt"),
        "totalLiabilities": _first_int_value(item, "enpTdbtAmt"),
        "totalEquity": _first_int_value(item, "enpTcptAmt"),
        "capital": _first_int_value(item, "enpCptlAmt"),
        "debtRatio": _first_float_value(item, "fnclDebtRto"),
        "source": "fsc_summary_financials",
    }


def _fetch_summary_financials_from_public_api(crno: str) -> Optional[dict]:
    items = _fetch_public_data_items(
        "https://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2/getSummFinaStat_V2",
        {
            "numOfRows": 100,
            "pageNo": 1,
            "crno": crno,
        },
    )
    if not items:
        return None

    def sort_key(item: dict) -> tuple[str, str, int]:
        statement_name = str(item.get("fnclDcdNm", "") or "")
        consolidated_rank = 1 if "연결" in statement_name else 0
        return (
            str(item.get("bizYear", "") or ""),
            str(item.get("basDt", "") or ""),
            consolidated_rank,
        )

    latest = sorted(items, key=sort_key, reverse=True)[0]
    return _normalize_summary_financials(latest)


def _normalize_public_listing_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 6:
        year_prefix = "19" if int(digits[:2]) > 40 else "20"
        return year_prefix + digits
    if len(digits) == 8:
        return digits
    return str(value).strip() or None


def _fetch_public_company_info(symbol: str, company_name: Optional[str] = None) -> Optional[dict]:
    from concurrent.futures import ThreadPoolExecutor

    # Step 1: listing 조회 + 이름 있으면 company_basic(이름검색)을 병렬로 동시 시도.
    # listing 결과에서 crno와 stockIssueCompanyName을 얻으므로 일반적으로 첫 step에서 모든 정보 확보.
    with ThreadPoolExecutor(max_workers=2) as ex:
        listing_future = ex.submit(_fetch_listing_info_from_public_api, symbol)
        basic_by_name_future = (
            ex.submit(_fetch_company_basic_from_public_api, None, company_name)
            if company_name else None
        )
        listing = listing_future.result()
        basic_by_name = basic_by_name_future.result() if basic_by_name_future else None

    crno = (listing or {}).get("crno") or (basic_by_name or {}).get("crno")

    resolved_company_name = (
        _first_nonempty_from_dicts(listing, keys=("stockIssueCompanyName", "name"))
        or company_name
    )

    # Step 2: crno 확보 후 company_basic(crno검색)과 summary_financials를 병렬 실행.
    # 이름 검색 결과(basic_by_name)가 이미 있으면 그대로 사용.
    with ThreadPoolExecutor(max_workers=2) as ex:
        basic_future = (
            None if basic_by_name
            else ex.submit(_fetch_company_basic_from_public_api, crno, resolved_company_name)
        )
        summary_future = (
            ex.submit(_fetch_summary_financials_from_public_api, crno) if crno else None
        )
        company_basic = basic_by_name if basic_by_name else (basic_future.result() if basic_future else None)
        summary_financials = summary_future.result() if summary_future else None

    if not listing and company_basic:
        listing_date = _normalize_public_listing_date(
            company_basic.get("exchangeListingDate")
            or company_basic.get("kosdaqListingDate")
            or company_basic.get("krxListingDate")
        )
        listing = {
            "listingDate": listing_date,
            "crno": crno,
            "source": "fsc_company_basic",
        } if listing_date or crno else None

    if not listing and not company_basic and not summary_financials:
        return None

    return {
        "listing": listing,
        "companyBasic": company_basic,
        "summaryFinancials": summary_financials,
        "source": "fsc_public_company_info",
    }


def _fetch_yahoo_company_profile(symbol: str) -> Optional[dict]:
    try:
        import yfinance as yf
    except Exception:
        return None

    candidates = [f"{symbol}.KS", f"{symbol}.KQ", symbol]
    best_profile: Optional[dict] = None
    best_score = -1

    for candidate in candidates:
        try:
            info = yf.Ticker(candidate).get_info() or {}
        except Exception:
            continue

        if not isinstance(info, dict):
            continue

        name = _first_nonempty_str(info, "longName", "shortName")
        sector = _first_nonempty_str(info, "sector")
        industry = _first_nonempty_str(info, "industry")
        description = _summarize_company_description(
            _first_nonempty_str(info, "longBusinessSummary", "description")
        )

        score = (
            (4 if description else 0)
            + (2 if sector else 0)
            + (2 if industry else 0)
            + (1 if name else 0)
        )
        if score <= 0:
            continue

        profile = {
            "name": name,
            "description": description,
            "sector": sector or "",
            "industry": industry or "",
            "source": f"yahoo_profile:{candidate}",
        }
        if score > best_score:
            best_profile = profile
            best_score = score

    return best_profile


def _get_cached_company_profile(symbol: str) -> Optional[dict]:
    cached = _company_profile_cache.get(symbol)
    if cached and cached[1] > time.time():
        return cached[0]

    value = _fetch_yahoo_company_profile(symbol)
    _company_profile_cache[symbol] = (value, time.time() + _COMPANY_PROFILE_CACHE_TTL)
    return value


def _get_cached_listing_info(symbol: str) -> Optional[dict]:
    cached = _listing_info_cache.get(symbol)
    if cached and cached[1] > time.time():
        return cached[0]

    value = _fetch_listing_info_from_public_api(symbol)
    _listing_info_cache[symbol] = (value, time.time() + _LISTING_INFO_CACHE_TTL)
    return value


def _get_cached_public_company_info(symbol: str, company_name: Optional[str] = None) -> Optional[dict]:
    cache_key = f"{symbol}:{company_name or ''}"
    cached = _public_company_info_cache.get(cache_key)
    if cached and cached[1] > time.time():
        return cached[0]

    value = _fetch_public_company_info(symbol, company_name)
    _public_company_info_cache[cache_key] = (
        value,
        time.time() + _PUBLIC_COMPANY_INFO_CACHE_TTL,
    )
    return value


def _fetch_kis_stock_detail(
    symbol: str,
    app_key: str,
    app_secret: str,
    token: str,
    include_debt_ratio: bool = True,
) -> Optional[dict]:
    try:
        resp = _http_session.get(
            "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-price",
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": "FHKST01010100",
                "custtype": "P",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "UN",
                "FID_INPUT_ISCD": symbol,
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return None

        output = resp.json().get("output", {})
        if not isinstance(output, dict):
            return None

        current_price = _first_nonzero_int(output, "stck_prpr")
        if current_price <= 0:
            return None

        market_cap_key, market_cap = _first_nonzero_entry(
            output,
            "hts_avls",
            "stck_avls",
            "mrkt_tot_amt",
            "mrkt_cap",
            "market_cap",
        )
        listed_shares = _first_nonzero_int(
            output,
            "lstn_stcn",
            "listed_stcn",
            "istt_qty",
            "stck_lstn_qty",
        )
        market_cap = normalize_market_cap(
            market_cap,
            market_cap_key,
            listed_shares,
            current_price,
        )

        per = _first_nonzero_float(output, "perx", "per")
        pbr = _first_nonzero_float(output, "pbrx", "pbr")
        debt_ratio = _fetch_kis_debt_ratio(symbol, app_key, app_secret, token) if include_debt_ratio else None
        week52_high = _first_nonzero_int(output, "w52_hgpr")
        week52_low = _first_nonzero_int(output, "w52_lwpr")
        week52_high_ratio = _first_nonzero_float(output, "w52_hgpr_vrss_prpr_ctrt")
        week52_low_ratio = _first_nonzero_float(output, "w52_lwpr_vrss_prpr_ctrt")
        new_high_low_code = _first_nonempty_str(output, "new_hgpr_lwpr_cls_code")

        return {
            "symbol": symbol,
            "name": output.get("hts_kor_isnm", symbol),
            "currentPrice": current_price,
            "open": _first_nonzero_int(output, "stck_oprc"),
            "high": _first_nonzero_int(output, "stck_hgpr"),
            "low": _first_nonzero_int(output, "stck_lwpr"),
            "volume": _first_nonzero_int(output, "acml_vol"),
            "marketCap": market_cap,
            "previousClose": _first_nonzero_int(output, "stck_sdpr"),
            "changePercent": float(output.get("prdy_ctrt", 0) or 0),
            "per": per if per > 0 else None,
            "pbr": pbr if pbr > 0 else None,
            "debtRatio": debt_ratio if debt_ratio and debt_ratio > 0 else None,
            "week52High": week52_high or None,
            "week52HighDate": _first_nonempty_str(output, "w52_hgpr_date"),
            "week52HighChangePercent": week52_high_ratio if week52_high_ratio > 0 else None,
            "week52Low": week52_low or None,
            "week52LowDate": _first_nonempty_str(output, "w52_lwpr_date"),
            "week52LowChangePercent": week52_low_ratio if week52_low_ratio > 0 else None,
            "newHighLowCode": new_high_low_code,
            "isNew52WeekHigh": new_high_low_code == "1",
            "isNew52WeekLow": new_high_low_code == "2",
            "source": "kis_inquire_price",
        }
    except Exception:
        return None


def _fetch_kis_vi_display(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[dict]:
    try:
        today = datetime.now().strftime("%Y%m%d")
        resp = _http_session.get(
            "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-vi-status",
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": "FHPST01390000",
                "custtype": "P",
            },
            params={
                "FID_DIV_CLS_CODE": "0",
                "FID_COND_SCR_DIV_CODE": "20139",
                "FID_MRKT_CLS_CODE": "0",
                "FID_INPUT_ISCD": symbol,
                "FID_RANK_SORT_CLS_CODE": "0",
                "FID_INPUT_DATE_1": today,
                "FID_TRGT_CLS_CODE": "",
                "FID_TRGT_EXLS_CLS_CODE": "",
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return None

        output = resp.json().get("output", [])
        if not isinstance(output, list) or not output:
            return None

        records = [
            item for item in output
            if isinstance(item, dict) and str(item.get("mksc_shrn_iscd", "")) == symbol
        ]
        if not records:
            return None

        records.sort(key=lambda item: str(item.get("cntg_vi_hour", "")), reverse=True)
        return build_vi_display(records[0])
    except Exception:
        return None

_vi_cache: dict[str, tuple[Optional[dict], float]] = {}
_trade_strength_cache: dict[str, tuple[Optional[float], float]] = {}
_VI_CACHE_TTL = 5.0
_TRADE_STRENGTH_CACHE_TTL = 10.0


def _get_cached_vi_display(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[dict]:
    cached = _vi_cache.get(symbol)
    if cached and cached[1] > time.time():
        return cached[0]
    value = _fetch_kis_vi_display(symbol, app_key, app_secret, token)
    _vi_cache[symbol] = (value, time.time() + _VI_CACHE_TTL)
    return value


def _fetch_kis_trade_strength(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[float]:
    try:
        resp = _http_session.get(
            "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-ccnl",
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": "FHKST01010300",
                "custtype": "P",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "UN",
                "FID_INPUT_ISCD": symbol,
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return None

        output = resp.json().get("output", [])
        if not isinstance(output, list) or not output:
            return None

        latest = output[0] if isinstance(output[0], dict) else None
        if not latest:
            return None

        value = float(latest.get("tday_rltv", 0) or 0)
        return value if value > 0 else None
    except Exception:
        return None


def _get_cached_trade_strength(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[float]:
    cached = _trade_strength_cache.get(symbol)
    if cached and cached[1] > time.time():
        return cached[0]
    value = _fetch_kis_trade_strength(symbol, app_key, app_secret, token)
    _trade_strength_cache[symbol] = (value, time.time() + _TRADE_STRENGTH_CACHE_TTL)
    return value


async def _run_blocking(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


async def _resolve_kis_orderbook_context(symbol: str) -> tuple[Optional[object], str, str, Optional[str]]:
    # 호가창 스트림 컨텍스트에서는 stale 외부캐시(30s TTL) 우회 — WS 실시간 캐시 우선,
    # 없으면 market_data_provider 폴백
    quote: Optional[object] = None
    if market_data_provider.ws_provider.is_configured():
        quote = await market_data_provider.ws_provider.get_price(symbol)
        if not quote:
            await market_data_provider.ws_provider.subscribe([symbol])
    if not quote:
        quote = await market_data_provider.get_price(symbol)
    if not quote:
        raise HTTPException(status_code=404, detail=f"{symbol} 시세 없음")

    app_key = os.getenv("KIS_APP_KEY", "").strip()
    app_secret = os.getenv("KIS_APP_SECRET", "").strip()
    token = getattr(market_data_provider.providers[1], "_access_token", None) if len(market_data_provider.providers) > 1 else None
    expires_at = getattr(market_data_provider.providers[1], "_token_expires_at", 0.0) if len(market_data_provider.providers) > 1 else 0.0

    if app_key and app_secret and (not token or time.time() >= expires_at):
        try:
            token = await market_data_provider.providers[1]._ensure_token()  # type: ignore[attr-defined]
        except Exception:
            token = None

    return quote, app_key, app_secret, token


def _fetch_kis_orderbook_rest(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[dict]:
    try:
        resp = _http_session.get(
            "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn",
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": "FHKST01010200",
                "custtype": "P",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "UN",
                "FID_INPUT_ISCD": symbol,
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        output = resp.json().get("output1", {})
        sell_orders = []
        buy_orders = []
        for level in range(1, 11):
            ask_price = int(float(output.get(f"askp{level}", 0) or 0))
            ask_qty = int(float(output.get(f"askp_rsqn{level}", 0) or 0))
            bid_price = int(float(output.get(f"bidp{level}", 0) or 0))
            bid_qty = int(float(output.get(f"bidp_rsqn{level}", 0) or 0))
            if ask_price > 0:
                sell_orders.append({"price": ask_price, "quantity": ask_qty})
            if bid_price > 0:
                buy_orders.append({"price": bid_price, "quantity": bid_qty})
        if not sell_orders and not buy_orders:
            return None
        return {
            "sellOrders": sell_orders,
            "buyOrders": buy_orders,
            "totalAskQty": int(float(output.get("total_askp_rsqn", 0) or 0)),
            "totalBidQty": int(float(output.get("total_bidp_rsqn", 0) or 0)),
        }
    except Exception:
        return None


async def _build_orderbook_payload(symbol: str) -> dict:
    if market_data_provider.ws_provider.is_configured():
        await market_data_provider.subscribe([symbol])

    quote, app_key, app_secret, token = await _resolve_kis_orderbook_context(symbol)

    if app_key and app_secret and token:
        vi_display, trade_strength, ws_orderbook = await asyncio.gather(
            _run_blocking(_get_cached_vi_display, symbol, app_key, app_secret, token),
            _run_blocking(_get_cached_trade_strength, symbol, app_key, app_secret, token),
            market_data_provider.ws_provider.get_orderbook(symbol),
        )
        if ws_orderbook:
            return {
                **ws_orderbook,
                "symbol": symbol,
                "currentPrice": quote.close,
                "vi": vi_display,
                "tradeStrength": trade_strength,
                "source": "kis_ws_total_orderbook",
            }

        rest_data = await _run_blocking(_fetch_kis_orderbook_rest, symbol, app_key, app_secret, token)
        if rest_data:
            return {
                "symbol": symbol,
                "currentPrice": quote.close,
                **rest_data,
                "vi": vi_display,
                "recentTrades": [],
                "tradeStrength": trade_strength,
                "source": "kis_total_orderbook_rest",
                "timestamp": time.time(),
            }

    raise HTTPException(status_code=503, detail="실제 호가 데이터를 아직 받지 못했습니다")


def _fetch_naver_investor_trading(symbol: str) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = _http_session.get(
            f"https://m.stock.naver.com/api/stock/{symbol}/integration",
            headers=headers,
            timeout=4,
        )
        if resp.status_code != 200:
            return []
    except Exception:
        return []

    deals = resp.json().get("dealTrendInfos") or []

    def _parse_qty(val: str) -> int:
        try:
            return int(str(val).replace(",", "").replace("+", ""))
        except (ValueError, TypeError):
            return 0

    rows = []
    for d in deals:
        raw = d.get("bizdate", "")
        date_str = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}" if len(raw) == 8 else raw
        rows.append({
            "date": date_str,
            "individual_net": _parse_qty(d.get("individualPureBuyQuant")),
            "foreign_net": _parse_qty(d.get("foreignerPureBuyQuant")),
            "institutional_net": _parse_qty(d.get("organPureBuyQuant")),
            "close_price": _parse_qty(d.get("closePrice")),
            "volume": _parse_qty(d.get("accumulatedTradingVolume")),
            "foreign_hold_ratio": d.get("foreignerHoldRatio", ""),
        })
    return rows


@app.get("/market/investor-trading/{symbol}")
async def market_investor_trading(symbol: str):
    """투자자별 일별 매매동향 (개인/외국인/기관).

    KIS와 Naver를 병렬로 시도하고 KIS 결과를 우선 사용한다.
    KIS가 실패하거나 빈 결과를 주면 Naver 결과로 폴백.
    """
    kis = next(
        (p for p in market_data_provider.providers if p.name == "kis"),
        None,
    )

    async def _try_kis():
        if not kis:
            return None
        try:
            return await kis.get_investor_trading(symbol)
        except Exception:
            return None

    kis_rows, naver_rows = await asyncio.gather(
        _try_kis(),
        asyncio.to_thread(_fetch_naver_investor_trading, symbol),
    )

    if kis_rows:
        return {"symbol": symbol, "data": kis_rows, "source": "kis"}
    if naver_rows:
        return {"symbol": symbol, "data": naver_rows, "source": "naver"}

    raise HTTPException(status_code=503, detail="투자자 매매동향 데이터를 가져올 수 없습니다")


@app.get("/market/orderbook/{symbol}")
async def market_orderbook(symbol: str):
    """
    실시간 10호가 조회.
    KIS REST 호가 API 응답이 있을 때만 실제 10호가를 반환한다.
    실호가를 받지 못하면 503을 반환한다.
    """
    return await _build_orderbook_payload(symbol)


@app.get("/market/orderbook-stream/{symbol}")
async def market_orderbook_stream(symbol: str, request: Request):
    async def generate():
        last_payload: Optional[str] = None

        while True:
            if await request.is_disconnected():
                break

            try:
                payload = await _build_orderbook_payload(symbol)
                serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                if serialized != last_payload:
                    yield f"data: {serialized}\n\n"
                    last_payload = serialized
            except HTTPException as exc:
                serialized = json.dumps({"error": exc.detail}, ensure_ascii=False, separators=(",", ":"))
                if serialized != last_payload:
                    yield f"data: {serialized}\n\n"
                    last_payload = serialized

            await asyncio.sleep(0.1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/market/prices-stream")
async def market_prices_stream(symbols: str, request: Request):
    """
    다중 종목 실시간 가격 SSE 스트림 (500ms 주기).
    ?symbols=005930,000660,373220,...
    이벤트 데이터: {symbol: {close, change_rate, prev_close, open}, ...}
    """
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]

    if symbol_list:
        try:
            await market_data_provider.subscribe(symbol_list)
        except Exception:
            pass

    async def generate():
        last_payload: Optional[str] = None
        while True:
            if await request.is_disconnected():
                break
            try:
                quotes = await market_data_provider.get_prices(symbol_list)
                data = {
                    sym: {
                        "close": q.to_dict().get("close", 0),
                        "change_rate": q.to_dict().get("change_rate", 0),
                        "prev_close": q.to_dict().get("prev_close", 0),
                        "open": q.to_dict().get("open", 0),
                    }
                    for sym, q in quotes.items()
                }
                serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                if serialized != last_payload:
                    yield f"data: {serialized}\n\n"
                    last_payload = serialized
            except Exception:
                pass
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/market/subscribe")
async def market_subscribe(body: dict):
    """
    KIS WebSocket 실시간 구독 종목 추가.
    body: {"symbols": ["005930", "000660", ...]}
    구독 후 /market/price/{symbol} 조회 시 WebSocket 캐시(실시간)가 최우선 반환.
    """
    symbols: list[str] = body.get("symbols", [])
    if not symbols:
        raise HTTPException(status_code=400, detail="symbols 필드가 필요합니다")
    await market_data_provider.subscribe(symbols)
    return {"subscribed": symbols, "total": len(market_data_provider.ws_provider.get_subscribed())}


@app.get("/market/realtime")
async def market_realtime():
    """KIS WebSocket 실시간 캐시 전체 스냅샷 반환"""
    snapshot = market_data_provider.ws_provider.get_cache_snapshot()
    return {
        "running": await market_data_provider.ws_provider.health_check(),
        "subscribed": market_data_provider.ws_provider.get_subscribed(),
        "quotes": snapshot,
    }


# ── /market/indices 서버 측 캐시 ──────────────────────────────────────────
_indices_cache: dict = {"data": None, "expires_at": 0.0, "loading": False}
_INDICES_TTL = 30  # seconds


def _fetch_kis_index(iscd: str, name: str, token: str, app_key: str, app_secret: str) -> Optional[dict]:
    """KIS API로 국내 지수(코스피/코스닥) 현재값을 조회한다."""
    import requests as req
    try:
        resp = req.get(
            "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-price",
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": app_key,
                "appsecret": app_secret,
                "tr_id": "FHKUP03500100",
            },
            params={"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": iscd},
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        o = resp.json().get("output", {})
        close = float(o.get("bstp_nmix_prpr", 0) or 0)
        if not close:
            return None
        change = float(o.get("bstp_nmix_prdy_vrss", 0) or 0)
        change_pct = float(o.get("bstp_nmix_prdy_ctrt", 0) or 0)
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "name": name,
            "value": round(close, 2),
            "change": round(change, 2),
            "changePercent": round(change_pct, 2),
            "open": round(float(o.get("bstp_nmix_oprc", close) or close), 2),
            "high": round(float(o.get("bstp_nmix_hgpr", close) or close), 2),
            "low": round(float(o.get("bstp_nmix_lwpr", close) or close), 2),
            "volume": int(float(o.get("acml_vol", 0) or 0)),
            "date": today,
            "source": "kis",
        }
    except Exception as e:
        print(f"[market/indices] KIS index {iscd} 실패: {e}")
        return None


def _fetch_naver_index(code: str, name: str) -> Optional[dict]:
    """네이버 금융 모바일 API로 코스피/코스닥 지수를 조회한다. (KIS 실패 시 폴백)"""
    import requests as req
    _HEADERS = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
    _BASE = "https://m.stock.naver.com/api/index"

    def _num(s):
        try:
            return float(str(s).replace(",", "").strip())
        except Exception:
            return 0.0

    try:
        basic = req.get(f"{_BASE}/{code}/basic", headers=_HEADERS, timeout=5)
        if basic.status_code != 200:
            return None
        b = basic.json()
        close = _num(b.get("closePrice", 0))
        if not close:
            return None
        change = _num(b.get("compareToPreviousClosePrice", 0))
        change_pct = _num(b.get("fluctuationsRatio", 0))
        date_raw = b.get("localTradedAt", "")[:10]

        integ = req.get(f"{_BASE}/{code}/integration", headers=_HEADERS, timeout=5)
        open_p = high_p = low_p = 0.0
        volume = 0
        if integ.status_code == 200:
            infos = {i["code"]: i["value"] for i in integ.json().get("totalInfos", [])}
            open_p = _num(infos.get("openPrice", 0))
            high_p = _num(infos.get("highPrice", 0))
            low_p  = _num(infos.get("lowPrice", 0))
            volume = int(_num(infos.get("accumulatedTradingVolume", 0)))

        return {
            "name": name,
            "value": round(close, 2),
            "change": round(change, 2),
            "changePercent": round(change_pct, 2),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "volume": volume,
            "date": date_raw,
            "source": "naver",
        }
    except Exception as e:
        print(f"[market/indices] naver index {code} 실패: {e}")
        return None


def _fetch_indices_data() -> dict:
    """지수 데이터를 가져온다 — KOSPI/KOSDAQ: KIS → Naver 폴백, 해외: yfinance (blocking)."""
    import yfinance as yf
    from datetime import timezone

    YFINANCE_TICKERS = {
        "nasdaq":          ("^IXIC",     "나스닥"),
        "dow":             ("^DJI",      "다우존스"),
        "sp500":           ("^GSPC",     "S&P 500"),
        "vix":             ("^VIX",      "VIX"),
        "nikkei":          ("^N225",     "닛케이 225"),
        "shanghai":        ("000001.SS", "상하이종합"),
        "shenzhen":        ("399001.SZ", "선전종합"),
        "exchangeRate":    ("USDKRW=X",  "원/달러"),
        "goldPrice":       ("GC=F",      "금"),
        "oilPrice":        ("CL=F",      "WTI 원유"),
        "silverPrice":     ("SI=F",      "은"),
        "naturalGasPrice": ("NG=F",      "천연가스"),
        "copperPrice":     ("HG=F",      "구리"),
        "wheatPrice":      ("ZW=F",      "밀"),
    }

    result: dict = {}

    # ── KOSPI / KOSDAQ: KIS 우선, 실패 시 Naver 폴백 ───────────────────
    # iscd: 0001=코스피, 1001=코스닥
    KR_INDICES = {
        "kospi":  ("0001", "KOSPI", "코스피"),
        "kosdaq": ("1001", "KOSDAQ", "코스닥"),
    }
    app_key = os.getenv("KIS_APP_KEY", "")
    app_secret = os.getenv("KIS_APP_SECRET", "")

    # KIS 토큰: KISProvider 캐시 우선, 없으면 직접 발급
    kis_token: Optional[str] = None
    if app_key and app_secret:
        kis_provider = next((p for p in market_data_provider.providers if p.name == "kis"), None)
        if kis_provider and kis_provider._access_token and time.time() < kis_provider._token_expires_at:
            kis_token = kis_provider._access_token
        else:
            import requests as _req
            try:
                r = _req.post(
                    "https://openapi.koreainvestment.com:9443/oauth2/tokenP",
                    json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret},
                    timeout=5,
                )
                if r.status_code == 200:
                    kis_token = r.json().get("access_token")
                    # KISProvider 캐시에 저장해 다음 호출에서 재사용
                    if kis_provider and kis_token:
                        kis_provider._access_token = kis_token
                        kis_provider._token_expires_at = time.time() + 23 * 3600
            except Exception as e:
                print(f"[market/indices] KIS 토큰 발급 실패: {e}")

    for key, (iscd, naver_code, name) in KR_INDICES.items():
        data = None
        if kis_token:
            data = _fetch_kis_index(iscd, name, kis_token, app_key, app_secret)
            if data:
                print(f"[market/indices] {name} KIS 소스")
        if not data:
            data = _fetch_naver_index(naver_code, name)
        if data:
            result[key] = data

    # ── 해외지수 / 환율 / 원자재 ──────────────────────────────────────
    tickers_to_fetch = [v[0] for k, v in YFINANCE_TICKERS.items() if k not in result]
    data = None
    if tickers_to_fetch:
        try:
            data = yf.download(
                tickers_to_fetch,
                period="2d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as e:
            print(f"[market/indices] yfinance 다운로드 실패: {e}")

    for key, (ticker, name) in YFINANCE_TICKERS.items():
        if key in result:
            continue
        try:
            if data is None:
                continue
            df = data if len(tickers_to_fetch) == 1 else (
                data[ticker] if ticker in data.columns.get_level_values(0) else None
            )
            if df is None or df.empty:
                continue
            df = df.dropna(subset=["Close"])
            if len(df) < 1:
                continue
            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else last
            close = float(last["Close"])
            prev_close = float(prev["Close"])
            change = round(close - prev_close, 4)
            change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
            result[key] = {
                "name": name,
                "value": round(close, 2),
                "change": change,
                "changePercent": change_pct,
                "open": round(float(last.get("Open", close)), 2),
                "high": round(float(last.get("High", close)), 2),
                "low": round(float(last.get("Low", close)), 2),
                "date": str(df.index[-1].date()),
                "source": "yfinance",
            }
        except Exception as e:
            print(f"[market/indices] yfinance {key}({ticker}) 파싱 실패: {e}")

    return result


@app.get("/market/indices")
async def market_indices():
    """
    글로벌 시장 지수 조회 (서버 측 30초 캐시)
    - KOSPI/KOSDAQ: yfinance 1분봉 실시간
    - 해외지수/환율/원자재: yfinance 일봉
    """
    global _indices_cache

    now = time.time()

    # 캐시 유효: 즉시 반환
    if _indices_cache["data"] is not None and now < _indices_cache["expires_at"]:
        return _indices_cache["data"]

    # 다른 요청이 이미 로딩 중이면 stale 데이터 반환 (있을 때)
    if _indices_cache["loading"]:
        if _indices_cache["data"] is not None:
            return _indices_cache["data"]

    # 캐시 갱신
    _indices_cache["loading"] = True
    try:
        data = await asyncio.to_thread(_fetch_indices_data)
        _indices_cache["data"] = data
        _indices_cache["expires_at"] = time.time() + _INDICES_TTL
        return data
    finally:
        _indices_cache["loading"] = False


@app.post("/market/signals")
def market_signals(body: dict):
    """
    실제 데이터 기반 전략 시그널 평가
    body: {
        symbols: [...],
        entry_conditions: [...],
        exit_conditions: [...],
        history_days: 60  (optional)
    }
    반환: {date, signals: [{symbol, close, entry_signal, exit_signal, ...}]}
    """
    from engine.signals import SignalEngine
    from engine.indicators import IndicatorEngine

    symbols: list[str] = body.get("symbols", [])
    entry_conditions: list = body.get("entry_conditions", [])
    exit_conditions: list = body.get("exit_conditions", [])
    history_days: int = body.get("history_days", 60)

    if not symbols:
        raise HTTPException(status_code=400, detail="symbols 필드가 필요합니다")

    results = []
    latest_date = None

    sig_engine = SignalEngine()

    for symbol in symbols:
        try:
            df = engine.loader.load_symbol_data(symbol)
            live_quote = body.get("quotes", {}).get(symbol)
            df_live = prepare_signal_dataframe(
                df,
                live_quote,
                entry_conditions,
                exit_conditions,
                engine.ai_engine,
            )
            if df_live is None or len(df_live) == 0:
                results.append({"symbol": symbol, "error": "데이터 없음"})
                continue
            df_slice = df_live.tail(history_days + 15)

            last_row = df_slice.tail(1).to_dicts()[0]
            date_val = last_row["date"]
            date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
            if latest_date is None:
                latest_date = date_str

            entry_signal = False
            exit_signal = False
            entry_reason = None
            exit_reason = None

            if entry_conditions:
                entry_arr, entry_reasons = sig_engine.generate_signals(
                    df_slice, {"conditions": entry_conditions}
                )
                entry_signal = bool(entry_arr[-1])
                entry_reason = entry_reasons[-1]

            if exit_conditions:
                exit_arr, exit_reasons = sig_engine.generate_signals(
                    df_slice, {"conditions": exit_conditions}
                )
                exit_signal = bool(exit_arr[-1])
                exit_reason = exit_reasons[-1]

            results.append({
                "symbol": symbol,
                "date": date_str,
                "close": int(last_row.get("close", 0)),
                "open": int(last_row.get("open", 0)),
                "high": int(last_row.get("high", 0)),
                "low": int(last_row.get("low", 0)),
                "volume": int(last_row.get("volume", 0)),
                "entry_signal": entry_signal,
                "exit_signal": exit_signal,
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
            })
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)})

    return {"date": latest_date or "", "signals": results}


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
        from universe_history import build_universe_sync_log_lines, load_universe_history, record_universe_sync

        stocks: list[dict] = []
        fetch_errors: list[str] = []

        def _fetch_kind(market_type: str, market_label: str) -> list[dict]:
            import requests, io, pandas as pd
            r = _http_session.get(
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

        base_path = Path(__file__).resolve().parent.parent
        stocks_path = base_path / "data" / "korea-stocks.json"
        existing_stocks = []
        if stocks_path.exists():
            with open(stocks_path, "r", encoding="utf-8") as f:
                existing_stocks = json.load(f)

        existing_symbols = {s["symbol"] for s in existing_stocks}
        incoming_symbols = {s["symbol"] for s in stocks}
        added_symbols = [s for s in stocks if s["symbol"] not in existing_symbols]
        delisted_symbols = [s for s in existing_stocks if s["symbol"] not in incoming_symbols]

        # Atomic write (tmp → rename)
        tmp_path = stocks_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(stocks, f, ensure_ascii=False, indent=2)
        tmp_path.rename(stocks_path)

        kospi_cnt = sum(1 for s in stocks if s["market"] == "KOSPI")
        kosdaq_cnt = sum(1 for s in stocks if s["market"] == "KOSDAQ")
        synced_at = datetime.now().astimezone()
        history_entry = record_universe_sync(
            date=synced_at.strftime("%Y-%m-%d"),
            synced_at=synced_at.isoformat(),
            total_count=len(stocks),
            kospi_count=kospi_cnt,
            kosdaq_count=kosdaq_cnt,
            added=added_symbols,
            delisted=delisted_symbols,
        )
        history_store = load_universe_history()
        print(f"[INFO] sync-stocks: {len(stocks)} stocks saved (KOSPI={kospi_cnt}, KOSDAQ={kosdaq_cnt})", flush=True)
        for line in build_universe_sync_log_lines(history_entry, history_store):
            print(line, flush=True)

        return {
            "success": True,
            "count": len(stocks),
            "kospi": kospi_cnt,
            "kosdaq": kosdaq_cnt,
            "date": history_entry["date"],
            "added": len(added_symbols),
            "delisted": len(delisted_symbols),
            "added_symbols": added_symbols,
            "delisted_symbols": delisted_symbols,
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
    backend: str = "ollama"  # "mlx" | "ollama" — 기본값은 ollama (배포 환경 parity)
    model: Optional[str] = None  # None = 기본값 사용
    previous_parsed: Optional[dict] = None  # 수정 모드: 이전 파싱 결과
    # 직전 코치 문장(수정 모드). 코치가 특정 리스크 필드 설정을 권한 뒤 사용자가 "10%"처럼
    # 필드 없이 답할 때, 백엔드가 그 답을 코치가 물은 필드로 귀속하는 데 쓴다(FR-STR-019e).
    previous_coach_text: Optional[str] = None
    # 직전 planner ask 컨텍스트(수정 모드) — 응답의 pending_ask를 프론트가 그대로 에코한다
    # (previous_coach_text와 같은 무상태 컨텍스트 에코 계약). 입력이 이 칩 목록과 정확히
    # 일치하면 결정론 칩 답변 레인(run_chip_answer)이 인터프리터 없이 State에 반영한다.
    pending_ask: Optional[dict] = None
    # 답을 기다리는 되묻기 질문(수정 모드) — pending_ask·previous_coach_text와 같은 무상태
    # 컨텍스트 에코. "3억원"처럼 필드 없이 값만 온 답을 어느 필드로 귀속할지는 이 질문을
    # 함께 본 인터프리터 LLM이 판단한다(백엔드가 원문에서 필드를 추출하지 않는다).
    pending_question: Optional[str] = None
    # 이전 턴까지 "사용자가 명시한" 설정 필드 목록 — 응답의 explicit_fields를 프론트가
    # 그대로 에코한다(pending_ask와 같은 무상태 컨텍스트 에코 계약). ParsedStrategy 왕복은
    # 기본값을 물질화해 provenance를 지우므로, 누적은 이 에코로만 가능하다.
    previous_explicit_fields: Optional[List[str]] = None
    # 값 변경 추적 메타데이터(비권위) — explicit_fields와 같은 무상태 에코 계약.
    # {필드: {source, updated_at, confidence}}. 판정에는 쓰지 않는다.
    previous_field_metadata: Optional[dict] = None
    # 영속 Artifact 상태 에코 — 비싼 도구 산출물의 근거와 유효성 기록.
    previous_artifacts: Optional[dict] = None
    # 직전 턴의 파생 상태 에코 — 변경 영향(무효화·재유효화) 전이 판정의 유일한 입력이다.
    # 파생 상태는 저장하지 않으므로 현재 값만으로는 '방금 그렇게 됐다'를 알 수 없다.
    previous_field_states: Optional[dict] = None

class NLParseResponse(BaseModel):
    parsed: dict
    backtest_request: dict
    symbol_count: int
    clarification_question: Optional[str] = None
    clarification_suggestions: Optional[List[str]] = None
    # 되묻기 우선순위 표시(예: "theme_universe" — FR-STR-071 테마 관련 상장사 질문).
    # 인터프리터 질문이 유니버스 범위 질문을 덮어쓰지 않게 하는 내부 가드의 관측용 노출.
    clarification_priority: Optional[str] = None
    # planner ask 컨텍스트 {topic, question, chips} — 프론트가 다음 파스 요청의
    # pending_ask로 그대로 에코한다(칩 클릭의 결정론 귀속 근거).
    pending_ask: Optional[dict] = None
    # 이번 프롬프트에서 규칙 기반으로 결정적으로 바뀐 리스크 필드 {field: value|null}.
    # 프론트가 자체 정규식으로 재추측하지 말고 이 값을 그대로 신뢰하도록 단일 진실 소스로 제공.
    risk_overrides: Optional[dict] = None
    # 사용자가 **실제로 말한** 설정 필드(universe/max_positions/rebalancing/backtest_period/
    # initial_capital). 판정 근거는 인터프리터 LLM의 구조화 출력뿐이다 — 프론트가 사용자
    # 원문을 정규식으로 재분석해 되묻기 여부를 정하던 계약 위반(hasExplicit*)의 대체
    # 채널이며, risk_overrides와 동일한 "단일 진실 소스" 계약이다.
    explicit_fields: Optional[List[str]] = None
    # 값 변경 추적 메타데이터(비권위, {필드: {source, updated_at, confidence}}).
    # 디버깅·추적 전용 — 되묻기·진행률·실행 가능 여부 판정은 이 값을 보지 않는다.
    field_metadata: Optional[dict] = None
    # 영속 Artifact 상태({산출물: {status, produced_by, source_key}}).
    # 파생 상태와 달리 저장한다 — 재조회가 비싸 "아직 맞나"를 재실행으로 확인할 수 없다.
    artifacts: Optional[dict] = None
    # 변경 영향 범위(설계 스펙 § 8·§ 30) — 이번 턴이 무엇을 쓸 수 없게/있게 만들었나.
    # 내부 추적용이며 사용자 문구를 만들지 않는다(안내는 검증기가 이미 담당).
    impact: Optional[dict] = None
    # 이번 턴 State로 계산한 파생 상태 사이드카(FR-STR-019q). 요청의 previous_field_states
    # 에코 원본이다 — 이 필드가 응답 모델에 없으면 비-SSE 라우트에서 response_model이
    # 잘라내 impact 전이 판정이 성립 불가(2026-08-02 감사 #3 #6, SSE 라우트와 계약 비대칭).
    field_states: Optional[dict] = None
    # 값 미정으로 컴파일에서 제외된 조건 [{"role","label","source_text"}] — 요약이
    # "이해했지만 값 대기"를 표시할 근거. parsed에는 이 조건이 없다(기본값 확정 금지).
    pending_conditions: Optional[List[dict]] = None
    # 룰 파싱의 LLM 검증 리포트(Parse Fidelity Validator). 검증이 안 돌았으면 None.
    parse_validation: Optional[dict] = None
    # 하한선 보정 안내(비차단 notices 채널, 예: 초기자금 100만원 보정).
    notices: Optional[List[str]] = None
    runtime: Optional[dict] = None

_nl_parsers: dict = {}  # backend → NLStrategyParser (lazy singleton)
_nl_parser_status: dict = {"status": "loading", "error": None}  # "ok" | "failed" | "loading"


def _downgrade_unloaded_mlx(resolved: str) -> str:
    """mlx로 결정됐지만 모델이 startup에 로드되지 않았고 강제(LLM_BACKEND=mlx)도 아니면
    ollama로 강등한다. resolve_llm_backend는 mlx_lm 라이브러리 임포트 가능 여부만 보므로,
    라이브러리는 있어도 모델 미로드인 로컬 dev 환경에서 mlx로 결정되면 파스 라우트가 503을
    낸다. 라우트 상단 주석의 '강등' 의도를 실제로 실현한다."""
    if (
        resolved == "mlx"
        and "mlx" not in _nl_parsers
        and os.environ.get("LLM_BACKEND", "").strip().lower() != "mlx"
    ):
        return "ollama"
    return resolved


def _active_nl_parser():
    """등록된 NL 파서를 우선순위(mlx → ollama)로 하나 반환. 없으면 None.
    코치/종목분석이 백엔드와 무관하게 공유 파서를 찾을 때 쓴다."""
    return _nl_parsers.get("mlx") or _nl_parsers.get("ollama")


class PriorityInferenceLock:
    """Single-device inference gate with priority-aware admission."""

    def __init__(self):
        self._condition = threading.Condition()
        self._active = False
        self._next_ticket = 0
        self._waiting: list[tuple[int, int]] = []

    def priority(self, priority: int):
        lock = self

        class _PriorityContext:
            def __enter__(self):
                # Ollama는 별도 서버 프로세스가 동시성을 처리하므로(OLLAMA_NUM_PARALLEL)
                # 인프로세스 직렬화가 불필요·유해하다. MLX(인프로세스 단일 모델, 동시 호출
                # 불안전)일 때만 게이트를 건다. 이로써 모든 호출부가 백엔드에 따라 자동으로
                # 조건부가 된다 — 호출부 수정 불필요.
                from llm_backend import resolve_llm_backend

                self._engaged = resolve_llm_backend() == "mlx"
                if self._engaged:
                    lock.acquire(priority)
                return self

            def __exit__(self, *_args):
                if getattr(self, "_engaged", False):
                    lock.release()
                return False

        return _PriorityContext()

    def acquire(self, priority: int = 1):
        with self._condition:
            ticket = self._next_ticket
            self._next_ticket += 1
            marker = (priority, ticket)
            self._waiting.append(marker)

            while self._active or min(self._waiting) != marker:
                self._condition.wait()

            self._waiting.remove(marker)
            self._active = True

    def release(self):
        with self._condition:
            self._active = False
            self._condition.notify_all()

    def __enter__(self):
        self.acquire(priority=1)
        return self

    def __exit__(self, *_args):
        self.release()
        return False


_mlx_inference_lock = PriorityInferenceLock()

class RuntimeMetricsStore:
    """In-process latency summary for AI runtime paths."""

    def __init__(self, max_recent: int = 100):
        self._lock = threading.Lock()
        self._max_recent = max_recent
        self._samples: list[dict] = []

    def record(self, stage: str, runtime: dict | None) -> None:
        if not runtime:
            return

        sample = {
            "stage": stage,
            "timestamp": time.time(),
            "runtime": dict(runtime),
        }
        with self._lock:
            self._samples.append(sample)
            if len(self._samples) > self._max_recent:
                self._samples = self._samples[-self._max_recent:]

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()

    def snapshot(self) -> dict:
        with self._lock:
            samples = list(self._samples)

        by_stage: dict[str, list[dict]] = {}
        for sample in samples:
            by_stage.setdefault(sample["stage"], []).append(sample["runtime"])

        return {
            "stages": {
                stage: self._summarize(stage_samples)
                for stage, stage_samples in sorted(by_stage.items())
            },
            "recent": samples[-20:],
        }

    def _summarize(self, samples: list[dict]) -> dict:
        total_values = [
            float(sample["total_ms"])
            for sample in samples
            if isinstance(sample.get("total_ms"), (int, float))
        ]
        summary = {
            "count": len(samples),
            "cache_hits": sum(1 for sample in samples if sample.get("cache_hit") is True),
            "cache_misses": sum(1 for sample in samples if sample.get("cache_hit") is False),
        }
        if total_values:
            summary.update({
                "avg_total_ms": round(sum(total_values) / len(total_values), 2),
                "p50_total_ms": self._percentile(total_values, 0.50),
                "p95_total_ms": self._percentile(total_values, 0.95),
                "last_total_ms": round(total_values[-1], 2),
            })
        return summary

    def _percentile(self, values: list[float], percentile: float) -> float:
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
        return round(ordered[index], 2)


_ai_runtime_metrics = RuntimeMetricsStore()


def _record_ai_runtime(stage: str, runtime: dict | None) -> None:
    _ai_runtime_metrics.record(stage, runtime)


def _reset_ai_runtime_metrics_for_tests() -> None:
    _ai_runtime_metrics.reset()


@app.get("/ai/runtime/metrics")
def get_ai_runtime_metrics():
    return _ai_runtime_metrics.snapshot()


@app.post("/ai/runtime/metrics/reset")
def reset_ai_runtime_metrics():
    _ai_runtime_metrics.reset()
    return {"ok": True}


_nl_parse_cache: dict = {}   # cache_key → NLParseResponse dict
_NL_PARSE_CACHE_MAX = 200    # 최대 200개 항목 유지


_virtual_trader = VirtualTrader(market_data_provider, engine.loader, engine.ai_engine)


@app.on_event("startup")
async def startup():
    """서버 시작 시 KIS WebSocket + VirtualTrader 백그라운드 루프 시작"""
    await market_data_provider.start_ws()
    await _virtual_trader.start()


@app.on_event("startup")
def log_universe_status_on_startup():
    try:
        from universe_history import build_universe_startup_log_lines, load_universe_history

        history_store = load_universe_history()
        for line in build_universe_startup_log_lines(history_store):
            print(line, flush=True)
    except Exception as e:
        print(f"[startup] universe-sync 로그 출력 실패 (무시됨): {e}", flush=True)


@app.on_event("shutdown")
async def shutdown():
    """서버 종료 시 백그라운드 루프 정리"""
    await market_data_provider.stop_ws()
    await _virtual_trader.stop()


def _kick_ollama_warmup() -> None:
    """배포/재시작 직후 첫 코치 요청이 Modal 콜드스타트(~2분)를 통째로 떠안지 않도록,
    백그라운드 스레드에서 본문 없는 GET으로 Modal 컨테이너를 미리 깨운다(논블로킹).

    워밍업이 실패하거나 느려도 기동·요청 경로에는 영향이 없다.
    첫 코치 요청은 기존의 요청 내 lazy 워밍업(_ollama_ensure_warm)으로 폴백한다.
    """
    import threading

    from engine.nl_parser import _ollama_ensure_warm

    def _run() -> None:
        try:
            _ollama_ensure_warm()
            print("[startup] Modal LLM 워밍업 완료", flush=True)
        except Exception as e:  # noqa: BLE001 — 워밍업 실패는 비치명적
            print(f"[startup] Modal LLM 워밍업 실패 (무시됨, 첫 요청 시 재시도): {e}", flush=True)

    threading.Thread(target=_run, name="ollama-warmup", daemon=True).start()


def _local_preload_models(parser_model: str) -> list:
    """로컬 Ollama startup에서 적재할 모델 목록.

    2026-08-03 전 슬롯 9B 단일화(분류·파서·코치 4B 폐기 — 사용자 결정) 이후 서비스
    모델은 하나뿐이라 인터프리터 슬롯(미설정 시 파서 모델 폴백)만 적재하면 된다.
    파서 슬롯이 다른 모델로 갈라지는 구성은 지원하지 않는다 — 슬롯을 다시 나누면
    여기서 파서 모델도 함께 적재해야 유휴 후 첫 분류가 콜드 로드를 떠안지 않는다
    (2026-08-03 실측 ~5.5초).
    """
    interpreter_model = (os.environ.get("STRATEGY_INTERPRETER_MODEL") or "").strip()
    return [interpreter_model or parser_model]


def _local_ollama_reachable() -> bool:
    """로컬 Ollama 서버가 실제로 응답하는지 확인한다(모델 적재가 아니라 **서버 생사**).

    적재·prefill 실패는 "첫 호출 시 lazy 로드"로 복구되므로 비치명적이지만, 서버 자체가
    죽어 있으면 그 전제가 성립하지 않는다 — 백엔드는 LLM 없이 기동하고, 사용자에게는
    파싱 회귀처럼 보인다(2026-08-01: 전략 문장에 "일반적인 설명을 준비하지 못했습니다"
    폴백. 분류·파싱·일반답변 세 레인이 동시에 죽는다). 그래서 이 경우만 따로 알린다.
    """
    import urllib.request

    from llm_backend import OLLAMA_BASE_URL, ollama_auth_headers

    try:
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/tags", headers=ollama_auth_headers()
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001 — 어떤 이유든 못 닿으면 죽은 것으로 본다
        return False


def _warn_local_ollama_down() -> None:
    """로컬 Ollama 미기동을 눈에 띄게 알린다 — 조용한 기동이 오진을 만든다."""
    from llm_backend import OLLAMA_BASE_URL

    print(
        "\n"
        "[startup] ⚠️  로컬 Ollama 서버에 닿지 못했습니다 "
        f"({OLLAMA_BASE_URL}) — LLM 없이 기동합니다.\n"
        "[startup]     증상: 전략 입력이 UNKNOWN으로 분류돼 "
        "'해당 주제에 대한 일반적인 설명을 준비하지 못했습니다'로 답합니다.\n"
        "[startup]     조치: `brew services start ollama` (부팅 시 자동 기동) "
        "또는 `ollama serve`\n",
        flush=True,
    )


def _kick_local_ollama_model_preload(model: str) -> None:
    """로컬 Ollama면 서버 시작 직후 백그라운드로 모델을 메모리에 적재한다(첫 호출 지연 제거).

    Ollama는 기본적으로 첫 추론 호출 때 모델을 로드하는데, 로컬 dev에서는 콜드스타트가
    없으므로 startup에서 바로 적재해 첫 파싱/코치 요청이 로드 지연을 떠안지 않게 한다.
    원격(Modal)은 콜드스타트 특성상 GET 워밍업(_kick_ollama_warmup)을 쓰므로 제외한다.
    적재가 느리거나 실패해도 기동·요청 경로엔 영향 없다(첫 호출 시 lazy 로드로 폴백).
    """
    import threading

    from engine.nl_parser import _ollama_preload_model

    def _run() -> None:
        try:
            _ollama_preload_model(model)
            print(f"[startup] 로컬 Ollama 모델 적재 완료: {model}", flush=True)
        except Exception as e:  # noqa: BLE001 — 적재 실패는 비치명적
            print(f"[startup] 로컬 Ollama 모델 적재 실패 (무시됨, 첫 호출 시 로드): {e}", flush=True)

    threading.Thread(target=_run, name="ollama-model-preload", daemon=True).start()


def _kick_system_prompt_prefill(model: str) -> None:
    """전략 대화의 고정 system 프롬프트를 startup에 한 번 흘려 KV 프리픽스 캐시를 채운다.

    모델 적재(_kick_local_ollama_model_preload)와 다른 문제다 — 가중치가 올라와 있어도
    system 프롬프트 자체의 prefill은 매번 새로 계산되고, 그 비용이 지배적이다.
    실측(2026-07-29, 로컬 9B): 인터프리터 system은 20,470자(~8,900 tok)이고
    콜드 prefill 43.6초, 프리픽스 캐시가 살아 있으면 **0.4초**(총 호출 60.2초 → 7.5초).
    planner system(~2,760 tok)도 같은 성질이다.

    두 프롬프트는 대화마다 바뀌지 않으므로 startup에서 각각 1토큰만 생성시켜 캐시를
    올려두면 사용자 첫 요청이 콜드 prefill을 떠안지 않는다. 실패해도 비치명적이다
    (첫 요청이 예전처럼 콜드 prefill을 내면 그만).
    """
    import threading

    def _run() -> None:
        from engine.nl_parser import _ollama_prefill_system_prompt

        for label, build in (
            ("인터프리터", lambda: __import__(
                "strategy_conversation.interpreter.prompts", fromlist=["x"]
            ).build_system_prompt()),
            ("planner", lambda: __import__(
                "strategy_conversation.planner.dag_planner", fromlist=["x"]
            )._system_prompt()),
        ):
            try:
                elapsed = _ollama_prefill_system_prompt(build(), model)
                print(f"[startup] {label} system 프롬프트 prefill 완료 ({elapsed:.1f}s)",
                      flush=True)
            except Exception as e:  # noqa: BLE001 — prefill 실패는 비치명적
                print(f"[startup] {label} system 프롬프트 prefill 실패 (무시됨): {e}",
                      flush=True)

    threading.Thread(target=_run, name="system-prompt-prefill", daemon=True).start()


@app.on_event("startup")
def preload_nl_parser():
    """서버 시작 시 Ollama 기반 NL 파서를 준비한다.

    Ollama는 첫 호출 시 모델을 다운로드/로드하므로, startup에서는 HTTP 클라이언트만 초기화한다.
    Ollama 서버가 없어도 앱 기동을 막지 않는다(첫 파싱 호출 시 에러 발생).
    """
    from engine.nl_parser import NLStrategyParser
    from llm_backend import resolve_llm_backend

    backend = resolve_llm_backend()
    try:
        parser = NLStrategyParser(backend=backend)
        if backend == "ollama":
            parser._init_ollama()  # HTTP 클라이언트 준비 (모델 다운로드/접속은 첫 호출 시)
        else:
            # MLX 명시 사용 (LLM_BACKEND=mlx 환경변수 설정 시)
            parser._init_mlx()
        _nl_parsers[backend] = parser
        _nl_parser_status["status"] = "ok"
        _nl_parser_status["error"] = None
    except Exception as e:
        _nl_parser_status["status"] = "failed"
        _nl_parser_status["error"] = str(e)
        print(f"[startup] NL 파서 준비 실패 (backend={backend}): {e}", flush=True)
        # Ollama 서버가 없으면 첫 호출 시 에러, 앱 기동은 진행
        # MLX는 명시적 요청 시에만 사용 (LLM_BACKEND=mlx)
        if backend == "mlx":
            raise
        return

    # 코치 파서 주입은 NL 파서 상태와 분리한다 — 코치/검증 모듈 import 실패가
    # NL 모델 로드 실패로 오인돼 "AI 모델 로드 실패" 배너가 뜨는 것을 막는다.
    try:
        from api.coach_routes import set_parser as _set_coach_parser
        _set_coach_parser(parser)
    except Exception as coach_err:
        print(f"[startup] 코치 파서 주입 실패 (무시됨): {coach_err}", flush=True)

    if backend == "ollama":
        from llm_backend import is_local_ollama
        if is_local_ollama():
            # 서버 생사부터 확인한다 — 죽어 있으면 적재·prefill은 무의미하고(둘 다 실패를
            # 무시한다) 기동만 조용히 성공해 LLM 없는 백엔드가 된다.
            if not _local_ollama_reachable():
                _warn_local_ollama_down()
                return
            # 로컬 dev: 콜드스타트가 없으므로 모델을 즉시 메모리에 적재한다.
            for preload_model in _local_preload_models(parser.ollama_model):
                _kick_local_ollama_model_preload(preload_model)
                # 가중치 적재만으로는 부족하다 — 고정 system 프롬프트의 prefill 비용을
                # 여기서 선지불해 사용자 첫 요청이 콜드 prefill(실측 43초)을 떠안지 않게 한다.
                _kick_system_prompt_prefill(preload_model)
        else:
            # 원격(Modal): 콜드스타트 컨테이너를 GET으로 미리 깨운다.
            _kick_ollama_warmup()


def _ensure_summarize_model_loaded():
    """Ollama 기반 요약 모델은 첫 호출 시 로드되므로 startup 사전 로드 불필요.

    과거 MLX 기반 코드는 제거됨. Ollama는 HTTP 엔드포인트로 접속하므로
    프로세스 메모리에 모델을 로드할 필요가 없다."""
    pass  # Ollama 사용 시 사전 로드 불필요


@app.on_event("startup")
def preload_summarize_model():
    """서버 시작 시 AI 요약용 모델도 미리 로드한다."""
    try:
        with _mlx_inference_lock.priority(2):
            _ensure_summarize_model_loaded()
    except Exception as e:
        print(f"[startup] Summarize 모델 로딩 실패 (무시됨): {e}", flush=True)


@app.get("/model/status")
def get_model_status():
    """NL 파서 모델 로딩 상태 반환"""
    return _nl_parser_status


def _is_llm_connection_error(exc: BaseException) -> bool:
    """예외 체인을 따라가며 LLM 서버(Ollama/Modal) 연결 실패인지 판별한다."""
    markers = (
        "APIConnectionError", "Connection error", "ConnectionError",
        "Connection refused", "Max retries", "Failed to establish",
        "Errno 61", "Errno 111",
    )
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = f"{type(current).__name__}: {current}"
        if any(marker in text for marker in markers):
            return True
        current = current.__cause__ or current.__context__
    return False


@app.post("/strategy/parse", response_model=NLParseResponse)
def parse_nl_strategy(request: NLParseRequest):
    """자연어 전략 설명을 ParsedStrategy + BacktestRequest로 변환"""
    return _run_nl_parse(request)


def _finalize_parse_result(result: dict, request: NLParseRequest) -> dict:
    """파스 응답의 공통 마무리 — **모든 반환 지점이 여기를 지난다**.

    provenance 이월과 파생 상태 재계산을 개별 반환 지점에 흩어 두면 새 레인이 생길 때마다
    빠뜨린다(실제로 field_states가 레인 2곳에만 있었다). 순서가 중요하다: 값 축이
    explicit_fields를 입력으로 쓰므로 provenance가 먼저 확정돼야 한다.
    """
    # provenance 이월 — 인터프리터가 판정하지 않은 턴(폴백·레거시 레인)에서도 이전
    # 턴까지의 명시 필드를 잃지 않는다(프론트 에코 계약의 무상태 누적).
    if result.get("explicit_fields") is None:
        result["explicit_fields"] = list(request.previous_explicit_fields or [])
    _drop_rejected_provenance(result)
    _ensure_field_states(result)
    _ensure_field_metadata(result, request)
    _ensure_artifacts(result, request)
    _ensure_impact(result, request)
    _flag_unresolved_universe_ask(result, request)
    return result


def _flag_unresolved_universe_ask(result: dict, request: NLParseRequest) -> None:
    """직전 턴의 유니버스 범위 확인 질문이 답변 없이 소멸하면 notices로 알린다.

    2026-08-02 감사 #2: "ESS 관련주로 바꿔줘"에 "'전력저장장치(ESS)'로 바꿀까요?"라고
    확인을 물은 다음 턴, 사용자가 그 확인과 무관한 답을 하면(예: 매수조건 chip) DAG가
    그 확인을 재질문·안내 없이 버리고 다음 화제로 넘어갔다 — 유니버스는 이전 값(예:
    반도체)에 그대로 머물렀는데 사용자는 그 사실을 알 방법이 없었다. dag.py의
    NodeStatus.INVALIDATED는 관측(trace)에만 쓰이고 응답에 닿지 않는다(§ 12.2 설계
    의도가 실행에 배선되지 않음) — 이 함수가 그 최소 보정이다.
    판정은 두 턴의 pending_ask.topic 라벨(LLM/planner 출력)과 유니버스 관련 필드값의
    동일성 비교뿐이다 — 사용자 원문을 다시 읽지 않는다(계약 § 판정 기준: LLM 출력 정규화).
    """
    old_ask = request.pending_ask
    if not isinstance(old_ask, dict) or not old_ask.get("question"):
        return
    from strategy_conversation.primary import _is_universe_topic

    if not _is_universe_topic(old_ask.get("topic")):
        return  # 유니버스 확인 질문이 아니면 이 가드의 대상이 아니다
    new_ask = result.get("pending_ask")
    if _is_universe_topic((new_ask or {}).get("topic")):
        return  # 유니버스 질문이 이어지고 있다 — 정상 재질문
    prev_parsed = request.previous_parsed or {}
    new_parsed = result.get("parsed") or {}
    universe_fields = ("universe", "sector", "theme_universe", "etf_theme", "target_symbols")
    if any(prev_parsed.get(f) != new_parsed.get(f) for f in universe_fields):
        return  # 유니버스가 실제로 바뀌었다 — 답변된 것으로 본다
    notices = list(result.get("notices") or [])
    notices.append(
        f"앞서 물었던 \"{old_ask['question']}\"에는 아직 답하지 않아 유니버스는 바뀌지 않았어요."
    )
    result["notices"] = notices


def _drop_rejected_provenance(result: dict) -> None:
    """허용 범위를 벗어나 버려진 설정의 '사용자가 말했다' 기록을 떼어낸다.

    값은 이미 기본값으로 되돌아갔다. 기록만 남으면 되묻기 게이트가 그 기본값을 사용자
    확정으로 보고 그대로 실행 가능 상태로 넘긴다 — 사용자는 설정하지 못했다는 안내를
    읽고도 자기가 말한 적 없는 1천만원으로 백테스트를 돌리게 된다.
    파생 상태(field_states)도 이 provenance를 입력으로 쓰므로 함께 무효화해 재계산시킨다.
    """
    rejected = result.pop("reask_fields", None)
    if not rejected:
        return
    result["explicit_fields"] = [
        field for field in (result.get("explicit_fields") or []) if field not in rejected
    ]
    result["field_states"] = None


def _ensure_impact(result: dict, request: NLParseRequest) -> None:
    """변경 영향 범위 — 파생 상태가 확정된 **뒤에** 직전 턴과 대조한다."""
    try:
        from strategy_conversation.conversation.impact import compute_impact

        result["impact"] = compute_impact(
            request.previous_field_states,
            result.get("field_states"),
            result.get("changed_fields"),
        )
    except Exception:  # noqa: BLE001 — 추적 정보가 파스를 깨면 안 된다
        logger.warning("변경 영향 계산 실패 — 생략", exc_info=True)


def _ensure_artifacts(result: dict, request: NLParseRequest) -> None:
    """영속 Artifact 상태 — 비싼 도구 산출물이 아직 유효한지 근거 대조로 판정한다.

    파생 상태와 달리 **저장한다**: 지식그래프 조회 결과를 "아직 맞나" 확인하려고 다시
    조회할 수는 없으므로, 무엇을 근거로 만들었는지를 남겨 두고 근거만 대조한다.
    """
    try:
        from strategy_conversation.conversation.artifacts import evaluate_artifacts

        result["artifacts"] = evaluate_artifacts(
            result.get("parsed"), request.previous_artifacts)
    except Exception:  # noqa: BLE001 — 추적 정보가 파스를 깨면 안 된다
        logger.warning("Artifact 상태 판정 실패 — 생략", exc_info=True)


# 값이 사용자 발화가 아니라 지식 조회에서 온 필드 — 테마 유니버스가 채운 종목 목록이다.
# 이 구분은 저장된 구조(theme_universe 출처 표기)를 읽을 뿐 원문을 보지 않는다.
_KG_SOURCED_FIELDS = frozenset({"target_symbols", "theme_universe"})


def _ensure_field_metadata(result: dict, request: NLParseRequest) -> None:
    """값 변경 추적 메타데이터(비권위) — 이번 턴에 바뀐 필드에 출처·시각을 기록한다.

    **판정에 쓰지 않는다.** 되묻기·진행률·실행 가능 여부·분기는 값과 explicit_fields만
    본다(2026-07-30 사용자 결정 — 소비자가 생기기 전까지 비권위 메타데이터).
    바뀐 필드가 없으면 이전 기록을 그대로 이월한다.
    """
    from strategy_conversation.response.provenance import merge_field_metadata

    changed = result.get("changed_fields")
    previous = request.previous_field_metadata
    if not changed:
        result["field_metadata"] = dict(previous) if isinstance(previous, dict) else None
        return
    parsed = result.get("parsed")
    # 이 시점의 parsed는 model_dump() dict다 — getattr만 쓰면 항상 None이라
    # KNOWLEDGE_GRAPH 출처 표기가 죽는다(artifacts._field와 같은 2026-08-02 감사 #3 결함).
    theme = (parsed.get("theme_universe") if isinstance(parsed, dict)
             else getattr(parsed, "theme_universe", None))
    interpreter_meta = (result.get("runtime") or {}).get("interpreter") or {}
    kg_changed = [f for f in changed if theme and f in _KG_SOURCED_FIELDS]
    user_changed = [f for f in changed if f not in kg_changed]
    now = datetime.now(timezone.utc).isoformat()
    confidence = interpreter_meta.get("confidence")
    metadata = merge_field_metadata(
        previous, user_changed, source="USER", updated_at=now, confidence=confidence)
    metadata = merge_field_metadata(
        metadata, kg_changed, source="KNOWLEDGE_GRAPH", updated_at=now,
        confidence=confidence)
    result["field_metadata"] = metadata or None


def _ensure_field_states(result: dict) -> None:
    """파이프라인 불변조건 — 모든 응답은 **이번 턴의 State로 계산한** 파생 상태를 싣는다.

    파생 상태(NOT_APPLICABLE·INVALID·CONFLICTED)는 저장하지 않는 계산값이다. 그래서
    어떤 레인이 계산을 건너뛰면 값이 비는 게 아니라 **프론트가 직전 턴의 사본을 계속
    쓴다** — 전략이 바뀐 턴에서는 그것이 틀린 표시가 된다(실측: 칩 답변으로 최대 보유가
    10→5로 바뀌어도 상태 맵은 이전 턴 것이 그대로 남았다. 계산하는 레인은 초기 파스와
    수정 성공 둘뿐이었고, 칩 답변·확정·유니버스 칩·설명·되묻기 레인은 전부 빠져 있었다).

    인터프리터 레인은 (strategy, report)를 이미 들고 있어 같은 계산을 더 싸게 마쳤다 —
    그 결과가 있으면 그대로 둔다(계산을 건너뛰는 것이 아니라 재사용하는 것이다).
    """
    if result.get("field_states"):
        return
    try:
        from strategy_conversation.primary import derive_field_states

        result["field_states"] = derive_field_states(
            result["parsed"], result.get("explicit_fields")) or None
    except Exception:  # noqa: BLE001 — 표시용 부가 정보가 파스를 깨면 안 된다
        logger.warning("파생 상태 계산 실패 — 생략", exc_info=True)


def _build_parse_result(request: NLParseRequest, backend: str, parsed, validation_report,
                        *, load_ms: float, parse_ms: float, request_started: float,
                        scan_prompt_for_sector: bool = True,
                        pending_conditions: Optional[List[dict]] = None) -> dict:
    """parsed(ParsedStrategy)로부터 응답 payload를 구성한다.

    인라인 경로(_run_nl_parse)와 후행 검증 경로(_complete_deferred_validation)가 공유한다 —
    교정된 전략도 하한선 보정·DSL 변환·되묻기 감지를 동일하게 거치게 하기 위한 추출.

    scan_prompt_for_sector: False면 원문 스캔(apply_theme_universe·
    detect_unresolved_sector_clarification·detect_symbol_typo_clarification)을 건너뛴다 — 인터프리터 primary 레인은
    LLM이 뽑은 표현의 term-in 체인(§ 11-3, primary._resolve_sector_terms_term_in)이
    담당하고, 해석 실패 결과에 원문 스캔이 전략을 만들어 붙이면 실패 의미가 왜곡된다.
    레거시 레인(off/shadow 기본 경로·후행 검증)만 True를 유지한다(1d 이관 대상).
    """
    from engine.nl_parser import (
        apply_single_asset_adjustments,
        apply_theme_universe,
        build_unsupported_concept_notice,
        concepts_covered_by_pending,
        concepts_expressed_in_strategy,
        detect_etf_factor_conflict,
        detect_missing_entry_clarification,
        detect_symbol_typo_clarification,
        detect_unresolved_sector_clarification,
        enforce_strategy_minimums,
        synthesize_risk_overrides,
    )
    from engine.nl_parser import MAX_INITIAL_CAPITAL, backtest_window_is_empty
    from engine.strategy_converter import to_backtest_request

    # 허용 범위를 벗어나 **버려지는** 설정은 enforce가 기본값으로 되돌리므로 **되돌리기
    # 전에** 잡아 두어야 한다 — 그러지 않으면 되돌아온 기본값이 '사용자가 정한 값'
    # (explicit)으로 남아 되묻기 게이트가 그냥 통과시킨다.
    reask_fields = []
    if parsed.initial_capital > MAX_INITIAL_CAPITAL:      # 초기 자금 상한 100억
        reask_fields.append("initial_capital")
    if backtest_window_is_empty(parsed):                  # 창 전체가 데이터 밖(미래·1996 이전)
        reask_fields.append("backtest_period")
    # 설정값 범위 보정 — 비현실적 입력(초기자금 300원·0일 보유·3일 모멘텀·0% 손절 등)을
    # 자동 보정/제거하고 사용자에게 안내한다(모든 파싱 경로 공통).
    notices = enforce_strategy_minimums(parsed)
    # 스키마가 표현할 수 없는 재무 조건은 그 항목만 드롭됐다(전체 실패 금지) — 조용한 드롭은
    # 전략 의미를 몰래 바꾸므로 비차단 안내로 알린다.
    dropped_filters = list(getattr(parsed, "dropped_filter_notices", None) or [])
    if dropped_filters:
        notices.append(
            f"'{', '.join(dropped_filters)}' 조건은 해석할 수 없어 전략에서 제외했어요."
        )
    # 테마 관련 검증 상장사 자동 적용(FR-STR-071 ④ 개정, 사용자 결정 2026-07-25) —
    # 되묻기 없이 target_symbols를 설정한다. 적용 안내는 사용자 notices에 싣지 않는다
    # (2026-08-02 사용자 지시 — 요약 카드가 유니버스를 이미 표시, 반환 문구는 신호 전용).
    # DSL 변환(to_backtest_request) 전에 실행해야 지정 종목 모드로 심볼이 해석된다.
    theme_notice = apply_theme_universe(parsed, request.prompt) if scan_prompt_for_sector else None
    # 지정 종목(단일 종목) 백테스트: 청산 조건 누락을 추천 기본값/안내로 보정한다(FR-STR-068).
    # 조용한 임의 실행 방지 — 무엇이 추천 적용됐는지 notices로 알린다.
    parsed, single_asset_notices = apply_single_asset_adjustments(parsed)
    notices.extend(single_asset_notices)
    # 단일 종목 프로파일 리뷰(FR-STR-068b): 종목의 실제 데이터 통계와 대조해 희소/과다
    # 신호·재무 데이터 미보유·PIT 적용 사실·데이터 품질을 비차단 안내한다. 프로파일 조회
    # 실패는 조용히 무시된다(파싱 흐름 보호).
    if len(getattr(parsed, "target_symbols", None) or []) == 1:
        from engine.single_asset_review import review_single_asset_strategy
        profile_notices = review_single_asset_strategy(parsed)
        notices.extend(profile_notices)
        if profile_notices:
            print(
                f"[SINGLE-ASSET-REVIEW] symbol={parsed.target_symbols[0]} "
                f"notices={len(profile_notices)}", flush=True,
            )
    # 언급한 업종/테마를 지원 섹터로 매핑하지 못했으면 조용히 전체 시장으로 강등하지 않고
    # 되묻는다(오타 '재약주'→'제약주'·목록 밖 표현 정정 기회). 되묻기로 능동 처리하는 경우
    # 수동 안내에서 'sector'를 빼 중복(안내 + 질문)을 피한다.
    if scan_prompt_for_sector:
        sector_reask_q, sector_reask_s = detect_unresolved_sector_clarification(parsed, request.prompt)
    else:
        sector_reask_q, sector_reask_s = None, None
    # 미지원 개념(배당·섹터·변동성 등)은 LLM 폴백조차 스키마가 표현 불가라 조용히
    # 누락/유사 해석될 수 있다 → 침묵 왜곡 대신 비차단 안내로 알린다. 테마 자동 적용이
    # 관련 상장사를 확정한 경우(theme_notice)에도 'sector'를 뺀다 — '설정했어요' 안내와
    # '지원되지 않아요' 안내가 한 응답에 공존하는 모순 방지. 원문 섹터 스캔을 끈 레인은
    # term-in 체인이 섹터 처리의 단일 권위라 항상 'sector'를 뺀다(중복 안내 방지).
    # 전략이 실제로 표현한 개념(현금흐름 증가율·이동평균 상하 관계 등)도 뺀다 — 반영됐는데
    # "지원되지 않아요"가 함께 나가던 오탐(2026-08-01). 판정은 컴파일 결과만 본다.
    unsupported_exclude = concepts_expressed_in_strategy(parsed, request.prompt)
    # 값 대기 조건도 같은 계약 — 컴파일 결과에는 없지만 '이해한 조건'이다. 되묻는 그 응답에
    # "지원되지 않아요"가 함께 나가던 오탐(2026-08-04 '고배당률 종목 투자 전략').
    unsupported_exclude |= concepts_covered_by_pending(pending_conditions)
    if sector_reask_q or theme_notice or not scan_prompt_for_sector:
        unsupported_exclude.add("sector")
    unsupported_notice = build_unsupported_concept_notice(
        request.prompt, exclude=unsupported_exclude or None,
    )
    if unsupported_notice:
        notices.append(unsupported_notice)
    convert_started = time.perf_counter()
    backtest_req = to_backtest_request(parsed)
    convert_ms = round((time.perf_counter() - convert_started) * 1000, 2)

    print(f"[NL-PARSE] filters={len(parsed.fundamental_filters)}, entry={len(parsed.entry_signals)}, symbols={len(backtest_req['symbols'])}", flush=True)

    runtime = {
        "cache_hit": False,
        "backend": backend,
        "load_ms": load_ms,
        "parse_ms": parse_ms,
        "convert_ms": convert_ms,
        "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
    }
    # 이번 프롬프트에서 바뀐 리스크 필드(단일 진실 소스). 프론트가 그대로 신뢰한다.
    # 결정적 추출이 놓친 구어체("10% 이익 나면 팔아줘")는 파서(LLM 포함) 결과로 보완한다.
    risk_overrides = synthesize_risk_overrides(
        request.prompt, parsed, request.previous_parsed
    )
    # 미해결 업종 되묻기를 최우선으로 둔다 — 종목 범위(유니버스/섹터)가 진입 조건보다 먼저
    # 정해져야 하고, 조용한 전체 시장 강등을 막는다.
    clarification_question, clarification_suggestions = sector_reask_q, sector_reask_s
    # 테마 관련 상장사는 이제 되묻지 않고 자동 적용된다(apply_theme_universe — FR-STR-071
    # ④ 개정). 미해결 업종/테마 질문(되묻기·검색 후 '찾을 수 없음' 종결 안내)에는 우선순위
    # 마커를 실어 프론트 explicit 설정 게이트·primary 인터프리터 질문이 이 질문을 삼키지
    # 않게 한다('리센즈 관련주'가 조용히 시장 질문으로 강등되던 회귀, 2026-07-26).
    clarification_priority = "sector_unresolved" if sector_reask_q else None
    # 종목명 오타로 지정 종목을 잃었으면 '혹시 이 종목?'을 먼저 되묻는다 — 조용히 전체 시장으로
    # 진행하지 않도록, 진입 조건보다 앞서 종목 범위를 확정한다(자모 근접 매칭, 자동 치환 아님).
    # 원문 스캔은 레거시 레인 전용이다(§ 11-3 섹터 이관과 동일) — primary 레인은 LLM이
    # universe.symbols로 뽑은 표현만 후보로 보는 term-in 경로가 담당한다.
    if clarification_question is None and scan_prompt_for_sector:
        clarification_question, clarification_suggestions = detect_symbol_typo_clarification(
            parsed, request.prompt
        )
    # ETF 유니버스 × 기업 재무지표 충돌: 조용히 무시하지 않고 이유 설명 + 기술 지표
    # 대안 제안으로 되묻는다(universe_capabilities 레지스트리 판정). 충돌이 없으면
    # 진입(종목 선정) 규칙을 통째로 잃었을 때의 되묻기를 검사한다.
    if clarification_question is None:
        clarification_question, clarification_suggestions = detect_etf_factor_conflict(
            parsed, request.prompt
        )
    if clarification_question is None:
        clarification_question, clarification_suggestions = detect_missing_entry_clarification(
            parsed, request.prompt
        )
    # 복수 지정 종목 '한 종목만 고르기' 되묻기(detect_symbol_ambiguity)는 폐지됐다(사용자
    # 결정 2026-07-26 — "종목을 교체 할 수 있나?"에 종목 선택 칩이 뜨던 사고). 여러 종목이
    # 지정되면 되묻지 않고 전체를 함께 백테스트하며, 축소·교체는 채팅 수정 요청이 처리한다.
    # 백테스트 최소 조건(유니버스·진입·청산·손절·익절)이 하나라도 비면, "현재 상태로도 실행
    # 가능"으로 진행시키지 않고 채우도록 가이드한다(2026-07-22 정책). clarification이 뜨면
    # 프론트가 실행 버튼을 숨기고 안내 칩을 보여준다. 단일 종목 '기간 종료까지 보유' 안내는
    # 이 게이트와 모순이라 함께 제거한다.
    gate_pending_ask = None
    if clarification_question is None:
        from engine.nl_parser import next_incomplete_backtest_slots
        from strategy_conversation.primary import _pending_ask_payload

        gate_slots = next_incomplete_backtest_slots(parsed, request.prompt)
        if gate_slots:
            slot = gate_slots[0]
            clarification_question = slot.question
            clarification_suggestions = list(slot.suggestions)
            notices = [n for n in notices if "기간 종료까지 보유" not in n]
            # 이 게이트의 질문에도 결속을 붙인다(2026-07-31). 칩은 이미 슬롯 SOT에
            # 있었는데 pending_ask만 None으로 하드코딩돼 있어, 여기서 나간 질문의 답은
            # 다음 턴에 귀속 근거를 잃고 일반 분류 레인으로 떨어졌다(실측 4/13턴).
            # topic은 슬롯 라벨 — 물질화 기본값과 같은 칩을 확정 칩으로 살리는 판정이
            # 이 라벨로 필드를 찾는다.
            gate_pending_ask = _pending_ask_payload(
                clarification_question, clarification_suggestions, slot.slot, parsed
            )
            if gate_pending_ask is not None:
                clarification_suggestions = gate_pending_ask["chips"]
    return {
        "parsed": parsed.model_dump(),
        "backtest_request": backtest_req,
        "symbol_count": len(backtest_req["symbols"]),
        "clarification_question": clarification_question,
        "clarification_suggestions": clarification_suggestions,
        "clarification_priority": clarification_priority,
        # 최소 조건 게이트가 낸 질문의 결속. primary 경로의 planner ask는
        # apply_primary_meta가 이 자리를 덮어쓴다.
        "pending_ask": gate_pending_ask,
        # 진행 골격 8칸의 두 상태 축(설계 스펙 § 5) — 응답 조립 끝에서 불변조건으로
        # 채워진다(_ensure_field_states). 여기서는 자리만 잡는다.
        "field_states": None,
        # 이 턴이 바꾼 필드 이름(설계 스펙 § 19) — 프론트가 변경 이력에 쌓아 되돌리기의
        # 근거로 쓴다. 수정 턴에서만 채워진다(최초 파스는 되돌릴 이전 상태가 없다).
        "changed_fields": None,
        # 허용 범위를 벗어나 **버려진** 설정 필드 — provenance를 떼어내 다시 묻게 한다.
        # 응답에 나가지 않는 내부 신호로, _finalize_parse_result가 소비하며 제거한다.
        "reask_fields": reask_fields or None,
        # 값 변경 추적 메타데이터(비권위) — _finalize_parse_result가 채운다.
        "field_metadata": None,
        # 영속 Artifact 상태 — _finalize_parse_result가 채운다.
        "artifacts": None,
        # 변경 영향 범위 — _finalize_parse_result가 채운다.
        "impact": None,
        "risk_overrides": risk_overrides,
        "parse_validation": validation_report,
        "notices": notices,
        "runtime": runtime,
    }


def _store_nl_parse_cache(cache_key, result: dict) -> None:
    """파싱 결과 캐시 저장(최대 크기 초과 시 가장 오래된 항목 제거)."""
    if len(_nl_parse_cache) >= _NL_PARSE_CACHE_MAX:
        oldest_key = next(iter(_nl_parse_cache))
        del _nl_parse_cache[oldest_key]
    _nl_parse_cache[cache_key] = result


def _complete_deferred_validation(defer_ctx: dict):
    """SSE 결과 전송 후의 후행 LLM 검증(비차단 검증의 2단계).

    교정이 적용된 경우에만 갱신된 result payload를 반환한다(스트림이 result_update로 후속
    전송). 리포트만 있고 교정이 없으면 캐시의 parse_validation만 채우고 None을 반환한다 —
    프론트는 리포트 내용을 표시하지 않으므로 재전송이 무의미하다. 교정 시 캐시도 교정본으로
    갱신해 동일 프롬프트 재요청이 교정 전 결과를 돌려주지 않게 한다.
    """
    from engine.parse_validator import validate_parse

    from observability import span
    from observability.agent_trace import state_diff

    request = defer_ctx["request"]
    parsed = defer_ctx["parsed"]
    started = time.perf_counter()
    with span("Validation · 후행 파스 검증", "state",
              inputs={"user_input": request.prompt}) as trace:
        validated, report = validate_parse(defer_ctx["parser"], request.prompt, parsed)
        trace.output(corrected=validated is not parsed, report=report,
                     state_diff=state_diff(parsed, validated)
                     if validated is not parsed else None)
    cache_key = defer_ctx["cache_key"]
    if validated is parsed:
        cached = _nl_parse_cache.get(cache_key)
        if cached is not None:
            cached["parse_validation"] = report
        return None
    result = _build_parse_result(
        request, defer_ctx["backend"], validated, report,
        load_ms=0.0,
        parse_ms=round((time.perf_counter() - started) * 1000, 2),
        request_started=started,
    )
    extra_notices = defer_ctx.get("extra_notices") or []
    if extra_notices:
        result["notices"] = extra_notices + list(result.get("notices") or [])
    _finalize_parse_result(result, defer_ctx["request"])
    _store_nl_parse_cache(cache_key, result)
    return result


def _learn_unknown_sector_term(prompt: str, parser, on_stage=None) -> Optional[str]:
    """어휘 밖 업종/테마 언급을 파싱 전에 검색 그라운딩으로 학습한다(FR-STR-069 파싱 경로).

    '마운자로 관련주'처럼 정규식·지식그래프가 모르는 테마가 파싱 경로로 들어오면
    빌더 경로처럼 인터넷 검색 학습이 없어 조용히 미지원 처리되던 공백 보정 —
    학습되면 어휘집→지식그래프 합성으로 이후 결정적 섹터 추출(_extract_sector)이
    규칙·LLM 폴백·인터프리터 오버라이드·수정 전 경로에서 그대로 해석한다.
    반환: 해석 안내 notice 문구 | None(게이트 미해당·학습 실패·매핑 불가)."""
    from engine.term_grounding import learn_sector_term, lexicon_entry, search_available

    if not search_available():
        return None

    def chat(system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
        with _mlx_inference_lock.priority(0):
            return parser.chat(system_prompt, user_msg, max_tokens=max_tokens)

    stage_entered = False

    def on_stage_cb(stage: str):
        nonlocal stage_entered
        stage_entered = True
        if on_stage is not None:
            on_stage(stage)

    try:
        sector = learn_sector_term(
            prompt, chat,
            on_search=lambda: on_stage_cb("searching"),
            on_kg_lookup=lambda: on_stage_cb("kg_lookup"),
        )
    except Exception as exc:  # noqa: BLE001 — 그라운딩 실패가 파싱을 막으면 안 된다
        print(f"[NL-PARSE] 용어 그라운딩 실패(무시): {exc}", flush=True)
        return None
    finally:
        if stage_entered and on_stage is not None:
            on_stage("parsing")
    if not sector:
        return None
    entry = lexicon_entry(prompt)
    term = (entry or {}).get("term")
    print(f"[NL-PARSE] 용어 그라운딩: '{term or prompt}' → 섹터 '{sector}'", flush=True)
    if term:
        return (
            f"'{term}'은(는) 인터넷 검색으로 확인해 '{sector}' 업종 관련으로 해석했어요. "
            "다른 업종을 원하시면 말씀해 주세요."
        )
    return f"말씀하신 테마를 '{sector}' 업종 관련으로 해석했어요."


_INTERPRETATION_FAILURE_MESSAGE = (
    "요청을 전략 조건으로 해석하지 못했어요. 바꾸거나 추가하고 싶은 내용을 조금 더 "
    "구체적으로 알려주시면 그대로 반영할게요."
)
# 되묻기 칩은 백엔드 답변 프로토콜의 일부다(UI_GUIDELINES §17) — 기존 수정 되묻기와 같은
# 라벨을 재사용한다(클릭 시 결정론 fast-path가 즉시 확정하는 완결 지시문).
_INTERPRETATION_FAILURE_MODIFY_CHIPS = [
    "손절을 10%로 변경", "익절을 20%로 변경", "최대 10종목으로 변경",
    "백테스트 기간을 5년으로 변경", "직접 입력",
]
# 전략이 아직 없는 상태(초기 파스 실패)에는 '변경' 칩이 가리킬 대상이 없다 — 새 칩 라벨을
# 지어내지 않고, 어떻게 말하면 되는지를 문장으로만 안내한다.
_INTERPRETATION_FAILURE_CREATE_MESSAGE = (
    "요청을 전략 조건으로 해석하지 못했어요. 진입·청산 규칙을 문장으로 알려주시면 그대로 "
    "만들어 드릴게요. 예: '5일 이동평균이 20일 이동평균을 위로 뚫으면 매수하고 아래로 뚫으면 "
    "매도, 손절 10%'"
)


def _interpretation_failure_result(request: NLParseRequest, backend: str, request_started: float):
    """해석 실패를 500이 아니라 되묻기 응답으로 돌려준다(None이면 구성 실패).

    해석 파이프라인의 어떤 레이어도 요청을 실패시킬 권한이 없다 — 레이어의 결과는 "처리했음"
    또는 "내 소관 아님"뿐이고, 예외는 후자로 취급한다. 500은 인프라 장애(LLM 서버 다운 등,
    503 경로) 전용이다. 기존 전략이 있으면 그대로 보존해 대화 교착("무엇을 입력해도 같은
    에러", 2026-07-26)을 원천 차단한다.
    """
    from engine.nl_parser import ParsedStrategy

    try:
        if request.previous_parsed:
            parsed = ParsedStrategy.model_validate(request.previous_parsed)
            question, chips = _INTERPRETATION_FAILURE_MESSAGE, _INTERPRETATION_FAILURE_MODIFY_CHIPS
        else:
            parsed = ParsedStrategy(description=request.prompt)
            question, chips = _INTERPRETATION_FAILURE_CREATE_MESSAGE, None
        # 실패 보고에 원문 섹터/테마 스캔을 적용하지 않는다 — 해석 실패 결과에 테마
        # 상장사가 자동 적용되면 실패가 전략처럼 위장된다(§ 11-3).
        result = _build_parse_result(
            request, backend, parsed, None,
            load_ms=0.0, parse_ms=0.0, request_started=request_started,
            scan_prompt_for_sector=False,
        )
    except Exception as exc:  # noqa: BLE001 — 되묻기 구성도 실패하면 호출부가 500으로
        print(f"[NL-PARSE] 해석 실패 되묻기 구성 실패(무시): {exc!r}", flush=True)
        return None
    result["clarification_question"] = question
    result["clarification_suggestions"] = chips
    # 우선순위 마커 — 프론트의 explicit 설정 게이트가 이 안내를 삼키지 않게 한다.
    result["clarification_priority"] = "interpretation_failed"
    return _finalize_parse_result(result, request)


def _run_nl_parse(request: NLParseRequest, on_stage=None, defer_holder: dict | None = None):
    """파싱 코어 로직 — 사용자 요청 하나당 Trace 하나의 루트.

    본체는 _run_nl_parse_traced다. 이 함수는 관찰 span만 연다(LangSmith와 로컬
    trace 둘 다 꺼져 있으면 완전한 no-op — observability/tracing.py). 파싱 동작·
    반환값·예외 전파는 전혀 바뀌지 않는다.

    반환 지점이 여러 곳(캐시 히트·되묻기·503·정상)이라 개별 지점에 관찰을 흩으면
    반드시 빠뜨린다 — _finalize_parse_result와 같은 이유로 여기 하나로 모은다.
    """
    from observability import span
    from observability.agent_trace import responder_payload
    from observability.identity import content_hash, trace_identity

    identity = trace_identity(request.prompt, request.previous_parsed)
    with span(
        "NullStock Strategy Agent", "chain", root=True,
        inputs={"user_input": request.prompt,
                "previous_parsed": request.previous_parsed,
                "pending_ask": request.pending_ask,
                "pending_question": request.pending_question},
        metadata={**identity, "backend": request.backend, "model": request.model},
    ) as trace:
        result = _run_nl_parse_traced(request, on_stage=on_stage, defer_holder=defer_holder)
        # 후행 검증(SSE)은 응답을 내보낸 뒤 다른 스레드에서 돈다 — 부모를 실어 보내야
        # 같은 Trace에 붙는다(안 그러면 고아 Trace가 하나 더 생긴다).
        if defer_holder is not None and defer_holder.get("parsed") is not None:
            from observability import current_parent

            defer_holder["trace_parent"] = current_parent()
        # Responder — 사용자에게 실제로 나간 것(스펙 § 8). 별도 span으로 남겨야
        # Trace 계층의 마지막 자리가 비지 않는다.
        with span("Responder", "responder",
                  inputs={"user_input": request.prompt}) as responder:
            responder.output(**responder_payload(result))
        trace.output(**responder_payload(result))
        trace.meta(strategy_id=content_hash((result or {}).get("parsed")),
                   cache_hit=bool(((result or {}).get("runtime") or {}).get("cache_hit")))
        return result


def _run_nl_parse_traced(request: NLParseRequest, on_stage=None,
                         defer_holder: dict | None = None):
    """파싱 코어 로직. on_stage: LLM 폴백 직전 호출되는 콜백(진행 스트리밍용).

    defer_holder: dict를 주면 룰 파스의 LLM 검증을 인라인으로 돌리지 않고(defer), 후행
    검증에 필요한 컨텍스트를 holder에 담아 즉시 응답한다. SSE 스트림 전용 — 호출 측이
    _complete_deferred_validation(holder)로 검증을 마저 실행한다.
    """
    from llm_backend import resolve_llm_backend

    request_started = time.perf_counter()
    # MLX를 쓸 수 없는 환경이면 요청이 "mlx"여도 ollama로 강등한다(프론트 변경 불필요).
    resolved_backend = _downgrade_unloaded_mlx(resolve_llm_backend(request.backend))
    if resolved_backend != request.backend:
        print(f"[NL-PARSE] backend '{request.backend}' 사용 불가 → '{resolved_backend}'로 폴백", flush=True)
    print(f"\n[NL-PARSE] prompt='{request.prompt}', backend={resolved_backend}", flush=True)

    # 캐시 조회 — 동일 프롬프트면 LLM 재호출 없이 즉시 반환
    cache_key = nl_cache_key(request.prompt, resolved_backend, request.model,
                             request.previous_parsed, request.pending_ask,
                             request.pending_question)
    if cache_key in _nl_parse_cache:
        print(f"[NL-PARSE] 캐시 히트 → 즉시 반환", flush=True)
        cached = dict(_nl_parse_cache[cache_key])
        runtime = {
            "cache_hit": True,
            "backend": resolved_backend,
            "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
        }
        cached["runtime"] = runtime
        _record_ai_runtime("parse", runtime)
        return cached

    try:
        from engine.nl_parser import NLStrategyParser

        load_started = time.perf_counter()
        backend = resolved_backend
        if backend not in _nl_parsers:
            if backend == "mlx":
                raise HTTPException(
                    status_code=503,
                    detail="NL parser model was not loaded at startup",
                )
            _nl_parser_status["status"] = "loading"
            _nl_parser_status["error"] = None
            kwargs = {"backend": backend}
            if request.model:
                if backend == "mlx":
                    kwargs["model"] = request.model
                else:
                    kwargs["ollama_model"] = request.model
            _nl_parsers[backend] = NLStrategyParser(**kwargs)

        parser = _nl_parsers[backend]
        # MLX 단일 추론 락을 게이트로 주입 — parser.parse/parse_modification의 LLM 구조화
        # 생성(_parse_mlx/_modify_mlx)만 직렬화된다. priority()는 backend가 mlx일 때만
        # 실제로 락을 걸므로 ollama에서는 no-op이다. 이로써 백엔드별 분기 없이 parse()의
        # 단일 하이브리드 경로(규칙→가드→검증→LLM 폴백)를 공유한다(드리프트 방지).
        parser.inference_gate = lambda: _mlx_inference_lock.priority(0)
        if backend == "mlx":
            from api.coach_routes import set_parser as _set_coach_parser
            _set_coach_parser(parser)
        load_ms = round((time.perf_counter() - load_started) * 1000, 2)
        # 어휘 밖 업종/테마 사전 학습(FR-STR-069) — 큐가 있는데 결정적 추출이 실패한 입력만
        # 검색 그라운딩으로 학습한다(어휘집 캐시 — 같은 용어 재검색 없음). 학습되면 아래
        # 파싱(규칙·수정)의 결정적 섹터 추출이 그대로 해석한다.
        # primary '초기 파스'는 이 원문 스캔 학습을 건너뛴다 — 인터프리터가 뽑은 미해결
        # 표현만 term-in으로 학습한다(§ 11-3, primary._ground_sector_term). 수정 레인은
        # 결정적 섹터 배선이 학습 어휘를 소비하므로 유지(단계 3 이관 대상).
        from strategy_conversation.primary import primary_enabled as _primary_on
        grounding_notice = None
        if request.previous_parsed or not _primary_on():
            grounding_notice = _learn_unknown_sector_term(request.prompt, parser, on_stage=on_stage)
        parse_started = time.perf_counter()
        # 룰베이스 파싱 결과의 LLM 검증 리포트(on_validation 콜백으로 수집). 스레드 로컬한
        # holder라 동시 요청 간 경합이 없다.
        validation_holder: dict = {}
        # LLM Interpreter primary 경로가 채우는 질문/안내/메타(초기 파스 전용)
        primary_holder: dict = {}
        def _capture_validation(report):
            validation_holder["report"] = report
        if request.previous_parsed:
            print(f"[NL-PARSE] 수정 모드 (diff)", flush=True)
            # Phase 4 후속 ①: planner ask 칩 클릭의 결정론 귀속. 입력이 직전 planner
            # 질문(pending_ask 에코)의 칩과 정확히 일치하면 새 수정 요청이 아니라 열거형
            # 옵션 선택이다 — 되묻기 가드·수정 인터프리터(LLM)보다 먼저 결정론으로 State에
            # 반영하고 다음 질문을 재계획한다. 미일치·결정적 추출 실패는 None으로 기존
            # 경로 그대로(칩 자기완결 계약의 안전망).
            from strategy_conversation.primary import run_chip_answer
            parsed = None
            _chip_result = run_chip_answer(
                request.prompt, request.previous_parsed, request.pending_ask,
                previous_explicit_fields=request.previous_explicit_fields,
            )
            # 결속 소비 관찰 — 발행된 pending_ask가 다음 턴에 실제로 답변 귀속에 쓰였나.
            # 발행(primary.ask_binding_gate)과 소비는 다른 요청이라 따로 봐야 한다:
            # 에코가 없으면 프론트 계약(currentParsed 게이트) 문제, 에코가 있는데 미일치면
            # 사용자가 칩을 타이핑으로 바꿔 쓴 것이다(정확 일치 요구의 비용).
            from observability import span as _obs_span

            _echoed = bool(request.pending_ask)
            _attributed = _chip_result is not None
            print(f"[NL-PARSE] 결속 소비 — 에코={'있음' if _echoed else '없음'} "
                  f"귀속={'성립' if _attributed else '불성립'} "
                  f"칩수={len((request.pending_ask or {}).get('chips') or [])}", flush=True)
            with _obs_span("Ask 결속 소비", "state",
                           inputs={"prompt": request.prompt},
                           metadata={"echoed": _echoed,
                                     "attributed": _attributed}) as _t:
                _t.output(echoed=_echoed, attributed=_attributed,
                          topic=(request.pending_ask or {}).get("topic"),
                          chips=(request.pending_ask or {}).get("chips"))
            if _chip_result is not None:
                primary_holder.update(_chip_result)
                parsed = _chip_result["parsed"]
            # "완전 다르게 해줘"류 전면 재작성 요청은 임의 해석 대신 방향을 되묻는다(QA 19-4).
            # [대원칙 1] 재무 팩터 추가 의도인데 기준값이 없는 경우(예: "영업이익률을 추가해
            # 볼까?")를 여기서 원문 정규식(구 clarification_for_add)으로 가로채던 코드는
            # 제거했다 — 그 판정은 사용자 원문 해석이라 LLM 전담이어야 한다. 아래
            # run_primary_modification이 인터프리터로 패치를 뽑은 뒤 validate_intent(→
            # validate_completeness)가 같은 상황(패치 필드에 값 없음)을 이미 구조화 출력
            # 기준으로 감지해 동일한 모양의 되묻기를 낸다(clarification_priority=
            # modify_unapplied, primary_modify_needs_value — 테스트:
            # test_strategy_conversation.py 내 "영업이익률 높고 PER 10 이하" 케이스).
            # 2026-08-02 감사에서 이 가로채기가 "ESS 종목 중에서 거래대금 상위만 넣어줘"
            # 같은 다중 의도 발화의 나머지 부분(테마 전환·랭킹)을 통째로 삼키는 것을 확인
            # (LLM 호출 0회로 응답) — 제거로 항상 인터프리터가 원문 전체를 본다.
            from engine.nl_parser import full_rewrite_clarification
            _clar = None if parsed is not None else full_rewrite_clarification(request.prompt)
            if _clar is not None:
                from engine.nl_parser import ParsedStrategy
                prev_parsed = ParsedStrategy.model_validate(request.previous_parsed)
                result = _build_parse_result(
                    request, backend, prev_parsed, None,
                    load_ms=load_ms,
                    parse_ms=round((time.perf_counter() - parse_started) * 1000, 2),
                    request_started=request_started,
                )
                # 전략은 그대로 유지하고 되묻기 질문+칩만 실어 보낸다(프론트가 칩으로 렌더링).
                result["clarification_question"] = _clar["question"]
                result["clarification_suggestions"] = _clar["suggestions"]
                _nl_parser_status["status"] = "ok"
                _finalize_parse_result(result, request)
                _record_ai_runtime("parse", result["runtime"])
                _store_nl_parse_cache(cache_key, result)
                return result
            # LLM Interpreter Primary Mode (Phase 2): 수정 요청도 인터프리터가 우선 처리
            # (patches 방식). 라운드트립 불가 전략·patches 미출력·검증 미통과는 기존
            # 하이브리드 수정 경로로 폴백한다. 값 없는 팩터 추가는 아래 검증 단계
            # (validate_intent→validate_completeness)가 구조화 출력 기준으로 잡는다.
            from strategy_conversation.primary import (
                primary_enabled as _interp_primary_enabled,
                run_primary_modification,
            )
            if parsed is None and _interp_primary_enabled():
                _primary_mod = run_primary_modification(
                    request.prompt, request.previous_parsed, on_stage=on_stage,
                    previous_explicit_fields=request.previous_explicit_fields,
                    pending_ask=request.pending_ask,
                    pending_question=request.pending_question,
                )
                if _primary_mod is not None:
                    primary_holder.update(_primary_mod)
                    parsed = _primary_mod["parsed"]
            if parsed is None:
                # 2026-07-26 사용자 지시: llm_first에서는 레거시 수정 레인(parse_modification —
                # 결정적 원문 해석 포함)으로 폴백하지 않는다. 인터프리터가 처리하지 못한
                # 수정은 전략 보존+되묻기로 끝낸다(FR-STR-019h 재사용 — "제주반도체 추가"가
                # 레거시 레인에서 유니버스 교체로 처리되던 사고의 재발 방지).
                # 롤백: STRATEGY_MODIFY_INTERPRETER_MODE=fast_path_first(레거시 전체 보존).
                from strategy_conversation.config import modify_interpreter_mode
                if _interp_primary_enabled() and modify_interpreter_mode() == "llm_first":
                    fallback = _interpretation_failure_result(request, backend, request_started)
                    if fallback is not None:
                        _nl_parser_status["status"] = "ok"
                        _record_ai_runtime("parse", fallback["runtime"])
                        return fallback
                parsed = parser.parse_modification(request.prompt, request.previous_parsed, on_stage=on_stage)
            # 코치 맥락 리스크 해석(프론트 inferPendingRiskChange 이관): 코치가 물은 리스크
            # 필드에 사용자의 "10%" 같은 필드 없는 답을 귀속한다. 백엔드가 코치 맥락으로 판단
            # → 프론트는 파스 결과를 재판정하지 않고 그대로 신뢰한다(FR-STR-019e).
            from engine.nl_parser import resolve_coach_context_risk
            _ctx_risk = None if _chip_result is not None else resolve_coach_context_risk(
                request.prompt, request.previous_coach_text, request.previous_parsed
            )
            if _ctx_risk is not None:
                _field, _value = _ctx_risk
                parsed = parsed.model_copy(update={_field: _value})
        else:
            # LLM Interpreter Primary Mode (Phase 2): STRATEGY_INTERPRETER_MODE=primary면
            # 초기 파스를 인터프리터 파이프라인(해석→검증→컴파일)이 담당한다. 실패/비전략
            # intent는 규칙 파서로 재해석하지 않고 실패 보고(되묻기)로 끝낸다 — "폴백은
            # 자연어 재해석이 아니라 실패 보고"(계약 § 8, 1c 폴백 차단, 2026-07-26).
            # 규칙 하이브리드는 primary가 꺼진 환경(off/shadow)의 기본 경로로만 동작한다.
            from strategy_conversation.primary import primary_enabled, run_primary_parse
            if primary_enabled():
                primary = run_primary_parse(
                    request.prompt, on_stage=on_stage,
                    previous_explicit_fields=request.previous_explicit_fields,
                )
                if primary is None:
                    fallback = _interpretation_failure_result(request, backend, request_started)
                    if fallback is not None:
                        _nl_parser_status["status"] = "ok"
                        _record_ai_runtime("parse", fallback["runtime"])
                        return fallback
                    raise HTTPException(
                        status_code=500,
                        detail="전략을 해석하지 못했습니다. 입력을 바꿔 다시 시도해 주세요.",
                    )
                primary_holder.update(primary)
                parsed = primary_holder["parsed"]
            else:
                parsed = parser.parse(
                    request.prompt, on_stage=on_stage, on_validation=_capture_validation,
                    defer_validation=defer_holder is not None,
                )
                # LLM Interpreter Shadow Mode (Phase 1): STRATEGY_INTERPRETER_MODE=shadow일
                # 때만 신규 파이프라인을 백그라운드로 병행 실행해 diff를 JSONL로 남긴다(비차단).
                from strategy_conversation.shadow import maybe_run_shadow
                maybe_run_shadow(request.prompt, parsed.model_dump())
        parse_ms = round((time.perf_counter() - parse_started) * 1000, 2)

        _nl_parser_status["status"] = "ok"
        _nl_parser_status["error"] = None

        validation_report = validation_holder.get("report")
        if (defer_holder is not None and isinstance(validation_report, dict)
                and validation_report.get("pending")):
            # 후행 검증 컨텍스트 — enforce_strategy_minimums가 parsed를 제자리 변형(clamp)
            # 하므로 검증 입력은 변형 전 사본으로 보존한다(인라인 검증과 동일한 입력).
            defer_holder.update({
                "parser": parser,
                "request": request,
                "parsed": parsed.model_copy(deep=True),
                "cache_key": cache_key,
                "backend": backend,
                "extra_notices": [grounding_notice] if grounding_notice else [],
            })

        result = _build_parse_result(
            request, backend, parsed, validation_report,
            load_ms=load_ms, parse_ms=parse_ms, request_started=request_started,
            # 인터프리터 primary가 처리한 턴(초기 파스·수정 모두)은 원문 섹터/테마 스캔을
            # 끈다 — 유니버스 의미는 인터프리터 patches가 담당하며, 원문 스캔이 그 출력을
            # 덮어쓰면 LLM 레인 해석이 소실된다(2026-07-27 사고: "삼성전자 관련 etf 매수"의
            # etf_theme 교체 결과를 apply_theme_universe가 삼성그룹 상장사 10곳으로 교체 —
            # ETF 단독 유니버스에 주식 혼합). 원문 스캔은 인터프리터가 처리하지 못한
            # 레거시 레인(fast_path_first 등)에만 남는다(단계 3 이관 대상).
            scan_prompt_for_sector=not primary_holder,
            # 값 대기 조건은 primary가 이미 산출했다 — 미지원 안내 판정에 함께 넘긴다
            # (되묻는 조건을 "지원되지 않아요"라고 안내하던 모순 방지).
            pending_conditions=primary_holder.get("pending_conditions") if primary_holder else None,
        )
        if primary_holder:
            from strategy_conversation.primary import apply_primary_meta
            apply_primary_meta(result, primary_holder)
        if grounding_notice:
            result["notices"] = [grounding_notice] + list(result.get("notices") or [])
        # provenance 이월 — 인터프리터가 판정하지 않은 턴(폴백·레거시 레인)에서도 이전
        # 턴까지의 명시 필드를 잃지 않는다(프론트 에코 계약의 무상태 누적).
        _finalize_parse_result(result, request)
        _record_ai_runtime("parse", result["runtime"])
        _store_nl_parse_cache(cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[NL-PARSE ERROR]\n{traceback.format_exc()}", flush=True)
        if _is_llm_connection_error(e):
            # LLM 서버 연결 실패 — 모델 미가용으로 표시하고 사용자에겐 친화적 메시지를 준다.
            _nl_parser_status["status"] = "failed"
            _nl_parser_status["error"] = str(e)
            raise HTTPException(
                status_code=503,
                detail="전략 분석 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
            )
        # 해석 실패는 시스템 장애가 아니다 — 요청을 죽이는 대신 기존 clarification 채널로
        # 되묻는다(전역 모델 상태도 건드리지 않는다). 되묻기 구성마저 실패한 경우에만 500.
        fallback = _interpretation_failure_result(request, resolved_backend, request_started)
        if fallback is not None:
            return fallback
        raise HTTPException(
            status_code=500,
            detail="전략을 해석하지 못했습니다. 입력을 바꿔 다시 시도해 주세요.",
        )


# 후행(비차단) LLM 검증이 SSE 스트림을 붙잡을 수 있는 최대 시간. 프록시의 스트림 예산
# (120s) 아래로 유지해 검증이 매달려도 스트림이 프록시 타임아웃으로 끊기지 않게 한다.
_DEFERRED_VALIDATION_MAX_WAIT_S = 90.0


@app.post("/strategy/parse-stream")
async def parse_nl_strategy_stream(request: NLParseRequest):
    """NL 파싱 진행 상황을 SSE로 스트리밍 — parsing(규칙 기반)→thinking(LLM 폴백) 단계 표시.

    파싱은 동기 함수라 별도 스레드에서 돌리고, on_stage 콜백이 단계 전환을 기록한다.
    제너레이터가 단계 변화를 폴링해 SSE로 흘려보내고, 완료 시 결과/에러를 전송한다.
    룰 파스가 LLM 검증 대상이면 결과를 먼저 보내고 검증은 후행(result_update)으로 처리한다.
    """
    from fastapi.responses import StreamingResponse
    import threading, json

    result_holder: dict = {}
    error_holder: dict = {}
    stage_holder: dict = {"stage": "parsing"}
    # 비차단 검증: 룰 파스의 LLM 검증을 인라인으로 기다리지 않고(수 초~수십 초),
    # 결과(result)를 먼저 내보낸 뒤 후행 검증을 돌려 교정이 있으면 result_update로
    # 후속 전송한다. 검증 필요 컨텍스트는 _run_nl_parse가 이 holder에 채운다.
    defer_holder: dict = {}

    def on_stage(stage: str):
        stage_holder["stage"] = stage

    def run_parse():
        try:
            result_holder["data"] = _run_nl_parse(request, on_stage=on_stage, defer_holder=defer_holder)
        except HTTPException as exc:
            error_holder["detail"] = exc.detail
        except Exception as exc:
            error_holder["detail"] = str(exc)

    thread = threading.Thread(target=run_parse, daemon=True)

    async def generate():
        def stage_event(stage: str) -> str:
            return f"data: {json.dumps({'type': 'stage', 'stage': stage})}\n\n"

        thread.start()
        emitted_stage = "parsing"
        yield stage_event(emitted_stage)

        while thread.is_alive():
            if stage_holder["stage"] != emitted_stage:
                emitted_stage = stage_holder["stage"]
                yield stage_event(emitted_stage)
            await asyncio.sleep(0.1)
        thread.join()

        # 스레드 종료 직전 전환된 단계를 놓치지 않도록 마지막으로 확인
        if stage_holder["stage"] != emitted_stage:
            yield stage_event(stage_holder["stage"])

        if "detail" in error_holder:
            yield f"data: {json.dumps({'type': 'error', 'detail': error_holder['detail']}, ensure_ascii=False)}\n\n"
        elif "data" in result_holder:
            yield f"data: {json.dumps({'type': 'result', 'data': result_holder['data']}, ensure_ascii=False)}\n\n"
            # 후행 검증. 'validating' stage 이벤트는 보내지 않는다 — 프론트가 로딩 버블로
            # 되돌아가 방금 표시한 전략 요약이 사라진다. 교정 없으면 조용히 종료.
            if defer_holder.get("parsed") is not None:
                update_holder: dict = {}

                def run_validation():
                    from observability import use_parent

                    # 응답 후 단계지만 같은 사용자 요청의 일부다 — 부모를 복원해 같은
                    # Trace에 붙인다(contextvar는 스레드를 건너지 않는다).
                    with use_parent(defer_holder.get("trace_parent")):
                        try:
                            update_holder["data"] = _complete_deferred_validation(defer_holder)
                        except Exception as exc:  # noqa: BLE001 — 검증은 best-effort
                            print(f"[NL-PARSE] 후행 검증 실패(무시): {exc}", flush=True)

                vthread = threading.Thread(target=run_validation, daemon=True)
                vthread.start()
                waited = 0.0
                # 프록시 스트림 예산(120s) 안에서 종료하도록 상한을 둔다. 초과 시 join 없이
                # 스트림만 닫는다(검증 스레드는 daemon으로 자연 소멸, 결과는 폐기).
                while vthread.is_alive() and waited < _DEFERRED_VALIDATION_MAX_WAIT_S:
                    await asyncio.sleep(0.1)
                    waited += 0.1
                if update_holder.get("data") is not None:
                    yield f"data: {json.dumps({'type': 'result_update', 'data': update_holder['data']}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
            start_time = time.time()
            req_dict = request.model_dump()
            sym_count = len(req_dict.get("symbols", []))
            print(f"[BT-STREAM] 엔진 시작: {sym_count}종목", flush=True)
            result = engine.run_backtest(req_dict)
            elapsed = time.time() - start_time
            result["executionTime"] = elapsed
            result_holder["data"] = result
            print(f"[BT-STREAM] 엔진 완료: {elapsed:.2f}s ({sym_count}종목, {result.get('trades',0)}거래)", flush=True)
        except Exception as exc:
            print(f"[BT-STREAM] 엔진 에러: {exc}", flush=True)
            error_holder["error"] = str(exc)

    thread = threading.Thread(target=run_bt, daemon=True)

    async def generate():
        period = request.period or "5y"
        period_years = {"1y": 1, "3y": 3, "5y": 5, "full": 10}.get(period, 5)

        def emit(msg: str) -> str:
            return f"data: {json.dumps({'type': 'status', 'message': msg})}\n\n"

        # 백테스트 스레드 시작
        thread.start()

        # ── Step 1: 종목 데이터 로딩
        # 종목 수는 표기하지 않는다 — request.symbols는 '현재 상장' 종목 수라 실제 백테스트
        # 유니버스(시점별 상장분 + 상장폐지분)와 달라 오해를 준다(아래 시뮬레이션 문구 참고).
        yield emit("종목 데이터 로딩 중...")

        # ── Step 2: 재무 필터 정보
        filter_descs = []
        for c in request.entry.conditions:
            if c.type == "filter":
                op = c.params.get("operator", "")
                val = c.params.get("value", "")
                filter_descs.append(f"{c.id.upper()} {op} {val}")
        if filter_descs:
            yield emit(f"재무 필터 적용 중... ({', '.join(filter_descs[:4])})")

        # ── Step 3: 실제 백테스트 완료 대기 (0.2초 단위 폴링, 인위적 지연 없음)
        phases = [
            simulation_phase_label(period_years),
            "거래 내역 집계 중...",
            "성과 지표 계산 중...",
        ]
        # 워치독: 엔진 스레드가 행에 빠지면 이 폴링 루프가 무한 상태 메시지를 내보낸다.
        # 벽시계 제한 시간을 넘기면 에러 이벤트를 보내고 스트림을 끝낸다(데몬 스레드는 유기).
        deadline = time.monotonic() + backtest_timeout_s()
        wait_count = 0
        while thread.is_alive():
            if time.monotonic() >= deadline:
                print(f"[BT-STREAM][WATCHDOG] 백테스트가 {backtest_timeout_s():.0f}s를 초과 — 스트림 종료", flush=True)
                yield f"data: {json.dumps({'type': 'error', 'message': backtest_timeout_message(backtest_timeout_s())})}\n\n"
                yield "data: [DONE]\n\n"
                return
            status_message = build_backtest_stream_status(wait_count, phases)
            if status_message:
                yield emit(status_message)
            await asyncio.sleep(0.2)
            wait_count += 1

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


# ─── AI 요약 ────────────────────────────────────────────────────────────────

class SummarizeRequest(BaseModel):
    metrics: dict
    strategySummary: Optional[dict] = None
    parsed_strategy: Optional[dict] = None
    user_prompt: Optional[str] = None


def _run_advisor_for_report(parsed_strategy: dict, user_prompt: Optional[str], metrics: dict) -> Optional[dict]:
    """백테스트 리포트용 advisor 진단을 실행한다(동기). 실패 시 None 을 반환해 LLM 단독 경로로 폴백한다."""
    try:
        from api.advisor_routes import _agent as _advisor_agent
        from advisor.news_enrichment import build_news_context_from_strategy
        from advisor.memory_repository import load_advisor_memory
        from advisor.schemas import AdvisorRequest, BacktestSummary
        from ai.summarize import to_advisor_backtest_summary

        req = AdvisorRequest(
            user_prompt=user_prompt or "",
            parsed_strategy=parsed_strategy,
            backtest_result=BacktestSummary(**to_advisor_backtest_summary(metrics)),
        )
        news_context = build_news_context_from_strategy(parsed_strategy)
        if news_context:
            req = req.model_copy(update={"news_context": news_context})
        strategy_cases, experiences = load_advisor_memory()
        if strategy_cases or experiences:
            req = req.model_copy(update={
                "memory_strategy_cases": strategy_cases,
                "memory_experiences": experiences,
            })
        return _advisor_agent.review(req).model_dump()
    except Exception as e:
        print(f"[summarize] advisor review skipped: {repr(e)}", flush=True)
        return None

# 모델 싱글턴 (최초 1회 로드, 이후 재사용)
_summarize_model = {"model": None, "tokenizer": None}

@app.post("/summarize")
def summarize_backtest(req: SummarizeRequest):
    """백테스트 결과를 Ollama 기반 AI로 요약한다."""
    from ai.summarize import (
        FALLBACK_SUMMARY,
        calculate_score,
        build_report_from_advisor,
        build_expert_report_prompt,
        parse_expert_report,
        normalize_report_items,
        summarize_ollama,
    )
    from ai.report_evidence import (
        build_evidence_pack,
        classify_strategy_profile,
        build_validation_roadmap,
        build_improvement_priorities,
    )

    request_started = time.perf_counter()
    score = calculate_score(req.metrics)

    # 하이브리드: advisor·evidence·corpus 가 결정론적으로 등급/근거/로드맵/개선안을
    # 만들고, LLM 은 그 위에서 서술 섹션만 작성한다(전략 검증 전문가 리포트).
    payload = {"metrics": req.metrics, "strategySummary": req.strategySummary}
    advisor_resp = None
    advisor_report = None
    if req.parsed_strategy:
        advisor_resp = _run_advisor_for_report(req.parsed_strategy, req.user_prompt, req.metrics)
        if advisor_resp is not None:
            advisor_report = build_report_from_advisor(advisor_resp)

    # 코퍼스 비교(결정론) — 리포트가 '결과 읽기'에 그치지 않고 동일 엔진 시뮬레이션
    # 분포 대비 상대적 위치·구조 장치 유무별 과거 통계를 서술할 근거를 만든다.
    corpus_comparison = None
    try:
        from advisor.corpus_insights import build_corpus_comparison
        corpus_comparison = build_corpus_comparison(req.parsed_strategy, req.metrics)
    except Exception as e:
        print(f"[summarize] corpus comparison skipped: {repr(e)}", flush=True)

    # 결정론 근거·구조 섹션 — LLM 없이 사실만으로 도출한다.
    evidence = build_evidence_pack(req.metrics, req.parsed_strategy)
    profile_tags = classify_strategy_profile(req.parsed_strategy, req.metrics)
    validation_roadmap = build_validation_roadmap(req.metrics, evidence, advisor_resp)
    improvement_priorities = build_improvement_priorities(score, advisor_report, evidence)

    prompt = build_expert_report_prompt(
        payload,
        evidence=evidence,
        advisor_report=advisor_report,
        corpus_comparison=corpus_comparison,
        profile_tags=profile_tags,
    )

    try:
        raw = summarize_ollama(prompt, num_predict=2600)
        parsed = parse_expert_report(raw)
        runtime = {
            "backend": "ollama",
            "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
        }
        _record_ai_runtime("summary", runtime)

        if parsed is None:
            # LLM 출력 파싱 실패 — 프록시/프론트가 캐시·저장하지 않고 재시도를 유도하게 한다.
            return {
                "score": score,
                "summary": FALLBACK_SUMMARY,
                "strengths": ["없음"],
                "weaknesses": ["없음"],
                "improvements": ["없음"],
                "degraded": True,
                "runtime": runtime,
            }

        result = {
            "score": score,
            # summary 는 executive_summary 로 매핑(하위호환 — 기존 프론트/캐시 키 유지).
            "summary": parsed["executive_summary"],
            "executiveSummary": parsed["executive_summary"],
            "topInsights": normalize_report_items(parsed["top_insights"]),
            "strengths": normalize_report_items(parsed["strengths"]),
            "weaknesses": normalize_report_items(parsed["weaknesses"]),
            "hiddenRisks": normalize_report_items(parsed["hidden_risks"]),
            "overfittingAnalysis": parsed["overfitting_analysis"],
            "strategyProfile": profile_tags,
            "strategyProfileNote": parsed["strategy_profile_note"],
            "validationRoadmap": validation_roadmap,
            # improvements 는 결정론(점수 인지형·검증 중심)으로 채운다(LLM DSL 환각 방지).
            "improvements": normalize_report_items(improvement_priorities),
            "finalVerdict": parsed["final_verdict"],
            "runtime": runtime,
        }
        if corpus_comparison is not None:
            result["corpusComparison"] = corpus_comparison
        if advisor_report is not None:
            result["advisorScore"] = advisor_report["advisorScore"]
            result["riskScore"] = advisor_report["riskScore"]
            result["overfitRisk"] = advisor_report["overfitRisk"]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarize error: {repr(e)}")


# ─── 데이터 동기화 이벤트 로깅 ──────────────────────────────────────────────

class SyncEventRequest(BaseModel):
    event: str  # "start" | "end"
    date: Optional[str] = None
    total: Optional[int] = None
    kospi: Optional[int] = None
    kosdaq: Optional[int] = None
    success: Optional[int] = None
    fail: Optional[int] = None
    new_symbols: Optional[int] = None
    added_symbols: Optional[List[dict]] = None
    delisted_symbols: Optional[List[dict]] = None
    message: Optional[str] = None


@app.post("/internal/sync/event")
def sync_event(req: SyncEventRequest):
    """scripts/sync_data.py 에서 동기화 시작/종료를 알린다."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if req.event == "start":
        print(f"[{ts}] [SYNC] 데이터 동기화 시작", flush=True)
    elif req.event == "end":
        parts = []
        if req.date is not None:
            parts.append(f"일자={req.date}")
        if req.total is not None:
            parts.append(f"전체={req.total}")
        if req.kospi is not None:
            parts.append(f"KOSPI={req.kospi}")
        if req.kosdaq is not None:
            parts.append(f"KOSDAQ={req.kosdaq}")
        if req.new_symbols is not None:
            parts.append(f"신규={req.new_symbols}")
        if req.delisted_symbols is not None:
            parts.append(f"상폐={len(req.delisted_symbols)}")
        if req.success is not None:
            parts.append(f"성공={req.success}")
        if req.fail is not None:
            parts.append(f"실패={req.fail}")
        summary = ", ".join(parts)
        print(f"[{ts}] [SYNC] 데이터 동기화 완료 — {summary}", flush=True)
    else:
        print(f"[{ts}] [SYNC] {req.message or req.event}", flush=True)
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
