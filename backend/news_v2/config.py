"""
news_v2.config — typed settings loaded from env, with safe dev defaults.

Fail-fast on truly invalid combinations (e.g. NEWSV2_ENABLED=true but no DB URL),
but allow incremental adoption: Redis/Celery are optional, with documented
degraded behaviors when missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_list(key: str, default: list[str]) -> list[str]:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _default_db_url() -> str:
    explicit = os.getenv("NEWSV2_DB_URL")
    if explicit:
        return explicit

    prisma_url = os.getenv("DATABASE_URL")
    if prisma_url and prisma_url.startswith("file:"):
        path = prisma_url.replace("file:", "", 1)
        if not os.path.isabs(path):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            path = os.path.abspath(os.path.join(project_root, path))
        return "sqlite+aiosqlite:///" + path

    return "sqlite+aiosqlite:///" + os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "prisma", "dev.db")
    )


@dataclass(frozen=True)
class PriorityWeights:
    turnover: float = 0.30
    volatility: float = 0.20
    view_count: float = 0.20
    watchlist: float = 0.15
    search_count: float = 0.10
    ai_importance: float = 0.05


@dataclass(frozen=True)
class Settings:
    enabled: bool = field(default_factory=lambda: _env_bool("NEWSV2_ENABLED", True))

    # Storage
    db_url: str = field(default_factory=_default_db_url)

    # Redis (cache + celery broker). Empty → degraded mode (no cache, in-process tasks).
    redis_url: Optional[str] = field(
        default_factory=lambda: os.getenv("NEWSV2_REDIS_URL") or None
    )
    # Celery broker is intentionally NOT inferred from NEWSV2_REDIS_URL: enabling
    # the queue without a running worker just buries messages in Redis with no
    # one to process them. Must be set explicitly when worker is up.
    celery_broker: Optional[str] = field(
        default_factory=lambda: os.getenv("NEWSV2_CELERY_BROKER") or None
    )

    # Tier cadences (seconds)
    tier1_interval_s: int = field(default_factory=lambda: _env_int("NEWSV2_TIER1_INTERVAL_S", 120))
    tier2_interval_s: int = field(default_factory=lambda: _env_int("NEWSV2_TIER2_INTERVAL_S", 600))
    tier3_interval_s: int = field(default_factory=lambda: _env_int("NEWSV2_TIER3_INTERVAL_S", 3600))
    startup_collect_enabled: bool = field(default_factory=lambda: _env_bool("NEWSV2_STARTUP_COLLECT_ENABLED", True))
    startup_collect_delay_s: int = field(default_factory=lambda: _env_int("NEWSV2_STARTUP_COLLECT_DELAY_S", 5))
    bootstrap_symbols: list[str] = field(
        default_factory=lambda: _env_list(
            "NEWSV2_BOOTSTRAP_SYMBOLS",
            ["005930", "000660", "035420", "005380", "051910"],
        )
    )
    bootstrap_collect_limit: int = field(default_factory=lambda: _env_int("NEWSV2_BOOTSTRAP_COLLECT_LIMIT", 20))

    # Tier thresholds (priority score)
    tier1_threshold: float = field(default_factory=lambda: _env_float("NEWSV2_TIER1_THRESHOLD", 1000))
    tier2_threshold: float = field(default_factory=lambda: _env_float("NEWSV2_TIER2_THRESHOLD", 200))

    # Cache TTLs (seconds)
    cache_ttl_s: int = field(default_factory=lambda: _env_int("NEWSV2_CACHE_TTL_S", 600))
    cache_ttl_tier1_s: int = field(default_factory=lambda: _env_int("NEWSV2_CACHE_TTL_TIER1_S", 300))
    status_ttl_s: int = field(default_factory=lambda: _env_int("NEWSV2_STATUS_TTL_S", 60))
    collect_lock_ttl_s: int = field(default_factory=lambda: _env_int("NEWSV2_COLLECT_LOCK_TTL_S", 180))

    # Priority
    view_bonus: float = field(default_factory=lambda: _env_float("NEWSV2_VIEW_BONUS", 50.0))
    priority_weights: PriorityWeights = field(default_factory=PriorityWeights)

    # AI agent
    ai_daily_budget: int = field(default_factory=lambda: _env_int("NEWSV2_AI_DAILY_BUDGET", 2000))
    ai_provider: str = field(default_factory=lambda: os.getenv("NEWSV2_AI_PROVIDER", "heuristic"))
    google_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY") or None)

    # Page sizes
    default_page_size: int = field(default_factory=lambda: _env_int("NEWSV2_DEFAULT_PAGE_SIZE", 20))
    max_page_size: int = field(default_factory=lambda: _env_int("NEWSV2_MAX_PAGE_SIZE", 100))

    @property
    def cache_enabled(self) -> bool:
        return self.enabled and self.redis_url is not None

    @property
    def queue_enabled(self) -> bool:
        return self.enabled and self.celery_broker is not None


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
