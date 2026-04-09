"""
네이버 금융 모바일 API Provider
- 장중 실시간 현재가 제공 (무료, API Key 불필요)
- https://m.stock.naver.com/api/stock/{symbol}/basic → 현재가, 종목명, 등락률
- https://m.stock.naver.com/api/stock/{symbol}/integration → 시가, 고가, 저가, 거래량
"""

import asyncio
import time
import re
import requests
from typing import Optional

from .base import BaseProvider, StockQuote

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _USER_AGENT}
_BASE_URL = "https://m.stock.naver.com/api/stock"
_REQUEST_TIMEOUT = 5


def _parse_number(s: str) -> int:
    """쉼표 포함 문자열 → 정수 변환 (예: '173,000' → 173000)"""
    if not s:
        return 0
    cleaned = re.sub(r"[^\d\-]", "", s)
    return int(cleaned) if cleaned else 0


def _fetch_naver_quote(symbol: str) -> Optional[StockQuote]:
    """동기 함수: 네이버 모바일 API에서 종목 시세 조회"""
    try:
        # 1) basic 엔드포인트 → 현재가, 종목명
        basic_resp = requests.get(
            f"{_BASE_URL}/{symbol}/basic",
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        if basic_resp.status_code != 200:
            return None
        basic = basic_resp.json()

        close = _parse_number(basic.get("closePrice", "0"))
        if close == 0:
            return None

        name = basic.get("stockName", symbol)
        date_str = basic.get("localTradedAt", "")[:10]  # "2026-03-27T..."

        # 전일종가 계산: close ± compareToPreviousClosePrice (방향 고려)
        compare_val = _parse_number(basic.get("compareToPreviousClosePrice", "0"))
        compare_dir = basic.get("compareToPreviousPrice", {})
        dir_code = compare_dir.get("code", "3") if isinstance(compare_dir, dict) else "3"
        # code: 1=하한가, 2=상승, 3=보합, 4=하락, 5=상한가
        if dir_code in ("4", "1"):  # 하락/하한가: 전일종가 = 현재가 + 변동폭
            prev_close = close + compare_val
        elif dir_code in ("2", "5"):  # 상승/상한가: 전일종가 = 현재가 - 변동폭
            prev_close = close - compare_val
        else:  # 보합
            prev_close = close

        # 2) integration 엔드포인트 → 시가, 고가, 저가, 거래량
        integ_resp = requests.get(
            f"{_BASE_URL}/{symbol}/integration",
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )

        open_price = 0
        high_price = 0
        low_price = 0
        volume = 0

        if integ_resp.status_code == 200:
            integ = integ_resp.json()
            infos = {item["code"]: item["value"] for item in integ.get("totalInfos", [])}
            open_price = _parse_number(infos.get("openPrice", "0"))
            high_price = _parse_number(infos.get("highPrice", "0"))
            low_price = _parse_number(infos.get("lowPrice", "0"))
            volume = _parse_number(infos.get("accumulatedTradingVolume", "0"))

        return StockQuote(
            symbol=symbol,
            name=name,
            date=date_str,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close,
            volume=volume,
            source="naver",
            timestamp=time.time(),
            prev_close=prev_close,
            change_rate=round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0,
        )
    except Exception as e:
        print(f"[NaverProvider] {symbol} 조회 실패: {e}")
        return None


class NaverProvider(BaseProvider):
    name = "naver"

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        return await asyncio.to_thread(_fetch_naver_quote, symbol)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        quotes = await asyncio.gather(
            *(self.get_price(sym) for sym in symbols),
            return_exceptions=True,
        )
        return {
            sym: q
            for sym, q in zip(symbols, quotes)
            if isinstance(q, StockQuote) and q is not None
        }

    async def health_check(self) -> bool:
        quote = await self.get_price("005930")  # 삼성전자
        return quote is not None
