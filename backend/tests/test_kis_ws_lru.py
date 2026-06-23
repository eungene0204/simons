"""KIS WebSocket 구독 LRU 관리 테스트.

KIS WS는 세션당 실시간 등록 건수 상한이 있어, 초과 종목은 조용히 틱이 안 들어온다.
구독을 LRU로 관리해 최근 조회 종목이 항상 등록되도록 하고, 상한 초과 시 가장
오래된 종목을 해제하는지 검증한다.
"""
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.providers.kis_ws import KISWebSocketProvider


def _drain(queue: asyncio.Queue) -> list:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def test_lru_evicts_oldest_when_over_cap(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")

    async def scenario():
        p = KISWebSocketProvider()
        p._max_symbols = 3
        await p.subscribe(["A", "B", "C"])
        assert list(p._subscribed) == ["A", "B", "C"]
        assert _drain(p._pending_subscribe) == ["A", "B", "C"]

        # 상한(3) 초과 → 가장 오래된 A가 해제되고 D가 등록된다.
        await p.subscribe(["D"])
        assert list(p._subscribed) == ["B", "C", "D"]
        assert _drain(p._pending_subscribe) == ["D"]
        assert _drain(p._pending_unsubscribe) == ["A"]

    asyncio.run(scenario())


def test_resubscribe_refreshes_recency(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")

    async def scenario():
        p = KISWebSocketProvider()
        p._max_symbols = 3
        await p.subscribe(["A", "B", "C"])
        # A를 다시 구독 → 최근 사용으로 갱신되어 LRU 맨 뒤로.
        await p.subscribe(["A"])
        assert list(p._subscribed) == ["B", "C", "A"]
        # 신규 D 추가 → 이제 가장 오래된 B가 밀려난다(A는 살아남음).
        await p.subscribe(["D"])
        assert list(p._subscribed) == ["C", "A", "D"]
        assert "B" not in p._subscribed
        assert _drain(p._pending_unsubscribe) == ["B"]

    asyncio.run(scenario())


def test_eviction_clears_caches(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")

    async def scenario():
        p = KISWebSocketProvider()
        p._max_symbols = 1
        await p.subscribe(["A"])
        p._cache["A"] = object()
        p._orderbook_cache["A"] = {"symbol": "A"}
        p._recent_trades["A"] = [{"price": 1}]

        await p.subscribe(["B"])  # A 밀려남
        assert "A" not in p._subscribed
        assert "A" not in p._cache
        assert "A" not in p._orderbook_cache
        assert "A" not in p._recent_trades

    asyncio.run(scenario())


def test_oversized_single_batch_does_not_evict_its_own_members(monkeypatch):
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")

    async def scenario():
        p = KISWebSocketProvider()
        p._max_symbols = 2
        # 한 번에 상한보다 많은 종목을 요청해도, 방금 요청한 종목끼리는 서로
        # 밀어내지 않는다(요청한 종목을 즉시 버리지 않기 위함).
        await p.subscribe(["A", "B", "C", "D"])
        assert list(p._subscribed) == ["A", "B", "C", "D"]
        assert _drain(p._pending_unsubscribe) == []

    asyncio.run(scenario())
