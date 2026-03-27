"""
통합 시장 데이터 Provider

우선순위 기반 폴백 체인:
  KIS → Naver → yfinance → pykrx → KRX API

기능:
  - PriceCache: 장중 30초 / 장외 5분 TTL
  - CircuitBreaker: 3회 연속 실패 → 60초 비활성화
  - MarketDataProvider: 캐시 + 서킷브레이커 + provider 체인 통합
"""

import time
from typing import Optional
from datetime import datetime, timezone, timedelta

from engine.providers.base import BaseProvider, StockQuote, ProviderHealth
from engine.providers.naver import NaverProvider
from engine.providers.kis import KISProvider
from engine.providers.yfinance_kr import YFinanceKRProvider
from engine.providers.pykrx_provider import PykrxProvider
from engine.providers.krx_api_provider import KRXApiProvider


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
        self._init_providers()

    def _init_providers(self) -> None:
        """우선순위 순서로 provider 초기화"""
        candidates = [
            KISProvider(),
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

    async def get_price(self, symbol: str) -> Optional[StockQuote]:
        """단일 종목 현재가 — 캐시 → provider 체인 순회"""
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
        """여러 종목 현재가 — 캐시 분리 후 provider 체인으로 미스분 조회"""
        result: dict[str, StockQuote] = {}
        uncached: list[str] = []

        for sym in symbols:
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
