"""
MarketDataProvider 통합 테스트 — 캐시, 서킷브레이커, 폴백 체인 검증
"""

import pytest
import time
from engine.providers.base import StockQuote, BaseProvider
from engine.market_data import PriceCache, CircuitBreaker, MarketDataProvider


def _make_quote(symbol="005930", source="test", close=55500) -> StockQuote:
    return StockQuote(
        symbol=symbol, name="테스트", date="2026-03-27",
        open=55000, high=56000, low=54000, close=close,
        volume=10000000, source=source, timestamp=time.time(),
    )


# ─── PriceCache ──────────────────────────────────────────────

class TestPriceCache:
    def test_put_and_get(self):
        cache = PriceCache(market_ttl=10, off_market_ttl=300)
        quote = _make_quote()
        cache.put("005930", quote)
        assert cache.get("005930") is not None
        assert cache.get("005930").close == 55500

    def test_cache_miss(self):
        cache = PriceCache()
        assert cache.get("NONEXIST") is None

    def test_expired_entry(self):
        cache = PriceCache(market_ttl=0, off_market_ttl=0)  # 즉시 만료
        quote = _make_quote()
        cache.put("005930", quote)
        # TTL=0이므로 즉시 만료
        time.sleep(0.01)
        assert cache.get("005930") is None

    def test_invalidate(self):
        cache = PriceCache(market_ttl=300, off_market_ttl=300)
        cache.put("005930", _make_quote())
        assert cache.get("005930") is not None
        cache.invalidate("005930")
        assert cache.get("005930") is None

    def test_clear(self):
        cache = PriceCache(market_ttl=300, off_market_ttl=300)
        cache.put("005930", _make_quote("005930"))
        cache.put("000660", _make_quote("000660"))
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0


# ─── CircuitBreaker ──────────────────────────────────────────

class TestCircuitBreaker:
    def test_initial_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        assert cb.is_open("test") is False

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        cb.record_failure("test")
        cb.record_failure("test")
        assert cb.is_open("test") is False  # 2회 — 아직 닫힘
        cb.record_failure("test")
        assert cb.is_open("test") is True  # 3회 — 열림

    def test_success_resets(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        cb.record_failure("test")
        cb.record_failure("test")
        cb.record_success("test")
        cb.record_failure("test")
        cb.record_failure("test")
        assert cb.is_open("test") is False  # 중간에 리셋되어 2회만 누적

    def test_recovery_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=1)
        cb.record_failure("test")
        # disabled_until을 과거로 강제 설정하여 복구 테스트
        cb._disabled_until["test"] = time.time() - 1
        assert cb.is_open("test") is False  # 복구됨

    def test_get_status(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        cb.record_failure("test")
        status = cb.get_status("test")
        assert status["failure_count"] == 1
        assert status["is_open"] is False


# ─── MarketDataProvider ──────────────────────────────────────

class MockProvider(BaseProvider):
    name = "mock"

    def __init__(self, quotes=None, should_fail=False):
        self._quotes = quotes or {}
        self._should_fail = should_fail

    async def get_price(self, symbol):
        if self._should_fail:
            raise Exception("mock failure")
        return self._quotes.get(symbol)

    async def get_prices(self, symbols):
        if self._should_fail:
            raise Exception("mock failure")
        return {s: self._quotes[s] for s in symbols if s in self._quotes}

    async def health_check(self):
        return not self._should_fail


class TestMarketDataProvider:
    def _make_provider(self, providers):
        """테스트용 MarketDataProvider 생성 (기본 provider 초기화 건너뜀)"""
        from engine.providers.kis_ws import KISWebSocketProvider
        mdp = MarketDataProvider.__new__(MarketDataProvider)
        mdp.cache = PriceCache(market_ttl=300, off_market_ttl=300)
        mdp.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        mdp.providers = providers
        # 테스트에서는 ws_provider 미설정 (환경변수 없음) → WS 경로 건너뜀
        mdp.ws_provider = KISWebSocketProvider()
        mdp._health = {}
        for p in providers:
            from engine.providers.base import ProviderHealth
            mdp._health[p.name] = ProviderHealth(name=p.name, available=False, configured=True)
        return mdp

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """캐시에 있으면 provider 호출 안 함"""
        mock = MockProvider(should_fail=True)  # provider는 실패하도록
        mdp = self._make_provider([mock])
        # 직접 캐시에 넣기
        quote = _make_quote()
        mdp.cache.put("005930", quote)

        result = await mdp.get_price("005930")
        assert result is not None
        assert result.close == 55500

    @pytest.mark.asyncio
    async def test_fallback_chain(self):
        """첫 번째 provider 실패 시 두 번째로 폴백"""
        failing = MockProvider(should_fail=True)
        failing.name = "failing"
        working = MockProvider(quotes={"005930": _make_quote(source="working")})
        working.name = "working"

        mdp = self._make_provider([failing, working])
        result = await mdp.get_price("005930")
        assert result is not None
        assert result.source == "working"

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """모든 provider 실패 시 None 반환"""
        f1 = MockProvider(should_fail=True)
        f1.name = "f1"
        f2 = MockProvider(should_fail=True)
        f2.name = "f2"

        mdp = self._make_provider([f1, f2])
        result = await mdp.get_price("005930")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_prices_partial_fallback(self):
        """첫 provider가 일부만 반환하면 나머지는 다음 provider에서 조회"""
        p1 = MockProvider(quotes={"005930": _make_quote("005930", source="p1")})
        p1.name = "p1"
        p2 = MockProvider(quotes={
            "005930": _make_quote("005930", source="p2"),
            "000660": _make_quote("000660", source="p2"),
        })
        p2.name = "p2"

        mdp = self._make_provider([p1, p2])
        result = await mdp.get_prices(["005930", "000660"])
        assert "005930" in result
        assert "000660" in result
        assert result["005930"].source == "p1"  # 첫 provider에서 가져옴
        assert result["000660"].source == "p2"  # 두 번째 provider에서 가져옴

    @pytest.mark.asyncio
    async def test_result_cached_after_fetch(self):
        """provider 조회 결과가 캐시에 저장되는지 확인"""
        p = MockProvider(quotes={"005930": _make_quote(source="cached_test")})
        p.name = "p"
        mdp = self._make_provider([p])

        await mdp.get_price("005930")
        cached = mdp.cache.get("005930")
        assert cached is not None
        assert cached.source == "cached_test"

    def test_get_health(self):
        """health 엔드포인트 구조 확인"""
        p = MockProvider()
        p.name = "mock"
        mdp = self._make_provider([p])
        health = mdp.get_health()
        assert "status" in health
        assert "providers" in health
        assert "cache_size" in health
        assert isinstance(health["providers"], list)
