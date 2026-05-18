"""
pykrx Provider (기존 krx_client.py 래핑)
- KRX 공개 데이터 스크래핑, API Key 불필요
- EOD 데이터 (전일 종가) + 장중에는 현재가 반영 가능
"""

import asyncio
import time
from typing import Optional
from datetime import datetime, timedelta

from .base import BaseProvider, StockQuote


def _latest_trading_date() -> str:
    candidate = datetime.now() - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate.strftime("%Y%m%d")


def _fetch_pykrx_prices(symbols: list[str], date: Optional[str] = None) -> dict[str, StockQuote]:
    """pykrx로 종목 시세 조회 (동기)"""
    from pykrx import stock as pykrx_stock

    end_date = date or _latest_trading_date()
    # 전일종가 계산을 위해 최근 10 거래일치 데이터를 조회한다
    start_dt = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=14)
    start_date = start_dt.strftime("%Y%m%d")

    result: dict[str, StockQuote] = {}
    now = time.time()

    for sym in symbols:
        try:
            df = pykrx_stock.get_market_ohlcv_by_date(start_date, end_date, sym)
            if df.empty or len(df) < 1:
                continue

            row = df.iloc[-1]
            name = pykrx_stock.get_market_ticker_name(sym)

            close = int(row.get("종가", 0))
            if close == 0:
                continue

            actual_date = df.index[-1]
            date_str = actual_date.strftime("%Y-%m-%d") if hasattr(actual_date, "strftime") else str(actual_date)[:10]

            prev_close = 0
            change_rate = 0.0
            if len(df) >= 2:
                prev_row = df.iloc[-2]
                prev_close = int(prev_row.get("종가", 0))
                if prev_close > 0:
                    change_rate = round((close - prev_close) / prev_close * 100, 2)

            result[sym] = StockQuote(
                symbol=sym,
                name=name or sym,
                date=date_str,
                open=int(row.get("시가", 0)),
                high=int(row.get("고가", 0)),
                low=int(row.get("저가", 0)),
                close=close,
                volume=int(row.get("거래량", 0)),
                source="pykrx",
                timestamp=now,
                prev_close=prev_close,
                change_rate=change_rate,
            )
        except Exception as e:
            print(f"[PykrxProvider] {sym} 조회 실패: {e}")
            continue

    return result


class PykrxProvider(BaseProvider):
    name = "pykrx"

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        result = await asyncio.to_thread(_fetch_pykrx_prices, [symbol])
        return result.get(symbol)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        return await asyncio.to_thread(_fetch_pykrx_prices, symbols)

    async def health_check(self) -> bool:
        result = await asyncio.to_thread(_fetch_pykrx_prices, ["005930"])
        return "005930" in result
