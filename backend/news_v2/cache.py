"""
Redis cache layer for news_v2.

Degrades gracefully when Redis is unavailable: all operations become no-ops
(or return None on reads). This lets the service keep working with PG-only
behavior — slower but correct.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from news_v2.config import Settings, get_settings
from news_v2.logging_setup import get_logger
from news_v2.repository import ArticleDTO

log = get_logger(__name__)

try:
    import redis.asyncio as aioredis

    _HAS_REDIS = True
except ImportError:  # pragma: no cover
    _HAS_REDIS = False


def _serialize_article(a: ArticleDTO) -> dict:
    d = asdict(a)
    d["published_at"] = a.published_at.isoformat() if a.published_at else None
    return d


def _deserialize_article(d: dict) -> ArticleDTO:
    pub = d.get("published_at")
    if isinstance(pub, str):
        try:
            d["published_at"] = datetime.fromisoformat(pub)
        except ValueError:
            d["published_at"] = datetime.utcnow()
    return ArticleDTO(**d)


class NewsCache:
    """Thin wrapper over Redis. All methods are safe to call even when Redis is off."""

    def __init__(self, cfg: Optional[Settings] = None) -> None:
        self.cfg = cfg or get_settings()
        self._client = None  # type: ignore[var-annotated]

    @property
    def enabled(self) -> bool:
        return self.cfg.cache_enabled and _HAS_REDIS

    async def client(self):  # type: ignore[no-untyped-def]
        if not self.enabled:
            return None
        if self._client is None:
            self._client = aioredis.from_url(
                self.cfg.redis_url, encoding="utf-8", decode_responses=True
            )
        return self._client

    # ─── articles ──────────────────────────────────────────────────────────────

    @staticmethod
    def _key_articles(symbol: str) -> str:
        return f"news:{symbol}"

    @staticmethod
    def _key_status(symbol: str) -> str:
        return f"news:status:{symbol}"

    @staticmethod
    def _key_lock(symbol: str) -> str:
        return f"news:lock:{symbol}"

    @staticmethod
    def _key_views(symbol: str) -> str:
        return f"news:counters:views:{symbol}"

    @staticmethod
    def _key_priority_tier(tier: int) -> str:
        return f"news:priority:tier:{tier}"

    @staticmethod
    def _key_circuit(provider: str) -> str:
        return f"news:circuit:{provider}"

    async def get_articles(self, symbol: str) -> Optional[list[ArticleDTO]]:
        c = await self.client()
        if c is None:
            return None
        try:
            raw = await c.get(self._key_articles(symbol))
            if not raw:
                return None
            return [_deserialize_article(d) for d in json.loads(raw)]
        except Exception as e:  # pragma: no cover
            log.warning("redis_get_failed", symbol=symbol, error=str(e))
            return None

    async def set_articles(
        self, symbol: str, items: list[ArticleDTO], ttl_s: Optional[int] = None
    ) -> None:
        c = await self.client()
        if c is None:
            return
        try:
            payload = json.dumps([_serialize_article(a) for a in items], ensure_ascii=False)
            await c.setex(self._key_articles(symbol), ttl_s or self.cfg.cache_ttl_s, payload)
        except Exception as e:  # pragma: no cover
            log.warning("redis_set_failed", symbol=symbol, error=str(e))

    async def invalidate(self, symbol: str) -> None:
        c = await self.client()
        if c is None:
            return
        try:
            await c.delete(self._key_articles(symbol))
        except Exception:  # pragma: no cover
            pass

    # ─── status ────────────────────────────────────────────────────────────────

    async def get_status(self, symbol: str) -> Optional[str]:
        c = await self.client()
        if c is None:
            return None
        try:
            return await c.get(self._key_status(symbol))
        except Exception:  # pragma: no cover
            return None

    async def set_status(self, symbol: str, status: str) -> None:
        c = await self.client()
        if c is None:
            return
        try:
            await c.setex(self._key_status(symbol), self.cfg.status_ttl_s, status)
        except Exception:  # pragma: no cover
            pass

    # ─── single-flight lock ────────────────────────────────────────────────────

    async def acquire_collect_lock(self, symbol: str) -> bool:
        """SETNX. True if we got the lock (caller should enqueue), False if held."""
        c = await self.client()
        if c is None:
            return True  # No redis → no coordination; let the caller proceed.
        try:
            return bool(
                await c.set(
                    self._key_lock(symbol),
                    "1",
                    nx=True,
                    ex=self.cfg.collect_lock_ttl_s,
                )
            )
        except Exception:  # pragma: no cover
            return True

    async def release_collect_lock(self, symbol: str) -> None:
        c = await self.client()
        if c is None:
            return
        try:
            await c.delete(self._key_lock(symbol))
        except Exception:  # pragma: no cover
            pass

    # ─── view counter ──────────────────────────────────────────────────────────

    async def incr_views(self, symbol: str) -> int:
        c = await self.client()
        if c is None:
            return 0
        try:
            key = self._key_views(symbol)
            value = await c.incr(key)
            if value == 1:
                await c.expire(key, 24 * 3600)
            return int(value)
        except Exception:  # pragma: no cover
            return 0

    # ─── priority sorted set ───────────────────────────────────────────────────

    async def set_tier_members(self, tier: int, symbols_with_score: dict[str, float]) -> None:
        c = await self.client()
        if c is None or not symbols_with_score:
            return
        try:
            key = self._key_priority_tier(tier)
            pipe = c.pipeline()
            pipe.delete(key)
            pipe.zadd(key, symbols_with_score)
            await pipe.execute()
        except Exception:  # pragma: no cover
            pass

    async def get_tier_members(self, tier: int, limit: int = 500) -> list[str]:
        c = await self.client()
        if c is None:
            return []
        try:
            return list(await c.zrevrange(self._key_priority_tier(tier), 0, limit - 1))
        except Exception:  # pragma: no cover
            return []

    # ─── circuit breaker ───────────────────────────────────────────────────────

    async def is_circuit_open(self, provider: str) -> bool:
        c = await self.client()
        if c is None:
            return False
        try:
            return (await c.get(self._key_circuit(provider))) == "open"
        except Exception:  # pragma: no cover
            return False

    async def trip_circuit(self, provider: str, seconds: int = 600) -> None:
        c = await self.client()
        if c is None:
            return
        try:
            await c.setex(self._key_circuit(provider), seconds, "open")
        except Exception:  # pragma: no cover
            pass

    # ─── lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # pragma: no cover
                pass
            self._client = None
