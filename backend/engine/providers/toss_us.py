"""
토스증권 Open API Provider — 미국 주식 실시간 시세

- 인증·토큰 캐시·배치 조회는 공통부(toss_base.TossOpenAPIProvider) 구현을 사용한다
- 미국 규약: 영문 티커 필터, 뉴욕 시간대 날짜, 달러 소수가, 전일종가=data/ohlcv-us 파케이
- 종목명·섹터는 미국 마스터(data/us-stocks.json)에서 조회한다
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo
import re

import requests  # noqa: F401 — 테스트가 toss_us.requests를 패치한다 (공통부와 같은 모듈 객체)

from .base import StockQuote
from .toss_base import TossOpenAPIProvider

_ROOT = Path(__file__).resolve().parents[3]
_US_OHLCV_DIR = _ROOT / "data" / "ohlcv-us"
_US_MASTER_PATH = _ROOT / "data" / "us-stocks.json"

# 한국 심볼은 6자리·숫자 시작(005930, 0151S0), 미국 티커는 영문 시작(AAPL, BRK-B)
_US_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_NY_TZ = ZoneInfo("America/New_York")


def is_us_symbol(symbol: str) -> bool:
    """미국 티커 형식 여부"""
    return bool(_US_SYMBOL_RE.fullmatch(symbol))


_master_map: Optional[dict[str, dict]] = None


def us_master_entry(symbol: str) -> Optional[dict]:
    """미국 마스터(us-stocks.json)에서 종목 항목 조회 (섹터·업종·한글명 등)."""
    global _master_map
    if _master_map is None:
        try:
            data = json.loads(_US_MASTER_PATH.read_text())
            _master_map = {s["symbol"]: s for s in data if s.get("symbol")}
        except Exception:
            _master_map = {}
    return _master_map.get(symbol)


def _us_name(symbol: str) -> str:
    """미국 마스터에서 종목명 조회. 없으면 심볼 그대로."""
    entry = us_master_entry(symbol)
    return (entry or {}).get("name") or symbol


class TossUSProvider(TossOpenAPIProvider):
    name = "toss_us"

    # ── 미국 규약 ──────────────────────────────────

    def _data_dir(self) -> Path:
        return _US_OHLCV_DIR

    def _to_quote(self, item: dict, symbol: Optional[str] = None) -> Optional[StockQuote]:
        symbol = symbol or item.get("symbol", "")
        try:
            close = float(item.get("lastPrice") or 0)
        except (TypeError, ValueError):
            return None
        if not symbol or close <= 0:
            return None

        # 봉 병합·전일종가 판정은 미국 세션 날짜 기준이어야 하므로 뉴욕 시간대로 변환
        ts = item.get("timestamp")
        try:
            dt = datetime.fromisoformat(ts) if ts else datetime.now(_NY_TZ)
        except ValueError:
            dt = datetime.now(_NY_TZ)
        date_str = dt.astimezone(_NY_TZ).strftime("%Y-%m-%d")

        prev_close = self._prev_close(symbol, close)
        return StockQuote(
            symbol=symbol,
            name=_us_name(symbol),
            date=date_str,
            open=0,
            high=0,
            low=0,
            close=close,
            volume=0,
            source="toss_us",
            timestamp=time.time(),
            prev_close=prev_close,
            change_rate=round((close - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0,
        )

    # ── 공개 API ───────────────────────────────────

    async def get_stock_info(self, symbols: list[str]) -> dict[str, dict]:
        """종목 기본 정보 조회 (한글명·영문명·ISIN·상장일·발행주식수 등)."""
        us_symbols = [s for s in symbols if is_us_symbol(s)]
        if not us_symbols or not self.is_configured():
            return {}
        return await asyncio.to_thread(self._fetch_stock_info_sync, us_symbols)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        us_symbols = [s for s in symbols if is_us_symbol(s)]
        if not us_symbols or not self.is_configured():
            return {}
        return await asyncio.to_thread(self._fetch_quotes, us_symbols)

    async def health_check(self) -> bool:
        return (await self.get_price("AAPL")) is not None
