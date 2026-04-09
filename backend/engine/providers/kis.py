"""
한국투자증권 (KIS) Open API Provider
- REST API 기반 실시간 현재가 조회
- 환경변수: KIS_APP_KEY, KIS_APP_SECRET
- 완전 선택적: 환경변수 없으면 자동 건너뜀
"""

import asyncio
import os
import time
import requests
from typing import Optional

from .base import BaseProvider, StockQuote

_BASE_URL = "https://openapi.koreainvestment.com:9443"
_REQUEST_TIMEOUT = 5


class KISProvider(BaseProvider):
    name = "kis"

    def __init__(self):
        self._app_key = os.getenv("KIS_APP_KEY", "").strip()
        self._app_secret = os.getenv("KIS_APP_SECRET", "").strip()
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    def is_configured(self) -> bool:
        return bool(self._app_key and self._app_secret)

    def _acquire_token_sync(self) -> Optional[str]:
        """access_token 발급 (동기)"""
        try:
            resp = requests.post(
                f"{_BASE_URL}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                },
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                print(f"[KISProvider] 토큰 발급 실패: {resp.status_code} {resp.text[:200]}")
                return None
            data = resp.json()
            token = data.get("access_token")
            # 토큰 유효기간: 약 24시간, 안전하게 23시간으로 설정
            self._token_expires_at = time.time() + 23 * 3600
            return token
        except Exception as e:
            print(f"[KISProvider] 토큰 발급 예외: {e}")
            return None

    async def _ensure_token(self) -> Optional[str]:
        """토큰 보장 (만료 시 재발급, Lock으로 race condition 방지)"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        async with self._token_lock:
            # Double-check after acquiring lock
            if self._access_token and time.time() < self._token_expires_at:
                return self._access_token
            self._access_token = await asyncio.to_thread(self._acquire_token_sync)
            return self._access_token

    def _fetch_price_sync(self, symbol: str, token: str) -> Optional[StockQuote]:
        """단일 종목 현재가 REST 조회 (동기)"""
        try:
            headers = {
                "Content-Type": "application/json; charset=UTF-8",
                "authorization": f"Bearer {token}",
                "appkey": self._app_key,
                "appsecret": self._app_secret,
                "tr_id": "FHKST01010100",
                "custtype": "P",
            }
            params = {
                "FID_COND_MRKT_DIV_CODE": "UN",
                "FID_INPUT_ISCD": symbol,
            }
            resp = requests.get(
                f"{_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=headers,
                params=params,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            output = data.get("output", {})
            close = int(output.get("stck_prpr", "0") or "0")
            if close == 0:
                return None

            from datetime import datetime
            today = datetime.now().strftime("%Y-%m-%d")

            return StockQuote(
                symbol=symbol,
                name=output.get("hts_kor_isnm", symbol),
                date=today,
                open=int(output.get("stck_oprc", "0") or "0"),
                high=int(output.get("stck_hgpr", "0") or "0"),
                low=int(output.get("stck_lwpr", "0") or "0"),
                close=close,
                volume=int(output.get("acml_vol", "0") or "0"),
                source="kis_total",
                timestamp=time.time(),
                prev_close=int(output.get("stck_sdpr", "0") or "0"),
                change_rate=float(output.get("prdy_ctrt", "0") or "0"),
            )
        except Exception as e:
            print(f"[KISProvider] {symbol} 조회 실패: {e}")
            return None

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        if not self.is_configured():
            return None
        token = await self._ensure_token()
        if not token:
            return None
        return await asyncio.to_thread(self._fetch_price_sync, symbol, token)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        if not self.is_configured():
            return {}
        token = await self._ensure_token()
        if not token:
            return {}

        # KIS rate limit: 20 req/sec → 5종목 동시 요청은 안전 범위
        quotes = await asyncio.gather(
            *(asyncio.to_thread(self._fetch_price_sync, sym, token) for sym in symbols),
            return_exceptions=True,
        )
        return {
            sym: q
            for sym, q in zip(symbols, quotes)
            if isinstance(q, StockQuote) and q is not None
        }

    async def health_check(self) -> bool:
        if not self.is_configured():
            return False
        token = await self._ensure_token()
        if not token:
            return False
        quote = await asyncio.to_thread(self._fetch_price_sync, "005930", token)
        return quote is not None
