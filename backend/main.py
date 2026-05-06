from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from schemas import (
    BacktestRequest, BacktestResponse,
    OptimizationRequest, OptimizationResponse,
    WalkForwardRequest, WalkForwardResponse,
)
from backtest_engine import BacktestEngine
from engine.market_data import market_data_provider
from engine.live_signal_utils import prepare_signal_dataframe
from engine.virtual_trader import VirtualTrader
from engine.vi_utils import build_vi_display
from nl_cache import nl_cache_key
from stream_progress import build_backtest_stream_status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
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

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(_app):
    # 백엔드 시작 시 LLM 모델을 백그라운드 스레드에서 미리 로드
    def _preload():
        try:
            from news import llm_extractor
            llm_extractor._load()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("LLM preload failed: %s", e)

    thread = threading.Thread(target=_preload, daemon=True, name="llm-preload")
    thread.start()
    yield

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
_ = engine.ai_engine  # 서버 시작 시 AI 모델 사전 로드

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
    public_company_info = (
        _get_cached_public_company_info(symbol, company_name)
        if include_public_info else None
    )
    listing_info = (
        (public_company_info or {}).get("listing")
        or (_get_cached_listing_info(symbol) if include_listing else None)
    )
    company_basic = (public_company_info or {}).get("companyBasic") or {}
    summary_financials = (public_company_info or {}).get("summaryFinancials") or {}

    detail = None
    if app_key and app_secret and token:
        detail = _fetch_kis_stock_detail(symbol, app_key, app_secret, token)

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
        resp = requests.get(
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
            resp = requests.get(
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
    listing = _fetch_listing_info_from_public_api(symbol)
    crno = (listing or {}).get("crno")

    resolved_company_name = (
        _first_nonempty_from_dicts(listing, keys=("stockIssueCompanyName", "name"))
        or company_name
    )
    company_basic = _fetch_company_basic_from_public_api(crno, resolved_company_name)
    if not crno:
        crno = (company_basic or {}).get("crno")
    summary_financials = _fetch_summary_financials_from_public_api(crno) if crno else None

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


def _fetch_kis_stock_detail(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[dict]:
    try:
        resp = requests.get(
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
        debt_ratio = _fetch_kis_debt_ratio(symbol, app_key, app_secret, token)
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
        resp = requests.get(
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
_TRADE_STRENGTH_CACHE_TTL = 1.0


def _get_cached_vi_display(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[dict]:
    cached = _vi_cache.get(symbol)
    if cached and cached[1] > time.time():
        return cached[0]
    value = _fetch_kis_vi_display(symbol, app_key, app_secret, token)
    _vi_cache[symbol] = (value, time.time() + _VI_CACHE_TTL)
    return value


def _fetch_kis_trade_strength(symbol: str, app_key: str, app_secret: str, token: str) -> Optional[float]:
    try:
        resp = requests.get(
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


async def _resolve_kis_orderbook_context(symbol: str) -> tuple[Optional[object], str, str, Optional[str]]:
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


async def _build_orderbook_payload(symbol: str) -> dict:
    if market_data_provider.ws_provider.is_configured():
        await market_data_provider.subscribe([symbol])

    quote, app_key, app_secret, token = await _resolve_kis_orderbook_context(symbol)

    if app_key and app_secret and token:
        vi_display = _get_cached_vi_display(symbol, app_key, app_secret, token)
        trade_strength = _get_cached_trade_strength(symbol, app_key, app_secret, token)
        ws_orderbook = await market_data_provider.ws_provider.get_orderbook(symbol)
        if ws_orderbook:
            return {
                **ws_orderbook,
                "symbol": symbol,
                "currentPrice": quote.close,
                "vi": vi_display,
                "tradeStrength": trade_strength,
                "source": "kis_ws_total_orderbook",
            }

        try:
            resp = requests.get(
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
            if resp.status_code == 200:
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

                if sell_orders or buy_orders:
                    return {
                        "symbol": symbol,
                        "currentPrice": quote.close,
                        "sellOrders": sell_orders,
                        "buyOrders": buy_orders,
                        "totalAskQty": int(float(output.get("total_askp_rsqn", 0) or 0)),
                        "totalBidQty": int(float(output.get("total_bidp_rsqn", 0) or 0)),
                        "vi": vi_display,
                        "recentTrades": ws_orderbook.get("recentTrades", []) if ws_orderbook else [],
                        "tradeStrength": trade_strength,
                        "source": "kis_total_orderbook_rest",
                        "timestamp": time.time(),
                    }
        except Exception:
            pass

    raise HTTPException(status_code=503, detail="실제 호가 데이터를 아직 받지 못했습니다")


@app.get("/market/investor-trading/{symbol}")
async def market_investor_trading(symbol: str):
    """투자자별 일별 매매동향 (개인/외국인/기관).

    KIS API 우선 (최대 30일, 매수/매도 수량 포함),
    실패 시 Naver dealTrendInfos 폴백 (최근 5영업일).
    """
    # --- KIS 우선 ---
    kis = next(
        (p for p in market_data_provider.providers if p.name == "kis"),
        None,
    )
    if kis:
        kis_rows = await kis.get_investor_trading(symbol)
        if kis_rows:
            return {"symbol": symbol, "data": kis_rows, "source": "kis"}

    # --- Naver 폴백 ---
    def _fetch_naver(symbol: str) -> list[dict]:
        import requests as _req

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = _req.get(
            f"https://m.stock.naver.com/api/stock/{symbol}/integration",
            headers=headers,
            timeout=6,
        )
        if resp.status_code != 200:
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

    rows = await asyncio.to_thread(_fetch_naver, symbol)
    if not rows:
        raise HTTPException(status_code=503, detail="투자자 매매동향 데이터를 가져올 수 없습니다")

    return {"symbol": symbol, "data": rows, "source": "naver"}


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
    backend: str = "mlx"  # "mlx" | "ollama"
    model: Optional[str] = None  # None = 기본값 사용
    previous_parsed: Optional[dict] = None  # 수정 모드: 이전 파싱 결과

class NLParseResponse(BaseModel):
    parsed: dict
    backtest_request: dict
    symbol_count: int
    clarification_question: Optional[str] = None
    clarification_suggestions: Optional[List[str]] = None
    runtime: Optional[dict] = None

_nl_parsers: dict = {}  # backend → NLStrategyParser (lazy singleton)
_nl_parser_status: dict = {"status": "loading", "error": None}  # "ok" | "failed" | "loading"


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
                lock.acquire(priority)
                return self

            def __exit__(self, *_args):
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

        from api.coach_routes import set_parser as _set_coach_parser
        _set_coach_parser(parser)

        print(
            f"[startup] NL 파서 모델 로딩 완료: {parser._model_log_label(parser.model_7b)}",
            flush=True,
        )
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
            print(
                f"[startup] Summarize 모델이 NL 파서 모델을 공유합니다: {shared_parser._model_log_label(shared_parser.model_7b)}",
                flush=True,
            )
            return

    from ai.summarize import MLX_MODEL
    from mlx_lm import load  # type: ignore

    model_label = shared_parser._model_log_label(MLX_MODEL) if shared_parser is not None else MLX_MODEL.split("/")[-1].replace("-OptiQ-4bit", "")
    print(f"[startup] Summarize 모델 최초 로드 중: {model_label}", flush=True)
    m, t = load(MLX_MODEL)
    _summarize_model["model"] = m
    _summarize_model["tokenizer"] = t
    print(f"[startup] Summarize 모델 로드 완료: {model_label}", flush=True)


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


@app.post("/strategy/parse", response_model=NLParseResponse)
def parse_nl_strategy(request: NLParseRequest):
    """자연어 전략 설명을 ParsedStrategy + BacktestRequest로 변환"""
    request_started = time.perf_counter()
    print(f"\n[NL-PARSE] prompt='{request.prompt}', backend={request.backend}", flush=True)

    # 캐시 조회 — 동일 프롬프트면 LLM 재호출 없이 즉시 반환
    cache_key = nl_cache_key(request.prompt, request.backend, request.model, request.previous_parsed)
    if cache_key in _nl_parse_cache:
        print(f"[NL-PARSE] 캐시 히트 → 즉시 반환", flush=True)
        cached = dict(_nl_parse_cache[cache_key])
        runtime = {
            "cache_hit": True,
            "backend": request.backend,
            "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
        }
        cached["runtime"] = runtime
        _record_ai_runtime("parse", runtime)
        return cached

    try:
        from engine.nl_parser import NLStrategyParser
        from engine.strategy_converter import to_backtest_request

        load_started = time.perf_counter()
        backend = request.backend
        if backend not in _nl_parsers:
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
        load_ms = round((time.perf_counter() - load_started) * 1000, 2)
        parse_started = time.perf_counter()
        if backend == "mlx":
            with _mlx_inference_lock.priority(0):
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
        parse_ms = round((time.perf_counter() - parse_started) * 1000, 2)

        _nl_parser_status["status"] = "ok"
        _nl_parser_status["error"] = None
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
        result = {
            "parsed": parsed.model_dump(),
            "backtest_request": backtest_req,
            "symbol_count": len(backtest_req["symbols"]),
            "clarification_question": None,
            "clarification_suggestions": None,
            "runtime": runtime,
        }
        _record_ai_runtime("parse", runtime)

        # 캐시 저장 (최대 크기 초과 시 가장 오래된 항목 제거)
        if len(_nl_parse_cache) >= _NL_PARSE_CACHE_MAX:
            oldest_key = next(iter(_nl_parse_cache))
            del _nl_parse_cache[oldest_key]
        _nl_parse_cache[cache_key] = result

        return result
    except Exception as e:
        _nl_parser_status["status"] = "failed"
        _nl_parser_status["error"] = str(e)
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
        wait_count = 0
        while thread.is_alive():
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

# 모델 싱글턴 (최초 1회 로드, 이후 재사용)
_summarize_model = {"model": None, "tokenizer": None}

@app.post("/summarize")
def summarize_backtest(req: SummarizeRequest):
    """백테스트 결과를 AI로 요약. 모델을 프로세스 내에서 재사용 → 로드 시간 제거."""
    from ai.summarize import calculate_score, build_prompt, parse_llm_output, normalize_report_items
    import platform

    request_started = time.perf_counter()
    score = calculate_score(req.metrics)
    prompt = build_prompt({"metrics": req.metrics, "strategySummary": req.strategySummary})

    try:
        is_mac = platform.system() == "Darwin"
        if is_mac:
            import os
            from mlx_lm import generate  # type: ignore
            os.environ["HF_HUB_OFFLINE"] = "1"

            with _mlx_inference_lock.priority(2):
                _ensure_summarize_model_loaded()

                tokenizer = _summarize_model["tokenizer"]
                if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
                    formatted = tokenizer.apply_chat_template(
                        [{"role": "user", "content": prompt}],
                        tokenize=False,
                        add_generation_prompt=True,
                        enable_thinking=False,
                    )
                else:
                    formatted = prompt

                raw = generate(
                    _summarize_model["model"], tokenizer, prompt=formatted, max_tokens=1200, verbose=False
                ).strip()
        else:
            from ai.summarize import summarize_ollama
            raw = summarize_ollama(prompt)

        parsed = parse_llm_output(raw)
        runtime = {
            "backend": "mlx" if is_mac else "ollama",
            "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
        }
        _record_ai_runtime("summary", runtime)
        return {
            "score": score,
            "summary": parsed.get("total_summary", ""),
            "strengths": normalize_report_items(parsed.get("strengths", [])),
            "weaknesses": normalize_report_items(parsed.get("weaknesses", [])),
            "improvements": normalize_report_items(parsed.get("improvements", [])),
            "runtime": runtime,
        }
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
