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


def test_oversized_single_batch_is_trimmed_to_cap(monkeypatch):
    """2026-08-24 사고 재현: 배치 멤버 보호 예외로 30종목이 상한을 통과해 KIS
    세션 등록 정원 초과(MAX SUBSCRIBE OVER) → 거부 종목 영구 틱 침묵. 상한은
    배치 크기와 무관하게 강제하고, 최신(뒤쪽) 종목만 남긴다."""
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")

    async def scenario():
        p = KISWebSocketProvider()
        p._max_symbols = 2
        await p.subscribe(["A", "B", "C", "D"])
        assert list(p._subscribed) == ["C", "D"]
        # A·B는 등록해 본 적이 없다 — 해제를 보내면 not found desync 소음만 생긴다
        assert _drain(p._pending_unsubscribe) == []
        assert _drain(p._pending_subscribe) == ["C", "D"]

    asyncio.run(scenario())


def test_oversized_batch_unsubscribes_preexisting_members(monkeypatch):
    """상한 초과 배치가 기존 구독을 밀어낼 때, 서버에 실제 등록돼 있던(기존)
    종목만 해제 큐로 보낸다."""
    monkeypatch.setenv("KIS_APP_KEY", "k")
    monkeypatch.setenv("KIS_APP_SECRET", "s")

    async def scenario():
        p = KISWebSocketProvider()
        p._max_symbols = 2
        await p.subscribe(["A", "B"])
        _drain(p._pending_subscribe)
        await p.subscribe(["C", "D", "E"])
        assert list(p._subscribed) == ["D", "E"]
        # 기존 등록 A·B만 해제 — 이번 배치에서 잘린 C는 해제 대상 아님
        assert _drain(p._pending_unsubscribe) == ["A", "B"]
        assert _drain(p._pending_subscribe) == ["D", "E"]

    asyncio.run(scenario())
