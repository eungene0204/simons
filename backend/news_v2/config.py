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


def _app_db_url() -> str:
    """앱(Prisma) DB의 SQLAlchemy async URL — news DB와 무관하게 DATABASE_URL을 해석한다.

    Priority sync가 앱 수요 신호(WatchlistSymbol/SearchCount/VirtualPosition/Stock)를
    읽을 때 쓴다. NEWSV2_DB_URL이 Postgres로 갈려 있어도 이 앱 테이블들은 여기
    (Prisma sqlite)에 있으므로, news 세션이 아니라 앱 DB에서 읽어야 한다.

    Prisma는 `file:` URL을 schema.prisma가 있는 디렉터리(<repo>/prisma) 기준으로
    해석한다 — news.storage._db_path()와 동일 규칙으로 같은 파일을 가리키게 한다.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    prisma_dir = os.path.join(repo_root, "prisma")

    prisma_url = os.getenv("DATABASE_URL")
    if prisma_url and prisma_url.startswith("file:"):
        rel = prisma_url.replace("file:", "", 1)
        if os.path.isabs(rel):
            return "sqlite+aiosqlite:///" + rel
        # schema-relative first (Prisma's rule), then repo-root-relative as a fallback.
        schema_rel = os.path.abspath(os.path.join(prisma_dir, rel))
        if os.path.exists(schema_rel):
            return "sqlite+aiosqlite:///" + schema_rel
        root_rel = os.path.abspath(os.path.join(repo_root, rel.lstrip("./")))
        if os.path.exists(root_rel):
            return "sqlite+aiosqlite:///" + root_rel
        return "sqlite+aiosqlite:///" + schema_rel

    return "sqlite+aiosqlite:///" + os.path.join(prisma_dir, "prisma", "dev.db")


def _default_db_url() -> str:
    # news_v2 저장소: 명시 NEWSV2_DB_URL(운영 Postgres) 우선, 없으면 앱 sqlite와 동일 파일.
    explicit = os.getenv("NEWSV2_DB_URL")
    if explicit:
        return explicit
    return _app_db_url()


@dataclass(frozen=True)
class PriorityWeights:
    current_view: float = 1200.0
    watchlist: float = 650.0
    holding: float = 600.0
    view_count: float = 18.0
    search_count: float = 60.0
    turnover: float = 120.0
    news_velocity: float = 180.0
    index_member: float = 90.0
    market_cap: float = 40.0
    volatility: float = 25.0
    ai_importance: float = 50.0


@dataclass(frozen=True)
class Settings:
    enabled: bool = field(default_factory=lambda: _env_bool("NEWSV2_ENABLED", True))
    collection_enabled: bool = field(
        default_factory=lambda: _env_bool("NEWSV2_COLLECTION_ENABLED", True)
    )

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
    worker_autostart_enabled: bool = field(
        default_factory=lambda: _env_bool("NEWSV2_WORKER_AUTOSTART_ENABLED", True)
    )
    worker_concurrency: int = field(
        default_factory=lambda: _env_int("NEWSV2_WORKER_CONCURRENCY", 2)
    )
    worker_lock_path: str = field(
        default_factory=lambda: os.getenv("NEWSV2_WORKER_LOCK_PATH", "/tmp/simons_news_v2_worker.lock")
    )
    worker_queues: list[str] = field(
        default_factory=lambda: _env_list(
            "NEWSV2_WORKER_QUEUES",
            [
                "news.collect.high",
                "news.collect.default",
                "news.collect.cold",
                "news.analyze",
                "news.maintenance",
            ],
        )
    )

    # Collection queue cadences (seconds). Tier names are kept as compatibility aliases.
    hot_interval_s: int = field(
        default_factory=lambda: _env_int("NEWSV2_HOT_INTERVAL_S", _env_int("NEWSV2_TIER1_INTERVAL_S", 120))
    )
    warm_interval_s: int = field(
        default_factory=lambda: _env_int("NEWSV2_WARM_INTERVAL_S", _env_int("NEWSV2_TIER2_INTERVAL_S", 600))
    )
    cold_interval_s: int = field(
        default_factory=lambda: _env_int("NEWSV2_COLD_INTERVAL_S", _env_int("NEWSV2_TIER3_INTERVAL_S", 3600))
    )
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
    priority_recompute_interval_s: int = field(
        default_factory=lambda: _env_int("NEWSV2_PRIORITY_RECOMPUTE_INTERVAL_S", 300)
    )
    current_view_ttl_s: int = field(
        default_factory=lambda: _env_int("NEWSV2_CURRENT_VIEW_TTL_S", 600)
    )
    priority_weights: PriorityWeights = field(default_factory=PriorityWeights)

    @property
    def tier1_interval_s(self) -> int:
        return self.hot_interval_s

    @property
    def tier2_interval_s(self) -> int:
        return self.warm_interval_s

    @property
    def tier3_interval_s(self) -> int:
        return self.cold_interval_s

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
        return self.enabled and self.collection_enabled and self.celery_broker is not None


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
