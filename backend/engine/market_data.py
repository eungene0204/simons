"""
통합 시장 데이터 Provider

우선순위 기반 폴백 체인:
  KIS → Naver → yfinance → pykrx → KRX API

기능:
  - PriceCache: 장중 30초 / 장외 5분 TTL
  - CircuitBreaker: 3회 연속 실패 → 60초 비활성화
  - MarketDataProvider: 캐시 + 서킷브레이커 + provider 체인 통합
"""

import json
import os
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta

from engine.providers.base import BaseProvider, StockQuote, ProviderHealth
from engine.providers.naver import NaverProvider
from engine.providers.kis import KISProvider
from engine.providers.kis_ws import KISWebSocketProvider
from engine.providers.yfinance_kr import YFinanceKRProvider
from engine.providers.pykrx_provider import PykrxProvider
from engine.providers.krx_api_provider import KRXApiProvider

# ─────────────────────────────────────────────
# 상장폐지 종목 관리
# ─────────────────────────────────────────────

_DELISTED_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "delisted-stocks.json"


class DelistedSymbolStore:
    """상장폐지 종목 영구 저장소 — 조회 시 provider 체인 전체를 건너뜀"""

    def __init__(self) -> None:
        self._symbols: set[str] = set()
        self._load()

    @staticmethod
    def _normalize(symbol: str) -> str:
        """152550.KS / 152550.KQ → 152550 으로 정규화"""
        for suffix in (".KS", ".KQ"):
            if symbol.endswith(suffix):
                return symbol[: -len(suffix)]
        return symbol

    def _load(self) -> None:
        if _DELISTED_FILE.exists():
            try:
                data = json.loads(_DELISTED_FILE.read_text())
                self._symbols = {self._normalize(s) for s in data.get("symbols", [])}
            except Exception:
                self._symbols = set()

    def _save(self) -> None:
        _DELISTED_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DELISTED_FILE.write_text(json.dumps({"symbols": sorted(self._symbols)}, ensure_ascii=False, indent=2))

    def mark(self, symbol: str) -> bool:
        """상장폐지로 등록. 이미 등록된 경우 False 반환."""
        key = self._normalize(symbol)
        if key in self._symbols:
            return False
        self._symbols.add(key)
        self._save()
        return True

    def unmark(self, symbol: str) -> bool:
        """상장폐지 해제. 미등록 종목이면 False 반환."""
        key = self._normalize(symbol)
        if key not in self._symbols:
            return False
        self._symbols.discard(key)
        self._save()
        return True

    def is_delisted(self, symbol: str) -> bool:
        return self._normalize(symbol) in self._symbols

    def all(self) -> list[str]:
        return sorted(self._symbols)


delisted_store = DelistedSymbolStore()


# ─────────────────────────────────────────────
# KST 시간 유틸
# ─────────────────────────────────────────────

_KST = timezone(timedelta(hours=9))


def _is_market_hours() -> bool:
    """KST 기준 장중 여부 (평일 09:00~15:30)"""
    now = datetime.now(_KST)
    if now.weekday() >= 5:  # 토/일
        return False
    t = now.hour * 100 + now.minute
    return 900 <= t <= 1530


# ─────────────────────────────────────────────
# PriceCache
# ─────────────────────────────────────────────

