"""
yfinance 한국 주식 Provider
- KOSPI 종목: .KS 접미사, KOSDAQ 종목: .KQ 접미사
- ~15분 지연이지만 안정적, API Key 불필요
- data/korea-stocks.json에서 시장 구분 로드
"""

import asyncio
import json
import os
import time
from typing import Optional
from datetime import datetime

from .base import BaseProvider, StockQuote

# 프로젝트 루트 기준 korea-stocks.json 경로
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STOCKS_JSON_PATH = os.path.join(_PROJECT_ROOT, "data", "korea-stocks.json")


def _load_market_map() -> dict[str, str]:
    """korea-stocks.json에서 symbol → market 매핑 로드"""
    try:
        with open(_STOCKS_JSON_PATH, "r", encoding="utf-8") as f:
            stocks = json.load(f)
        return {s["symbol"]: s.get("market", "KOSPI") for s in stocks}
    except Exception:
        return {}


def _get_yf_ticker(symbol: str, market_map: dict[str, str]) -> str:
    """종목코드 → yfinance 티커 변환 (예: 005930 → 005930.KS)"""
    market = market_map.get(symbol, "KOSPI")
    suffix = ".KS" if market in ("KOSPI", "STK") else ".KQ"
    return f"{symbol}{suffix}"


def _fetch_yf_prices(symbols: list[str], market_map: dict[str, str]) -> dict[str, StockQuote]:
    """yfinance로 여러 종목 일괄 조회 (동기)"""
    import yfinance as yf

    if not symbols:
        return {}

    tickers = [_get_yf_ticker(sym, market_map) for sym in symbols]
    ticker_to_symbol = {_get_yf_ticker(sym, market_map): sym for sym in symbols}

    result: dict[str, StockQuote] = {}

    try:
        data = yf.download(
            " ".join(tickers),
            period="5d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if data is None or data.empty:
            return {}

        now = time.time()
        single_ticker = len(tickers) == 1

        for ticker, symbol in ticker_to_symbol.items():
            try:
                if single_ticker:
                    df = data
                else:
                    df = data.xs(ticker, axis=1, level=1) if ticker in data.columns.get_level_values(1) else None
                if df is None or df.empty:
                    continue
                df = df.dropna(subset=["Close"])
                if df.empty:
                    continue

                last = df.iloc[-1]
                close = int(round(float(last["Close"])))
                if close == 0:
                    continue

                date_str = str(df.index[-1].date())

                # korea-stocks.json에서 이름 가져오기 시도
                name = symbol
                try:
                    with open(_STOCKS_JSON_PATH, "r", encoding="utf-8") as f:
                        for s in json.load(f):
                            if s["symbol"] == symbol:
                                name = s.get("name", symbol)
                                break
                except Exception:
                    pass

                result[symbol] = StockQuote(
                    symbol=symbol,
                    name=name,
                    date=date_str,
                    open=int(round(float(last.get("Open", 0)))),
                    high=int(round(float(last.get("High", 0)))),
                    low=int(round(float(last.get("Low", 0)))),
                    close=close,
                    volume=int(float(last.get("Volume", 0))),
                    source="yfinance",
                    timestamp=now,
                )
            except Exception as e:
                print(f"[YFinanceKRProvider] {symbol} 파싱 실패: {e}")
                continue
    except Exception as e:
        print(f"[YFinanceKRProvider] 다운로드 실패: {e}")

    # .KS 실패한 종목은 .KQ로 재시도
    missing = [sym for sym in symbols if sym not in result]
    for sym in missing:
        if market_map.get(sym) in ("KOSPI", "STK"):
            alt_ticker = f"{sym}.KQ"
        else:
            alt_ticker = f"{sym}.KS"
        try:
            df = yf.download(alt_ticker, period="5d", interval="1d",
                             auto_adjust=True, progress=False)
            if df is None or df.empty:
                continue
            if hasattr(df.columns, "levels"):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=["Close"])
            if df.empty:
                continue
            last = df.iloc[-1]
            close = int(round(float(last["Close"])))
            if close == 0:
                continue
            result[sym] = StockQuote(
                symbol=sym,
                name=sym,
                date=str(df.index[-1].date()),
                open=int(round(float(last.get("Open", 0)))),
                high=int(round(float(last.get("High", 0)))),
                low=int(round(float(last.get("Low", 0)))),
                close=close,
                volume=int(float(last.get("Volume", 0))),
                source="yfinance",
                timestamp=time.time(),
            )
        except Exception:
            continue

    return result


class YFinanceKRProvider(BaseProvider):
    name = "yfinance"

    def __init__(self):
        self._market_map = _load_market_map()

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        result = await asyncio.to_thread(_fetch_yf_prices, [symbol], self._market_map)
        return result.get(symbol)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        return await asyncio.to_thread(_fetch_yf_prices, symbols, self._market_map)

    async def health_check(self) -> bool:
        result = await asyncio.to_thread(_fetch_yf_prices, ["005930"], self._market_map)
        return "005930" in result
