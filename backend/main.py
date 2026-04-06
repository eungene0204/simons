from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from schemas import (
    BacktestRequest, BacktestResponse,
    MonteCarloRequest, MonteCarloResponse,
    OptimizationRequest, OptimizationResponse,
    WalkForwardRequest, WalkForwardResponse,
)
from backtest_engine import BacktestEngine
from engine.market_data import market_data_provider
from engine.virtual_trader import VirtualTrader
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import uvicorn
import time
import asyncio
import threading
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
_ = engine.ai_engine  # 서버 시작 시 AI 모델 사전 로드

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
            df_slice = df.tail(history_days + 15)

            if len(df_slice) == 0:
                results.append({"symbol": symbol, "error": "데이터 없음"})
                continue

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
    previous_parsed: Optional[dict] = None  # 수정 모드: 이전 파싱 결과

class NLParseResponse(BaseModel):
    parsed: dict
    backtest_request: dict
    symbol_count: int
    clarification_question: Optional[str] = None
    clarification_suggestions: Optional[List[str]] = None

_nl_parsers: dict = {}  # backend → NLStrategyParser (lazy singleton)
_nl_parser_status: dict = {"status": "loading", "error": None}  # "ok" | "failed" | "loading"
_mlx_inference_lock = threading.Lock()

# NL parse 결과 캐시: 동일 프롬프트 재파싱 방지 (LLM inference 14s → 0s)
import hashlib as _hashlib
import json as _json

_nl_parse_cache: dict = {}   # cache_key → NLParseResponse dict
_NL_PARSE_CACHE_MAX = 200    # 최대 200개 항목 유지


def _nl_cache_key(prompt: str, backend: str, model: str | None, previous_parsed: dict | None) -> str:
    payload = {
        "prompt": prompt.strip(),
        "backend": backend,
        "model": model or "",
        "previous_parsed": previous_parsed or {},
    }
    return _hashlib.sha256(_json.dumps(payload, sort_keys=True).encode()).hexdigest()


_virtual_trader = VirtualTrader(market_data_provider, engine.loader)


@app.on_event("startup")
async def startup():
    """서버 시작 시 KIS WebSocket + VirtualTrader 백그라운드 루프 시작"""
    await market_data_provider.start_ws()
    await _virtual_trader.start()


@app.on_event("shutdown")
async def shutdown():
    """서버 종료 시 백그라운드 루프 정리"""
    await market_data_provider.stop_ws()
    await _virtual_trader.stop()


@app.on_event("startup")
def preload_nl_parser():
    """서버 시작 시 NL 파서 모델을 미리 로드 (첫 요청 지연 방지)"""
    try:
        from engine.nl_parser import NLStrategyParser
        parser = NLStrategyParser(backend="mlx")
        parser._init_mlx()  # 모델 로딩 (최초 1회)
        _nl_parsers["mlx"] = parser
        _summarize_model["model"] = parser._mlx_model_7b
        _summarize_model["tokenizer"] = parser._tokenizer_7b
        _nl_parser_status["status"] = "ok"
        _nl_parser_status["error"] = None
        print("[startup] NL 파서 7B 모델 로딩 완료 (32B는 첫 수정 요청 시 lazy 로드)", flush=True)
    except Exception as e:
        _nl_parser_status["status"] = "failed"
        _nl_parser_status["error"] = str(e)
        print(f"[startup] NL 파서 로딩 실패 (무시됨): {e}", flush=True)


def _ensure_summarize_model_loaded():
    """요약용 Qwen MLX 모델을 프로세스 시작 시 1회 로드한다."""
    import platform

    if platform.system() != "Darwin":
        return

    if _summarize_model["model"] is not None:
        return

    shared_parser = _nl_parsers.get("mlx")
    if shared_parser is not None:
        shared_parser._init_mlx()
        if shared_parser._mlx_model_7b is not None and shared_parser._tokenizer_7b is not None:
            _summarize_model["model"] = shared_parser._mlx_model_7b
            _summarize_model["tokenizer"] = shared_parser._tokenizer_7b
            print("[startup] Summarize Qwen 7B 모델이 NL 파서 모델을 공유합니다", flush=True)
            return

    from mlx_lm import load  # type: ignore

    print("[startup] Summarize Qwen 7B 모델 최초 로드 중...", flush=True)
    m, t = load("mlx-community/Qwen2.5-7B-Instruct-4bit")
    _summarize_model["model"] = m
    _summarize_model["tokenizer"] = t
    print("[startup] Summarize Qwen 7B 모델 로드 완료", flush=True)


@app.on_event("startup")
def preload_summarize_model():
    """서버 시작 시 AI 요약용 Qwen 모델도 미리 로드한다."""
    try:
        with _mlx_inference_lock:
            _ensure_summarize_model_loaded()
    except Exception as e:
        print(f"[startup] Summarize 모델 로딩 실패 (무시됨): {e}", flush=True)


@app.get("/model/status")
def get_model_status():
    """NL 파서 모델 로딩 상태 반환"""
    return _nl_parser_status


