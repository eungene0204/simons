"""
토스증권 Open API Provider — 미국 주식 실시간 시세 전용

- OAuth2 client_credentials 토큰(24h)을 캐시하고 GET /api/v1/prices로 최대 200종목 배치 조회
- 응답에는 현재가·통화만 있어 전일종가는 로컬 미국 파케이(data/ohlcv-us)에서 보강한다
- 시세 조회 전용 — 주문·계좌 API는 절대 사용하지 않는다 (모의투자 전용 규제 원칙)
"""

import asyncio
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from .base import BaseProvider, StockQuote

_BASE_URL = "https://openapi.tossinvest.com"
_REQUEST_TIMEOUT = 5
_BATCH_MAX = 200          # /api/v1/prices 심볼 상한
_TOKEN_MARGIN = 300       # 만료 5분 전 선제 재발급
_PREV_CLOSE_TTL = 1800    # 전일종가 파케이 캐시 — 일 단위 데이터라 30분이면 충분

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


def _load_last_closes(symbol: str, data_dir: Optional[Path] = None) -> tuple[float, float]:
    """파케이 마지막 두 종가 (c_last, c_prev). 파일이 없으면 (0, 0)."""
    path = (data_dir or _US_OHLCV_DIR) / f"{symbol}.parquet"
    if not path.exists():
        return 0.0, 0.0
    import polars as pl
    closes = [
        float(v)
        for v in pl.read_parquet(path, columns=["close"]).drop_nulls()["close"].tail(2)
    ]
    if not closes:
        return 0.0, 0.0
    if len(closes) == 1:
        return closes[0], closes[0]
    return closes[1], closes[0]


class TossUSProvider(BaseProvider):
    name = "toss_us"

    def __init__(self):
        self._client_id = os.environ.get("TOSS_INVEST_CLIENT_ID", "")
        self._client_secret = os.environ.get("TOSS_INVEST_CLIENT_SECRET", "")
        self._token = ""
        self._token_expiry = 0.0
        self._token_lock = threading.Lock()
        # symbol → (c_last, c_prev, loaded_at)
        self._prev_close_cache: dict[str, tuple[float, float, float]] = {}

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    # ── 인증 ──────────────────────────────────────

    def _get_token(self) -> str:
        with self._token_lock:
            if self._token and time.time() < self._token_expiry - _TOKEN_MARGIN:
                return self._token
            resp = requests.post(
                f"{_BASE_URL}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["access_token"]
            self._token_expiry = time.time() + float(data.get("expires_in", 86400))
            return self._token

    def _invalidate_token(self) -> None:
        with self._token_lock:
            self._token = ""

    # ── 시세 조회 ──────────────────────────────────

    def _fetch_quotes(self, symbols: list[str]) -> dict[str, StockQuote]:
        """동기 함수: 토스 /api/v1/prices 배치 조회 (스레드에서 실행)"""
        result: dict[str, StockQuote] = {}
        for i in range(0, len(symbols), _BATCH_MAX):
            batch = symbols[i : i + _BATCH_MAX]
            # 클래스주 표기 차이: 우리 마스터/파케이는 대시(BRK-B), 토스는 점(BRK.B)
            request_map = {s.replace("-", "."): s for s in batch}
            resp = self._request_prices(list(request_map.keys()))
            if resp.status_code == 401:
                # 토큰 폐기/만료 — 1회 재발급 후 재시도
                self._invalidate_token()
                resp = self._request_prices(list(request_map.keys()))
            resp.raise_for_status()
            for item in resp.json().get("result", []):
                toss_symbol = item.get("symbol", "")
                our_symbol = request_map.get(toss_symbol, toss_symbol)
                quote = self._to_quote(item, our_symbol)
                if quote:
                    result[quote.symbol] = quote
        return result

    def _request_prices(self, batch: list[str]):
        return requests.get(
            f"{_BASE_URL}/api/v1/prices",
            params={"symbols": ",".join(batch)},
            headers={"Authorization": f"Bearer {self._get_token()}"},
            timeout=_REQUEST_TIMEOUT,
        )

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

    def _prev_close(self, symbol: str, live_price: float) -> float:
        cached = self._prev_close_cache.get(symbol)
        if cached and time.time() - cached[2] < _PREV_CLOSE_TTL:
            c_last, c_prev = cached[0], cached[1]
        else:
            c_last, c_prev = _load_last_closes(symbol)
            self._prev_close_cache[symbol] = (c_last, c_prev, time.time())
        # 장 마감 후 파케이가 이미 오늘 봉을 반영했으면(현재가 == 마지막 종가) 직전 봉이 전일종가
        if c_last > 0 and abs(live_price - c_last) < 1e-9:
            return c_prev
        return c_last

    # ── 종목정보 (GET /api/v1/stocks) ──────────────

    def _fetch_stock_info_sync(self, symbols: list[str]) -> dict[str, dict]:
        """동기 함수: 토스 종목정보 배치 조회 — {마스터 심볼: 응답 항목}"""
        result: dict[str, dict] = {}
        for i in range(0, len(symbols), _BATCH_MAX):
            batch = symbols[i : i + _BATCH_MAX]
            request_map = {s.replace("-", "."): s for s in batch}

            def _request():
                return requests.get(
                    f"{_BASE_URL}/api/v1/stocks",
                    params={"symbols": ",".join(request_map.keys())},
                    headers={"Authorization": f"Bearer {self._get_token()}"},
                    timeout=_REQUEST_TIMEOUT,
                )

            resp = _request()
            if resp.status_code == 401:
                self._invalidate_token()
                resp = _request()
            resp.raise_for_status()
            for item in resp.json().get("result", []):
                toss_symbol = item.get("symbol", "")
                our_symbol = request_map.get(toss_symbol, toss_symbol)
                if our_symbol:
                    result[our_symbol] = item
        return result

    async def get_stock_info(self, symbols: list[str]) -> dict[str, dict]:
        """종목 기본 정보 조회 (한글명·영문명·ISIN·상장일·발행주식수 등)."""
        us_symbols = [s for s in symbols if is_us_symbol(s)]
        if not us_symbols or not self.is_configured():
            return {}
        return await asyncio.to_thread(self._fetch_stock_info_sync, us_symbols)

    # ── BaseProvider 인터페이스 ────────────────────

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        return (await self.get_prices([symbol])).get(symbol)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        us_symbols = [s for s in symbols if is_us_symbol(s)]
        if not us_symbols or not self.is_configured():
            return {}
        return await asyncio.to_thread(self._fetch_quotes, us_symbols)

    async def health_check(self) -> bool:
        return (await self.get_price("AAPL")) is not None
