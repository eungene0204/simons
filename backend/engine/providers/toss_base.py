"""
토스증권 Open API 공통부 (시장 무관)

- OAuth2 client_credentials 토큰(24h) 캐시, 401 시 1회 재발급 후 재시도
- GET /api/v1/prices 최대 200종목 배치 조회 (클래스주 대시↔점 표기 변환 포함)
- 응답에는 현재가·통화만 있어 전일종가는 로컬 파케이 마지막 종가로 보강한다
- 시장별 규약(심볼 필터·시간대·가격 단위·파케이 위치)은 서브클래스(toss_us/toss_kr)가 정한다
- 시세 조회 전용 — 주문·계좌 API는 절대 사용하지 않는다 (모의투자 전용 규제 원칙)
"""

import os
import threading
import time
from pathlib import Path
from typing import Optional

import requests

from .base import BaseProvider, StockQuote

_BASE_URL = "https://openapi.tossinvest.com"
_REQUEST_TIMEOUT = 5
_BATCH_MAX = 200          # /api/v1/prices 심볼 상한
_TOKEN_MARGIN = 300       # 만료 5분 전 선제 재발급
_PREV_CLOSE_TTL = 1800    # 전일종가 파케이 캐시 — 일 단위 데이터라 30분이면 충분


def _load_last_closes(symbol: str, data_dir: Path) -> tuple[float, float]:
    """파케이 마지막 두 종가 (c_last, c_prev). 파일이 없으면 (0, 0)."""
    path = data_dir / f"{symbol}.parquet"
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


class TossOpenAPIProvider(BaseProvider):
    """토스 Open API 시세 provider 공통 구현 — 서브클래스가 시장 규약을 채운다."""

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

    # ── 시장별 규약 (서브클래스 구현) ───────────────

    def _data_dir(self) -> Path:
        """전일종가 보강용 로컬 파케이 디렉터리"""
        raise NotImplementedError

    def _to_quote(self, item: dict, symbol: Optional[str] = None) -> Optional[StockQuote]:
        """/api/v1/prices 응답 항목 → StockQuote (시간대·가격 단위·종목명 규약)"""
        raise NotImplementedError

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

    def _prev_close(self, symbol: str, live_price: float) -> float:
        cached = self._prev_close_cache.get(symbol)
        if cached and time.time() - cached[2] < _PREV_CLOSE_TTL:
            c_last, c_prev = cached[0], cached[1]
        else:
            c_last, c_prev = _load_last_closes(symbol, self._data_dir())
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

    # ── BaseProvider 인터페이스 ────────────────────

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        return (await self.get_prices([symbol])).get(symbol)