class PriceCache:
    """인메모리 캐시 — 장중 30초, 장외 5분 TTL"""

    def __init__(self, market_ttl: int = 30, off_market_ttl: int = 300):
        self._store: dict[str, tuple[StockQuote, float]] = {}  # symbol → (quote, expiry)
        self._market_ttl = market_ttl
        self._off_market_ttl = off_market_ttl

    def _ttl(self) -> int:
        return self._market_ttl if _is_market_hours() else self._off_market_ttl

    def get(self, symbol: str) -> Optional[StockQuote]:
        entry = self._store.get(symbol)
        if entry is None:
            return None
        quote, expiry = entry
        if time.time() > expiry:
            del self._store[symbol]
            return None
        return quote

    def put(self, symbol: str, quote: StockQuote) -> None:
        self._store[symbol] = (quote, time.time() + self._ttl())

    def invalidate(self, symbol: str) -> None:
        self._store.pop(symbol, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


# ─────────────────────────────────────────────
# CircuitBreaker
# ─────────────────────────────────────────────

class CircuitBreaker:
    """Provider 장애 감지 — 연속 실패 시 일시 비활성화"""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 60):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count: dict[str, int] = {}
        self._disabled_until: dict[str, float] = {}

    def is_open(self, provider_name: str) -> bool:
        """True면 provider 비활성 상태 (circuit open)"""
        until = self._disabled_until.get(provider_name, 0)
        if until and time.time() < until:
            return True
        if until and time.time() >= until:
            # 복구 시도 — 카운트 리셋하고 한 번 더 시도 허용
            self._disabled_until.pop(provider_name, None)
            self._failure_count[provider_name] = 0
        return False

    def record_success(self, provider_name: str) -> None:
        self._failure_count[provider_name] = 0
        self._disabled_until.pop(provider_name, None)

    def record_failure(self, provider_name: str) -> None:
        count = self._failure_count.get(provider_name, 0) + 1
        self._failure_count[provider_name] = count
        if count >= self._failure_threshold:
            self._disabled_until[provider_name] = time.time() + self._recovery_timeout
            print(f"[CircuitBreaker] {provider_name} 비활성화 ({self._recovery_timeout}초)")

    def get_status(self, provider_name: str) -> dict:
        return {
            "failure_count": self._failure_count.get(provider_name, 0),
            "disabled_until": self._disabled_until.get(provider_name),
            "is_open": self.is_open(provider_name),
        }


# ─────────────────────────────────────────────
# MarketDataProvider
# ─────────────────────────────────────────────