@app.post("/strategy/parse", response_model=NLParseResponse)
def parse_nl_strategy(request: NLParseRequest):
    """자연어 전략 설명을 ParsedStrategy + BacktestRequest로 변환"""
    print(f"\n[NL-PARSE] prompt='{request.prompt}', backend={request.backend}", flush=True)

    # 캐시 조회 — 동일 프롬프트면 LLM 재호출 없이 즉시 반환
    cache_key = _nl_cache_key(request.prompt, request.backend, request.model, request.previous_parsed)
    if cache_key in _nl_parse_cache:
        print(f"[NL-PARSE] 캐시 히트 → 즉시 반환", flush=True)
        return _nl_parse_cache[cache_key]

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
        if backend == "mlx":
            with _mlx_inference_lock:
                if request.previous_parsed:
                    print(f"[NL-PARSE] 수정 모드 (diff)", flush=True)
                    parsed = parser.parse_modification(request.prompt, request.previous_parsed)
                else:
                    parsed = parser.parse(request.prompt)
        else:
            if request.previous_parsed:
                print(f"[NL-PARSE] 수정 모드 (diff)", flush=True)
                parsed = parser.parse_modification(request.prompt, request.previous_parsed)
            else:
                parsed = parser.parse(request.prompt)
        backtest_req = to_backtest_request(parsed)

        from engine.nl_parser import validate_parsed_strategy
        clarification_question, clarification_suggestions = validate_parsed_strategy(parsed, request.prompt)

        print(f"[NL-PARSE] filters={len(parsed.fundamental_filters)}, entry={len(parsed.entry_signals)}, symbols={len(backtest_req['symbols'])}, clarification={'yes' if clarification_question else 'no'}", flush=True)

        result = {
            "parsed": parsed.model_dump(),
            "backtest_request": backtest_req,
            "symbol_count": len(backtest_req["symbols"]),
            "clarification_question": clarification_question,
            "clarification_suggestions": clarification_suggestions,
        }

        # 캐시 저장 (최대 크기 초과 시 가장 오래된 항목 제거)
        if len(_nl_parse_cache) >= _NL_PARSE_CACHE_MAX:
            oldest_key = next(iter(_nl_parse_cache))
            del _nl_parse_cache[oldest_key]
        _nl_parse_cache[cache_key] = result

        return result
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
        symbol_count = len(request.symbols)
        period = request.period or "5y"
        period_years = {"1y": 1, "3y": 3, "5y": 5, "full": 10}.get(period, 5)

        def emit(msg: str) -> str:
            return f"data: {json.dumps({'type': 'status', 'message': msg})}\n\n"

        # 백테스트 스레드 시작
        thread.start()

        # ── Step 1: 종목 데이터 로딩
        yield emit(f"{symbol_count:,}개 종목 데이터 로딩 중...")

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
            f"시뮬레이션 실행 중... ({symbol_count:,}종목 × {period_years}년)",
            "거래 내역 집계 중...",
            "성과 지표 계산 중...",
        ]
        phase_idx = 0
        wait_count = 0
        while thread.is_alive():
            if wait_count % 10 == 0 and phase_idx < len(phases):
                yield emit(phases[phase_idx])
                phase_idx += 1
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

# 모델 싱글턴 (최초 1회 로드, 이후 재사용)
_summarize_model = {"model": None, "tokenizer": None}

@app.post("/summarize")
def summarize_backtest(req: SummarizeRequest):
    """백테스트 결과를 AI로 요약. 모델을 프로세스 내에서 재사용 → 로드 시간 제거."""
    from ai.summarize import calculate_score, build_prompt, parse_llm_output, normalize_report_items
    import platform

    score = calculate_score(req.metrics)
    prompt = build_prompt({"metrics": req.metrics, "strategySummary": req.strategySummary})

    try:
        is_mac = platform.system() == "Darwin"
        if is_mac:
            import os
            from mlx_lm import generate  # type: ignore
            os.environ["HF_HUB_OFFLINE"] = "1"

            with _mlx_inference_lock:
                _ensure_summarize_model_loaded()

                tokenizer = _summarize_model["tokenizer"]
                if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
                    formatted = tokenizer.apply_chat_template(
                        [{"role": "user", "content": prompt}],
                        tokenize=False, add_generation_prompt=True,
                    )
                else:
                    formatted = prompt

                raw = generate(
                    _summarize_model["model"], tokenizer, prompt=formatted, max_tokens=600, verbose=False
                ).strip()
        else:
            from ai.summarize import summarize_ollama
            raw = summarize_ollama(prompt)

        parsed = parse_llm_output(raw)
        return {
            "score": score,
            "summary": parsed.get("total_summary", ""),
            "strengths": normalize_report_items(parsed.get("strengths", [])),
            "risks": normalize_report_items(parsed.get("risks", [])),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarize error: {repr(e)}")


# ─── 데이터 동기화 이벤트 로깅 ──────────────────────────────────────────────

class SyncEventRequest(BaseModel):
    event: str  # "start" | "end"
    total: Optional[int] = None
    success: Optional[int] = None
    fail: Optional[int] = None
    new_symbols: Optional[int] = None
    message: Optional[str] = None


@app.post("/internal/sync/event")
def sync_event(req: SyncEventRequest):
    """scripts/sync_data.py 에서 동기화 시작/종료를 알린다."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if req.event == "start":
        print(f"[{ts}] [SYNC] 데이터 동기화 시작", flush=True)
    elif req.event == "end":
        parts = []
        if req.total is not None:
            parts.append(f"전체={req.total}")
        if req.new_symbols is not None:
            parts.append(f"신규={req.new_symbols}")
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
