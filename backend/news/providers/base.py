"""
Abstract base class for news providers.

Mirrors the design of engine/providers/base.py (BaseProvider) but for news data.
Each concrete provider must normalize its output to RawArticle.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from news.schemas import RawArticle


class BaseNewsProvider(ABC):
    """Abstract interface for a news data source."""

    name: str = "base"

    @abstractmethod
    async def fetch(self, max_articles: int = 50) -> List[RawArticle]:
        """Fetch recent articles. Returns list of RawArticle (provider-normalized)."""
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if required env vars / credentials are present."""
        ...

    async def health_check(self) -> bool:
        """Quick connectivity test. Default: try fetch(1) and return non-empty."""
        try:
            results = await self.fetch(max_articles=1)
            return len(results) > 0
        except Exception:
            return False