class MarketDataProvider:
    """
    통합 시장 데이터 Provider

    사용법:
        provider = MarketDataProvider()
        quote = await provider.get_price("005930")
        quotes = await provider.get_prices(["005930", "000660"])
    """

    def __init__(self):
        self.cache = PriceCache()
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        self.providers: list[BaseProvider] = []
        self._health: dict[str, ProviderHealth] = {}
        self.ws_provider = KISWebSocketProvider()
        self._init_providers()

    def _init_providers(self) -> None:
        """우선순위 순서로 provider 초기화 (WebSocket 캐시 → REST 폴백 체인)"""
        candidates = [
            self.ws_provider,   # 1순위: KIS WebSocket 실시간 캐시
            KISProvider(),      # 2순위: KIS REST
            NaverProvider(),
            YFinanceKRProvider(),
            PykrxProvider(),
            KRXApiProvider(),
        ]
        for p in candidates:
            configured = p.is_configured()
            self.providers.append(p)
            self._health[p.name] = ProviderHealth(
                name=p.name,
                available=False,  # health_check 전까지 unknown
                configured=configured,
            )
            if not configured:
                print(f"[MarketData] {p.name}: 미설정 (환경변수 없음) — 건너뜀")
            else:
                print(f"[MarketData] {p.name}: 등록됨")

    async def start_ws(self) -> None:
        """KIS WebSocket 백그라운드 루프 시작"""
        # KIS는 appkey당 WS 세션이 1개뿐이라, 같은 키를 쓰는 로컬 개발 백엔드가 켜져
        # 있으면 프로덕션 세션을 가로채 양쪽 다 끊김 루프에 빠진다. 로컬은 KIS_WS_DISABLED로
        # WS를 끄고 REST/프록시만 쓴다(프로덕션에는 설정하지 않음).
        if os.environ.get("KIS_WS_DISABLED", "").strip().lower() in ("1", "true", "yes"):
            print("[MarketData] KIS_WS_DISABLED 설정 — WebSocket 비활성화 (REST/프록시만 사용)")
            return
        await self.ws_provider.start()

    async def stop_ws(self) -> None:
        """KIS WebSocket 백그라운드 루프 중지"""
        await self.ws_provider.stop()

    async def subscribe(self, symbols: list[str]) -> None:
        """실시간 구독 종목 추가"""
        await self.ws_provider.subscribe(symbols)

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        """단일 종목 현재가 — WebSocket 실시간 캐시 우선, 외부캐시 → provider 체인 순회"""
        if delisted_store.is_delisted(symbol):
            return None

        # WebSocket 실시간 캐시 최우선
        if self.ws_provider.is_configured():
            ws_quote = await self.ws_provider.get_price(symbol)
            if ws_quote:
                self.cache.put(symbol, ws_quote)
                self._update_health(self.ws_provider.name, True, 0)
                return ws_quote
            # 캐시 미스: 자동 구독 — 다음 호출부터 실시간 반영
            await self.ws_provider.subscribe([symbol])

        # 외부 캐시 (REST 폴백용)
        cached = self.cache.get(symbol)
        if cached:
            return cached

        for provider in self.providers:
            if not provider.is_configured():
                continue
            if self.circuit_breaker.is_open(provider.name):
                continue

            t0 = time.time()
            try:
                quote = await provider.get_price(symbol)
                latency = (time.time() - t0) * 1000

                if quote:
                    self.cache.put(symbol, quote)
                    self.circuit_breaker.record_success(provider.name)
                    self._update_health(provider.name, True, latency)
                    return quote
                else:
                    # 데이터 없음 (종목 미존재 등) — 실패로 간주하지 않음
                    continue
            except Exception as e:
                latency = (time.time() - t0) * 1000
                self.circuit_breaker.record_failure(provider.name)
                self._update_health(provider.name, False, latency, str(e))
                continue

        return None

    async def get_prices(self, symbols: list[str]) -> dict[str, StockQuote]:
        """여러 종목 현재가 — WebSocket 실시간 캐시 우선, 미구독 종목은 외부캐시 → REST 폴백"""
        symbols = [s for s in symbols if not delisted_store.is_delisted(s)]
        result: dict[str, StockQuote] = {}

        # 1. WebSocket 실시간 캐시 최우선 (30초 외부캐시 TTL 무시)
        if self.ws_provider.is_configured():
            ws_data = await self.ws_provider.get_prices(symbols)
            for sym, quote in ws_data.items():
                result[sym] = quote
                self.cache.put(sym, quote)  # 외부캐시도 갱신
            if ws_data:
                self._update_health(self.ws_provider.name, True, 0)

            # WebSocket 캐시에 없는 종목은 자동 구독 — 다음 폴링부터 실시간 반영
            ws_uncached = [s for s in symbols if s not in ws_data]
            if ws_uncached:
                await self.ws_provider.subscribe(ws_uncached)

        # 2. WS에서 못 구한 종목은 외부캐시 → REST 폴백
        uncached: list[str] = []
        for sym in symbols:
            if sym in result:
                continue
            cached = self.cache.get(sym)
            if cached:
                result[sym] = cached
            else:
                uncached.append(sym)

        if not uncached:
            return result

        for provider in self.providers:
            if not provider.is_configured():
                continue
            if self.circuit_breaker.is_open(provider.name):
                continue
            if not uncached:
                break

            t0 = time.time()
            try:
                fetched = await provider.get_prices(uncached)
                latency = (time.time() - t0) * 1000

                if fetched:
                    self.circuit_breaker.record_success(provider.name)
                    self._update_health(provider.name, True, latency)
                    for sym, quote in fetched.items():
                        self.cache.put(sym, quote)
                        result[sym] = quote
                    # 아직 못 구한 종목만 다음 provider에 위임
                    uncached = [s for s in uncached if s not in fetched]
                else:
                    continue
            except Exception as e:
                latency = (time.time() - t0) * 1000
                self.circuit_breaker.record_failure(provider.name)
                self._update_health(provider.name, False, latency, str(e))
                continue

        return result

    def get_health(self) -> dict:
        """전체 provider 상태 + 캐시 통계"""
        providers_status = []
        for p in self.providers:
            h = self._health.get(p.name, ProviderHealth(name=p.name, available=False, configured=False))
            cb = self.circuit_breaker.get_status(p.name)
            providers_status.append({
                **h.to_dict(),
                "circuit_breaker": cb,
            })

        return {
            "status": "ok",
            "market_hours": _is_market_hours(),
            "cache_size": self.cache.size,
            "cache_ttl": self.cache._ttl(),
            "providers": providers_status,
        }

    def _update_health(
        self, name: str, success: bool, latency_ms: float, error: Optional[str] = None
    ) -> None:
        h = self._health.get(name)
        if not h:
            return
        h.latency_ms = round(latency_ms, 1)
        if success:
            h.available = True
            h.last_success = time.time()
            h.error_count = 0
            h.last_error = None
        else:
            h.error_count += 1
            h.last_error = error


# ─────────────────────────────────────────────
# 싱글턴 인스턴스
# ─────────────────────────────────────────────

market_data_provider = MarketDataProvider()
