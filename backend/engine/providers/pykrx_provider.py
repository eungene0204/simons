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

    date = date or _latest_trading_date()
    result: dict[str, StockQuote] = {}
    now = time.time()

    for sym in symbols:
        try:
            df = pykrx_stock.get_market_ohlcv_by_date(date, date, sym)
            if df.empty:
                continue
            row = df.iloc[0]
            name = pykrx_stock.get_market_ticker_name(sym)

            close = int(row.get("종가", 0))
            if close == 0:
                continue

            date_str = f"{date[:4]}-{date[4:6]}-{date[6:8]}"

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
