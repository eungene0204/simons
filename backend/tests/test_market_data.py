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
        # 미국 레인·한국 배치 레인 provider — 자격증명을 비워 항상 미설정(건너뜀)으로.
        # (환경변수 의존 금지: 다른 테스트가 main.py를 import하면 .env의 실제 키가
        #  로드돼 테스트가 실제 API를 호출하게 된다)
        from engine.providers.toss_us import TossUSProvider
        from engine.providers.toss_kr import TossKRProvider
        mdp.us_provider = TossUSProvider()
        mdp.us_provider._client_id = ""
        mdp.us_provider._client_secret = ""
        mdp.kr_batch_provider = TossKRProvider()
        mdp.kr_batch_provider._client_id = ""
        mdp.kr_batch_provider._client_secret = ""
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
    async def test_kr_batch_lane_serves_multi_symbol_before_rest(self):
        """2종목 이상 조회는 토스 KR 배치 레인이 REST 체인보다 먼저 받는다."""
        rest = MockProvider(should_fail=True)  # REST 체인이 불리면 실패하도록
        rest.name = "rest"
        mdp = self._make_provider([rest])
        batch = MockProvider(quotes={
            "005930": _make_quote("005930", source="toss_kr"),
            "000660": _make_quote("000660", source="toss_kr"),
        })
        batch.name = "toss_kr"
        mdp.kr_batch_provider = batch

        result = await mdp.get_prices(["005930", "000660"])
        assert result["005930"].source == "toss_kr"
        assert result["000660"].source == "toss_kr"

    @pytest.mark.asyncio
    async def test_single_symbol_skips_kr_batch_lane(self):
        """단건 조회는 OHLC·거래량을 주는 기존 REST 체인 유지 — 배치 레인 미진입."""
        rest = MockProvider(quotes={"005930": _make_quote(source="rest")})
        rest.name = "rest"
        mdp = self._make_provider([rest])

        class _Boom:
            name = "toss_kr"

            def is_configured(self):
                return True

            async def get_prices(self, symbols):
                raise AssertionError("단건 조회가 배치 레인을 타면 안 된다")

        mdp.kr_batch_provider = _Boom()
        result = await mdp.get_prices(["005930"])
        assert result["005930"].source == "rest"

    @pytest.mark.asyncio
    async def test_kr_batch_failure_falls_back_to_rest(self):
        """배치 레인 실패(예외)는 REST 체인이 흡수한다."""
        rest = MockProvider(quotes={
            "005930": _make_quote("005930", source="rest"),
            "000660": _make_quote("000660", source="rest"),
        })
        rest.name = "rest"
        mdp = self._make_provider([rest])
        batch = MockProvider(should_fail=True)
        batch.name = "toss_kr"
        mdp.kr_batch_provider = batch

        result = await mdp.get_prices(["005930", "000660"])
        assert result["005930"].source == "rest"
        assert result["000660"].source == "rest"

    @pytest.mark.asyncio
    async def test_kr_batch_leftover_falls_to_rest(self):
        """배치가 일부만 채우면 나머지는 REST 체인이 이어받는다."""
        rest = MockProvider(quotes={"000660": _make_quote("000660", source="rest")})
        rest.name = "rest"
        mdp = self._make_provider([rest])
        batch = MockProvider(quotes={"005930": _make_quote("005930", source="toss_kr")})
        batch.name = "toss_kr"
        mdp.kr_batch_provider = batch

        result = await mdp.get_prices(["005930", "000660"])
        assert result["005930"].source == "toss_kr"
        assert result["000660"].source == "rest"

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

    @pytest.mark.asyncio
    async def test_stale_ws_cache_falls_back_to_rest(self, monkeypatch):
        """2026-08-24 사고 재현: WS 캐시에 죽은 틱(신선도 초과)이 남아 있어도
        REST 폴백 체인으로 내려가 살아있는 시세를 가져와야 한다."""
        monkeypatch.setenv("KIS_APP_KEY", "test-app-key")
        monkeypatch.setenv("KIS_APP_SECRET", "test-app-secret")

        rest = MockProvider(quotes={"005930": _make_quote(source="rest", close=257000)})
        rest.name = "rest"
        mdp = self._make_provider([rest])

        stale = _make_quote(source="kis_ws_total", close=269500)
        stale.timestamp = time.time() - 3600  # 1시간 전 틱
        mdp.ws_provider._cache["005930"] = stale

        result = await mdp.get_price("005930")
        assert result is not None
        assert result.source == "rest"
        assert result.close == 257000

    @pytest.mark.asyncio
    async def test_fresh_ws_cache_served_first(self, monkeypatch):
        """신선한 WS 캐시는 그대로 최우선 서빙된다(기존 동작 보존)."""
        monkeypatch.setenv("KIS_APP_KEY", "test-app-key")
        monkeypatch.setenv("KIS_APP_SECRET", "test-app-secret")

        rest = MockProvider(quotes={"005930": _make_quote(source="rest")})
        rest.name = "rest"
        mdp = self._make_provider([rest])
        mdp.ws_provider._cache["005930"] = _make_quote(source="kis_ws_total")

        result = await mdp.get_price("005930")
        assert result is not None
        assert result.source == "kis_ws_total"

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
