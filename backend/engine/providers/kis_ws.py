"""
한국투자증권 (KIS) WebSocket 실시간 시세 Provider
- WebSocket 기반 실시간 체결가 수신 (H0STCNT0)
- 환경변수: KIS_APP_KEY, KIS_APP_SECRET
- 백그라운드 루프가 WebSocket 연결 유지 및 자동 재접속

사용법:
    provider = KISWebSocketProvider()
    await provider.start()                    # 백그라운드 연결 시작
    await provider.subscribe(["005930"])      # 종목 구독
    quote = await provider.get_price("005930")
    await provider.stop()
"""

import asyncio
import json
import os
import time
import requests
import logging
from typing import Optional
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed

from .base import BaseProvider, StockQuote

logger = logging.getLogger(__name__)

_REST_BASE = "https://openapi.koreainvestment.com:9443"
_WS_URL = "ws://ops.koreainvestment.com:21000"

# H0STCNT0 응답 필드 인덱스 (KIS 공식 문서 기준)
# 0:유가증권단축종목코드 1:주식체결시간 2:주식현재가 3:전일대비부호 4:전일대비
# 5:전일대비율 6:가중평균주식가격 7:주식시가 8:주식최고가 9:주식최저가
# 10:매도호가 11:매수호가 12:체결거래량 13:누적거래량 14:누적거래대금
_F_SYMBOL = 0
_F_TIME = 1
_F_PRICE = 2
_F_SIGN = 3
_F_DIFF = 4
_F_RATE = 5
_F_OPEN = 7
_F_HIGH = 8
_F_LOW = 9
_F_VOLUME = 13


