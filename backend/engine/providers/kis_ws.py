"""
한국투자증권 (KIS) WebSocket 실시간 시세 Provider
- WebSocket 기반 통합 실시간 체결가/호가 수신 (H0UNCNT0, H0UNASP0)
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
from collections import OrderedDict
from typing import Optional
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed

from .base import BaseProvider, StockQuote

logger = logging.getLogger(__name__)

_REST_BASE = "https://openapi.koreainvestment.com:9443"
_WS_URL = "ws://ops.koreainvestment.com:21000"
# KRX 단독 체결/호가 피드. 통합(H0UNCNT0/H0UNASP0)은 NXT(넥스트레이드) 미참여
# 종목(예: 080220 제주반도체)에 대해 구독은 SUCCESS여도 틱을 전혀 안 보낸다.
# 모든 상장종목은 KRX에 있으므로 KRX 피드가 커버리지가 가장 넓다.
_TRADE_TR_ID = "H0STCNT0"
_ORDERBOOK_TR_ID = "H0STASP0"

# KIS WS는 세션당 실시간 등록 건수에 상한이 있다(종목당 체결+호가 2건).
# 상한을 넘으면 초과 종목은 조용히 틱이 안 들어온다. 그래서 구독 종목을 LRU로
# 관리해 최근 조회 종목이 항상 등록되도록 하고, 초과 시 가장 오래된 종목을 해제한다.
_DEFAULT_MAX_WS_SYMBOLS = 14


def _max_ws_symbols() -> int:
    try:
        return max(1, int(os.getenv("KIS_WS_MAX_SYMBOLS", str(_DEFAULT_MAX_WS_SYMBOLS))))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_WS_SYMBOLS

# H0UNCNT0 응답 필드 인덱스 (KIS 공식 문서 기준)
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
_F_ASK1 = 10
_F_BID1 = 11
_F_VOLUME = 13
_F_TRADE_VOLUME = 12
_F_SELL_COUNT = 15
_F_BUY_COUNT = 16
_F_TRADE_CLASS = 21

_OB_F_SYMBOL = 0
_OB_F_TIME = 1
_OB_F_ASK_START = 3
_OB_F_BID_START = 13
_OB_F_ASK_QTY_START = 23
_OB_F_BID_QTY_START = 33
_OB_F_TOTAL_ASK = 43
_OB_F_TOTAL_BID = 44
_OB_F_ANTC_CNPR = 47


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

        # 구독 중인 종목 (LRU 순서: 앞=가장 오래됨, 뒤=가장 최근). 값은 미사용.
        self._subscribed: "OrderedDict[str, None]" = OrderedDict()
        # 세션당 최대 구독 종목 수 (KIS 등록 상한 보호)
        self._max_symbols = _max_ws_symbols()

        # 신규 구독 요청 큐 (ws_loop에서 실시간 처리)
        self._pending_subscribe: asyncio.Queue[str] = asyncio.Queue()
        # LRU 초과로 해제할 종목 큐
        self._pending_unsubscribe: asyncio.Queue[str] = asyncio.Queue()

        # 인메모리 시세 캐시: symbol → StockQuote
        self._cache: dict[str, StockQuote] = {}
        self._orderbook_cache: dict[str, dict] = {}
        self._recent_trades: dict[str, list[dict]] = {}
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

    def _make_subscribe_msg(self, tr_id: str, symbol: str, tr_type: str = "1") -> str:
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
                    "tr_id": tr_id,
                    "tr_key": symbol,
                },
            },
        })

    async def _send_register(self, ws, symbol: str) -> None:
        await ws.send(self._make_subscribe_msg(_TRADE_TR_ID, symbol, "1"))
        await ws.send(self._make_subscribe_msg(_ORDERBOOK_TR_ID, symbol, "1"))

    async def _send_unregister(self, ws, symbol: str) -> None:
        await ws.send(self._make_subscribe_msg(_TRADE_TR_ID, symbol, "2"))
        await ws.send(self._make_subscribe_msg(_ORDERBOOK_TR_ID, symbol, "2"))

    def _log_subscribe_ack(self, raw: str) -> None:
        """KIS 구독 등록/해제 응답(JSON)의 성공/실패 코드를 로깅한다.
        등록 거부(rt_cd!=0)는 WARNING(틱 미수신의 직접 원인), 성공은 INFO."""
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return
        header = msg.get("header") or {}
        body = msg.get("body") or {}
        inp = body.get("input") or {}
        rt_cd = body.get("rt_cd")
        if rt_cd is None:
            return  # 구독 응답이 아닌 기타 제어 프레임
        tr_key = header.get("tr_key") or inp.get("tr_key")
        tr_id = header.get("tr_id") or inp.get("tr_id")
        if rt_cd != "0":
            logger.warning(
                "[KIS_WS] 구독 응답 실패 tr_id=%s tr_key=%s rt_cd=%s msg_cd=%s msg1=%s",
                tr_id, tr_key, rt_cd, body.get("msg_cd"), body.get("msg1"),
            )
        else:
            logger.info("[KIS_WS] 구독 응답 OK tr_id=%s tr_key=%s", tr_id, tr_key)

    async def _drain_pending(self, ws) -> None:
        """대기 중인 LRU 해제·신규 구독 큐를 WebSocket으로 전송한다(해제 먼저)."""
        while not self._pending_unsubscribe.empty():
            sym = self._pending_unsubscribe.get_nowait()
            await self._send_unregister(ws, sym)
            logger.info("[KIS_WS] 실시간 구독 해제(LRU 초과): %s", sym)
        while not self._pending_subscribe.empty():
            sym = self._pending_subscribe.get_nowait()
            # 큐에 있었지만 그새 LRU로 밀려난 종목은 건너뜀
            if sym not in self._subscribed:
                continue
            await self._send_register(ws, sym)
            logger.info("[KIS_WS] 실시간 구독 등록: %s", sym)

    # ------------------------------------------------------------------ #
    #  메시지 파싱                                                          #
    # ------------------------------------------------------------------ #

    def _parse_realtime(self, raw: str) -> Optional[StockQuote]:
        """
        실시간 체결가 메시지 파싱.
        포맷: '0|H0UNCNT0|{cnt}|{field1}^{field2}^...'
        """
        try:
            parts = raw.split("|")
            if len(parts) < 4:
                return None
            # parts[0]='0', parts[1]='H0UNCNT0', parts[2]=건수, parts[3]=데이터(^구분)
            if parts[0] != "0" or parts[1] not in ("H0STCNT0", "H0UNCNT0"):
                return None

            fields = parts[3].split("^")
            if len(fields) < 14:
                return None

            symbol = fields[_F_SYMBOL]
            price = int(fields[_F_PRICE] or "0")
            if price == 0:
                return None

            today = datetime.now().strftime("%Y-%m-%d")

            # 전일대비: 부호(1=상한,2=상승,3=보합,4=하한,5=하락)와 변동폭으로 전일종가 계산
            diff = int(fields[_F_DIFF] or "0")
            sign = fields[_F_SIGN]
            if sign in ("4", "5"):   # 하락/하한: 전일종가 = 현재가 + 변동폭
                prev_close = price + diff
            elif sign in ("1", "2"):  # 상한/상승: 전일종가 = 현재가 - 변동폭
                prev_close = price - diff
            else:
                prev_close = price

            change_rate = float(fields[_F_RATE] or "0")
            # 하락 시 부호 반영
            if sign in ("4", "5") and change_rate > 0:
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
                source="kis_ws_total",
                timestamp=time.time(),
                prev_close=prev_close,
                change_rate=change_rate,
            )
        except Exception as e:
            logger.debug("[KIS_WS] 파싱 실패: %s | raw=%s", e, raw[:100])
            return None

    def _parse_realtime_orderbook(self, raw: str) -> Optional[dict]:
        """
        실시간 통합 호가 메시지 파싱.
        포맷: '0|H0UNASP0|{cnt}|{field1}^{field2}^...'
        """
        try:
            parts = raw.split("|")
            if len(parts) < 4:
                return None
            if parts[0] != "0" or parts[1] not in ("H0STASP0", "H0UNASP0"):
                return None

            fields = parts[3].split("^")
            if len(fields) < _OB_F_TOTAL_BID + 1:
                return None

            symbol = fields[_OB_F_SYMBOL]
            sell_orders = []
            buy_orders = []
            for level in range(10):
                ask_price = int(fields[_OB_F_ASK_START + level] or "0")
                bid_price = int(fields[_OB_F_BID_START + level] or "0")
                ask_qty = int(fields[_OB_F_ASK_QTY_START + level] or "0")
                bid_qty = int(fields[_OB_F_BID_QTY_START + level] or "0")
                if ask_price > 0:
                    sell_orders.append({"price": ask_price, "quantity": ask_qty})
                if bid_price > 0:
                    buy_orders.append({"price": bid_price, "quantity": bid_qty})

            return {
                "symbol": symbol,
                "sellOrders": sell_orders,
                "buyOrders": buy_orders,
                "totalAskQty": int(fields[_OB_F_TOTAL_ASK] or "0"),
                "totalBidQty": int(fields[_OB_F_TOTAL_BID] or "0"),
                "anticipatedPrice": int(fields[_OB_F_ANTC_CNPR] or "0"),
                "asprAcptHour": fields[_OB_F_TIME],
                "source": "kis_ws_total_orderbook",
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.debug("[KIS_WS] 호가 파싱 실패: %s | raw=%s", e, raw[:100])
            return None

    def _build_recent_trade(self, quote: StockQuote, raw: str) -> Optional[dict]:
        try:
            parts = raw.split("|")
            if len(parts) < 4:
                return None
            fields = parts[3].split("^")
            quantity = int(fields[_F_TRADE_VOLUME] or "0")
            if quantity <= 0:
                return None

            ask1 = int(fields[_F_ASK1] or "0")
            bid1 = int(fields[_F_BID1] or "0")
            trade_class = fields[_F_TRADE_CLASS].strip() if len(fields) > _F_TRADE_CLASS else ""
            sell_count = int(fields[_F_SELL_COUNT] or "0")
            buy_count = int(fields[_F_BUY_COUNT] or "0")

            if ask1 > 0 and quote.close >= ask1:
                trade_type = "buy"
            elif bid1 > 0 and quote.close <= bid1:
                trade_type = "sell"
            elif ask1 > bid1 > 0:
                midpoint = (ask1 + bid1) / 2
                trade_type = "buy" if quote.close >= midpoint else "sell"
            elif trade_class in {"2", "5"}:
                trade_type = "buy"
            elif trade_class in {"1", "4"}:
                trade_type = "sell"
            else:
                trade_type = "buy" if buy_count >= sell_count else "sell"

            return {
                "price": quote.close,
                "quantity": quantity,
                "type": trade_type,
                "timestamp": quote.timestamp,
            }
        except Exception:
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

                    # 기존 구독 종목 재등록 (LRU 순서 유지)
                    async with self._cache_lock:
                        symbols_to_subscribe = list(self._subscribed)

                    for sym in symbols_to_subscribe:
                        await self._send_register(ws, sym)
                        logger.info("[KIS_WS] 통합 체결/호가 구독 등록: %s", sym)

                    # 큐에 남아있는 pending 해제/구독도 처리
                    await self._drain_pending(ws)

                    # 메시지 수신 루프 (pending 구독도 병행 처리)
                    while self._running:
                        # 0.1초마다 pending 구독 확인 + 메시지 수신
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        except asyncio.TimeoutError:
                            # 타임아웃: pending 해제/구독 큐만 처리하고 다시 recv
                            await self._drain_pending(ws)
                            continue

                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")

                        # PINGPONG 처리 (평문)
                        if raw.startswith("PINGPONG"):
                            await ws.send("PINGPONG")
                            continue

                        # JSON 제어 프레임: PINGPONG(keepalive) 또는 구독 등록/해제 응답
                        if raw.startswith("{"):
                            if '"PINGPONG"' in raw:
                                await ws.send(raw)  # keepalive 에코
                            else:
                                # 등록 거부(상한·미지원 등)면 WARNING으로 원인을 남긴다.
                                self._log_subscribe_ack(raw)
                            continue

                        # 체결가 파싱 및 캐시 업데이트
                        if "|" in raw and raw.split("|")[1] in ("H0STCNT0", "H0UNCNT0"):
                            quote = self._parse_realtime(raw)
                            if quote:
                                async with self._cache_lock:
                                    self._cache[quote.symbol] = quote
                                    trade = self._build_recent_trade(quote, raw)
                                    if trade:
                                        self._recent_trades.setdefault(quote.symbol, [])
                                        self._recent_trades[quote.symbol] = [
                                            trade,
                                            *self._recent_trades[quote.symbol][:15],
                                        ]

                        if "|" in raw and raw.split("|")[1] in ("H0STASP0", "H0UNASP0"):
                            orderbook = self._parse_realtime_orderbook(raw)
                            if orderbook:
                                async with self._cache_lock:
                                    self._orderbook_cache[orderbook["symbol"]] = orderbook

                        # recv 사이사이에 pending 해제/구독 큐 처리
                        await self._drain_pending(ws)

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
        종목 구독 추가 (LRU).
        - 이미 구독 중이면 최근 사용으로 갱신(move_to_end)해 LRU에서 살아남게 한다.
        - 신규 종목은 등록 큐에 넣고, 상한 초과 시 가장 오래된 종목을 해제 큐로 보낸다.
        WebSocket이 연결된 상태라면 큐를 통해 다음 루프에서 즉시 전송된다.
        """
        new_symbols: list[str] = []
        evicted: list[str] = []
        # 이번 호출에서 새로 들어온 종목은 보호(자기 자신을 evict 하지 않도록)
        incoming = set(symbols)
        async with self._cache_lock:
            for s in symbols:
                if s in self._subscribed:
                    self._subscribed.move_to_end(s)  # 최근 사용 갱신
                    continue
                self._subscribed[s] = None  # 신규 = 가장 최근
                new_symbols.append(s)
                # 상한 초과 시 가장 오래된(LRU) 종목부터 해제
                while len(self._subscribed) > self._max_symbols:
                    oldest = next(iter(self._subscribed))
                    if oldest in incoming:
                        # 이번에 추가된 종목들만 남았으면 더 못 줄임 — 중단
                        break
                    self._subscribed.pop(oldest, None)
                    self._cache.pop(oldest, None)
                    self._orderbook_cache.pop(oldest, None)
                    self._recent_trades.pop(oldest, None)
                    evicted.append(oldest)

        for sym in evicted:
            await self._pending_unsubscribe.put(sym)
            logger.info("[KIS_WS] LRU 초과 해제 큐 추가: %s", sym)
        for sym in new_symbols:
            await self._pending_subscribe.put(sym)
            logger.info("[KIS_WS] 구독 큐 추가: %s", sym)

    async def unsubscribe(self, symbols: list[str]):
        """종목 구독 해제"""
        async with self._cache_lock:
            for s in symbols:
                self._subscribed.pop(s, None)
                self._cache.pop(s, None)
                self._orderbook_cache.pop(s, None)
                self._recent_trades.pop(s, None)

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

    async def get_orderbook(self, symbol: str) -> Optional[dict]:
        if not self.is_configured():
            return None
        async with self._cache_lock:
            orderbook = self._orderbook_cache.get(symbol)
            if not orderbook:
                return None
            return {
                **orderbook,
                "recentTrades": list(self._recent_trades.get(symbol, [])),
            }

    async def health_check(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def get_subscribed(self) -> list[str]:
        return list(self._subscribed)

    def get_cache_snapshot(self) -> dict[str, dict]:
        """현재 캐시 전체 스냅샷 (디버그/API 응답용)"""
        return {sym: q.to_dict() for sym, q in self._cache.items()}
