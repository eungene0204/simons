"""
토스증권 Open API Provider — 한국 주식 배치 시세 (대량 조회 레인)

- 인증·토큰 캐시·배치 조회는 공통부(toss_base.TossOpenAPIProvider) 구현을 사용한다
- 한국 규약: 6자리 종목코드 필터, KST 날짜, 원 단위 정수가, 전일종가=data/ohlcv 파케이
- 여러 종목 조회(get_prices)의 주력 레인 — 단건 상세(OHLC·거래량)는 KIS REST 체인 담당
- lastPrice에는 시간외 거래 가격도 반영된다 (장외 시간 등락률은 참고치)
"""

import asyncio
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from .base import StockQuote
from .toss_base import TossOpenAPIProvider

_ROOT = Path(__file__).resolve().parents[3]
_KR_OHLCV_DIR = _ROOT / "data" / "ohlcv"
_KST = ZoneInfo("Asia/Seoul")

# 한국 심볼: 6자리·숫자 시작 (005930, 0151S0)
_KR_SYMBOL_RE = re.compile(r"^\d[0-9A-Z]{5}$")


def is_kr_symbol(symbol: str) -> bool:
    """한국 종목코드 형식 여부"""
    return bool(_KR_SYMBOL_RE.fullmatch(symbol))


class TossKRProvider(TossOpenAPIProvider):
    name = "toss_kr"

    # ── 한국 규약 ──────────────────────────────────

    def _data_dir(self) -> Path:
        return _KR_OHLCV_DIR

    def _to_quote(self, item: dict, symbol: Optional[str] = None) -> Optional[StockQuote]:
        symbol = symbol or item.get("symbol", "")
        try:
            close = float(item.get("lastPrice") or 0)
        except (TypeError, ValueError):
            return None
        if not symbol or close <= 0:
            return None

        ts = item.get("timestamp")
        try:
            dt = datetime.fromisoformat(ts) if ts else datetime.now(_KST)
        except ValueError:
            dt = datetime.now(_KST)
        date_str = dt.astimezone(_KST).strftime("%Y-%m-%d")

        prev_close = self._prev_close(symbol, close)
        price = int(round(close))  # 한국 시세는 원 단위 정수 규약
        prev = int(round(prev_close))
        return StockQuote(
            symbol=symbol,
            name=symbol,  # 시세 응답에 종목명 없음 — 이름은 마스터/상세 경로가 채운다
            date=date_str,
            open=0,
            high=0,
            low=0,
            close=price,
            volume=0,
            source="toss_kr",
            timestamp=time.time(),
            prev_close=prev,
            change_rate=round((price - prev) / prev * 100, 2) if prev > 0 else 0.0,
        )

    # ── 공개 API ───────────────────────────────────

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        kr_symbols = [s for s in symbols if is_kr_symbol(s)]
        if not kr_symbols or not self.is_configured():
            return {}
        return await asyncio.to_thread(self._fetch_quotes, kr_symbols)

    async def health_check(self) -> bool:
        return (await self.get_price("005930")) is not None