class KISWebSocketProvider(BaseProvider):
    """
    KIS WebSocket 기반 실시간 시세 Provider.
    get_price/get_prices는 인메모리 캐시에서 즉시 반환.
    """

    name = "kis_ws"

    def __init__(self):
        self._app_key = os.getenv("KIS_APP_KEY", "").strip()
        self._app_secret = os.getenv("KIS_APP_SECRET", "").strip()
        self._ws_url = _WS_URL

        # 승인키 (WebSocket 전용, REST 토큰과 다름)
        self._approval_key: Optional[str] = None

        # 구독 중인 종목 집합
        self._subscribed: set[str] = set()

        # 신규 구독 요청 큐 (ws_loop에서 실시간 처리)
        self._pending_subscribe: asyncio.Queue[str] = asyncio.Queue()

        # 인메모리 시세 캐시: symbol → StockQuote
        self._cache: dict[str, StockQuote] = {}
        self._cache_lock = asyncio.Lock()

        # 백그라운드 태스크
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # 재접속 대기 시간 (초), 최대 60초
        self._reconnect_delay = 5

    def is_configured(self) -> bool:
        return bool(self._app_key and self._app_secret)

    # ------------------------------------------------------------------ #
    #  승인키 발급                                                          #
    # ------------------------------------------------------------------ #

    def _fetch_approval_key(self) -> Optional[str]:
        """WebSocket 접속 승인키 발급 (동기, 별도 스레드에서 호출)"""
        try:
            resp = requests.post(
                f"{_REST_BASE}/oauth2/Approval",
                headers={"content-type": "application/json"},
                json={
                    "grant_type": "client_credentials",
                    "appkey": self._app_key,
                    "secretkey": self._app_secret,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.error("[KIS_WS] 승인키 발급 실패: %s %s", resp.status_code, resp.text[:200])
                return None
            key = resp.json().get("approval_key")
            if key:
                logger.info("[KIS_WS] 승인키 발급 성공")
            return key
        except Exception as e:
            logger.error("[KIS_WS] 승인키 발급 예외: %s", e)
            return None

    async def _ensure_approval_key(self) -> Optional[str]:
        if self._approval_key:
            return self._approval_key
        self._approval_key = await asyncio.to_thread(self._fetch_approval_key)
        return self._approval_key

    # ------------------------------------------------------------------ #
    #  구독 메시지 생성                                                     #
    # ------------------------------------------------------------------ #

    def _make_subscribe_msg(self, symbol: str, tr_type: str = "1") -> str:
        """tr_type: '1'=등록, '2'=해제"""
        return json.dumps({
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": tr_type,
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": "H0STCNT0",
                    "tr_key": symbol,
                },
            },
        })

    # ------------------------------------------------------------------ #
    #  메시지 파싱                                                          #
    # ------------------------------------------------------------------ #

    def _parse_realtime(self, raw: str) -> Optional[StockQuote]:
        """
        실시간 체결가 메시지 파싱.
        포맷: '0|H0STCNT0|{cnt}|{field1}^{field2}^...'
        """
        try:
            parts = raw.split("|")
            if len(parts) < 4:
                return None
            # parts[0]='0', parts[1]='H0STCNT0', parts[2]=건수, parts[3]=데이터(^구분)
            if parts[0] != "0" or parts[1] != "H0STCNT0":
                return None

            fields = parts[3].split("^")
            if len(fields) < 14:
                return None

            symbol = fields[_F_SYMBOL]
            price = int(fields[_F_PRICE] or "0")
            if price == 0:
                return None

            today = datetime.now().strftime("%Y-%m-%d")

            # 전일대비: 부호(3=보합,4/1=하락/하한,2/5=상승/상한)와 변동폭으로 전일종가 계산
            diff = int(fields[_F_DIFF] or "0")
            sign = fields[_F_SIGN]
            if sign in ("4", "1"):   # 하락: 전일종가 = 현재가 + 변동폭
                prev_close = price + diff
            elif sign in ("2", "5"):  # 상승: 전일종가 = 현재가 - 변동폭
                prev_close = price - diff
            else:
                prev_close = price

            change_rate = float(fields[_F_RATE] or "0")
            # 하락 시 부호 반영
            if sign in ("4", "1") and change_rate > 0:
                change_rate = -change_rate

            return StockQuote(
                symbol=symbol,
                name=symbol,  # WebSocket에서는 종목명 미전송
                date=today,
                open=int(fields[_F_OPEN] or "0"),
                high=int(fields[_F_HIGH] or "0"),
                low=int(fields[_F_LOW] or "0"),
                close=price,
                volume=int(fields[_F_VOLUME] or "0"),
                source="kis_ws",
                timestamp=time.time(),
                prev_close=prev_close,
                change_rate=change_rate,
            )
        except Exception as e:
            logger.debug("[KIS_WS] 파싱 실패: %s | raw=%s", e, raw[:100])
            return None

    # ------------------------------------------------------------------ #
    #  WebSocket 루프                                                       #
    # ------------------------------------------------------------------ #

    async def _ws_loop(self):
        """WebSocket 연결 유지 및 메시지 처리 루프"""
        while self._running:
            try:
                approval_key = await self._ensure_approval_key()
                if not approval_key:
                    logger.error("[KIS_WS] 승인키 없음, %ds 후 재시도", self._reconnect_delay)
                    await asyncio.sleep(self._reconnect_delay)
                    continue

                logger.info("[KIS_WS] WebSocket 연결 시도: %s", self._ws_url)
                async with websockets.connect(
                    self._ws_url,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._reconnect_delay = 5  # 연결 성공 시 리셋
                    logger.info("[KIS_WS] WebSocket 연결 성공")

                    # 기존 구독 종목 재등록
                    async with self._cache_lock:
                        symbols_to_subscribe = list(self._subscribed)

                    for sym in symbols_to_subscribe:
                        await ws.send(self._make_subscribe_msg(sym, "1"))
                        logger.info("[KIS_WS] 구독 등록: %s", sym)

                    # 큐에 남아있는 pending 구독도 처리
                    while not self._pending_subscribe.empty():
                        sym = self._pending_subscribe.get_nowait()
                        if sym not in self._subscribed:
                            continue
                        await ws.send(self._make_subscribe_msg(sym, "1"))
                        logger.info("[KIS_WS] 큐 구독 등록: %s", sym)

                    # 메시지 수신 루프 (pending 구독도 병행 처리)
                    while self._running:
                        # 0.1초마다 pending 구독 확인 + 메시지 수신
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        except asyncio.TimeoutError:
                            # 타임아웃: pending 큐만 처리하고 다시 recv
                            while not self._pending_subscribe.empty():
                                sym = self._pending_subscribe.get_nowait()
                                await ws.send(self._make_subscribe_msg(sym, "1"))
                                logger.info("[KIS_WS] 실시간 구독 추가: %s", sym)
                            continue

                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")

                        # PINGPONG 처리
                        if raw.startswith("PINGPONG"):
                            await ws.send("PINGPONG")
                            continue

                        # 체결가 파싱 및 캐시 업데이트
                        if "|" in raw and raw.split("|")[1] in ("H0STCNT0",):
                            quote = self._parse_realtime(raw)
                            if quote:
                                async with self._cache_lock:
                                    self._cache[quote.symbol] = quote

                        # recv 사이사이에 pending 큐 처리
                        while not self._pending_subscribe.empty():
                            sym = self._pending_subscribe.get_nowait()
                            await ws.send(self._make_subscribe_msg(sym, "1"))
                            logger.info("[KIS_WS] 실시간 구독 추가: %s", sym)

            except ConnectionClosed as e:
                logger.warning("[KIS_WS] 연결 종료: %s", e)
                self._approval_key = None  # 재접속 시 승인키 재발급
            except Exception as e:
                logger.error("[KIS_WS] 예외 발생: %s", e)
                self._approval_key = None

            if self._running:
                logger.info("[KIS_WS] %ds 후 재접속...", self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

    # ------------------------------------------------------------------ #
    #  공개 API                                                            #
    # ------------------------------------------------------------------ #

    async def start(self):
        """백그라운드 WebSocket 루프 시작"""
        if not self.is_configured():
            logger.warning("[KIS_WS] KIS_APP_KEY / KIS_APP_SECRET 미설정, 비활성화")
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._ws_loop())
        logger.info("[KIS_WS] 시작")

    async def stop(self):
        """백그라운드 루프 중지"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[KIS_WS] 중지")

    async def subscribe(self, symbols: list[str]):
        """
        종목 구독 추가.
        WebSocket이 연결된 상태라면 큐를 통해 즉시 구독 메시지 전송.
        """
        async with self._cache_lock:
            new_symbols = [s for s in symbols if s not in self._subscribed]
            self._subscribed.update(symbols)

        for sym in new_symbols:
            await self._pending_subscribe.put(sym)
            logger.info("[KIS_WS] 구독 큐 추가: %s", sym)

    async def unsubscribe(self, symbols: list[str]):
        """종목 구독 해제"""
        async with self._cache_lock:
            for s in symbols:
                self._subscribed.discard(s)
                self._cache.pop(s, None)

    # ------------------------------------------------------------------ #
    #  BaseProvider 구현                                                   #
    # ------------------------------------------------------------------ #

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        """캐시에서 최신 시세 반환 (WebSocket 수신 데이터)"""
        if not self.is_configured():
            return None
        async with self._cache_lock:
            return self._cache.get(symbol)

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        """캐시에서 여러 종목 시세 반환"""
        if not self.is_configured():
            return {}
        async with self._cache_lock:
            return {s: self._cache[s] for s in symbols if s in self._cache}

    async def health_check(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_subscribed(self) -> list[str]:
        return list(self._subscribed)

    def get_cache_snapshot(self) -> dict[str, dict]:
        """현재 캐시 전체 스냅샷 (디버그/API 응답용)"""
        return {sym: q.to_dict() for sym, q in self._cache.items()}
