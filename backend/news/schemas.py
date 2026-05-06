"""
News Impact AI Agent — Pydantic schemas for data contracts across the pipeline.

All timestamps are UTC-aware. publish_time is the single source of truth for
look-ahead bias enforcement in backtests.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ─── Raw provider output ──────────────────────────────────────────────────────

class RawArticle(BaseModel):
    """Output of a news provider before normalization."""
    provider: str
    external_id: Optional[str] = None
    title: str
    body: Optional[str] = None
    url: str
    source: str               # human-readable source name (e.g. "한국경제")
    author: Optional[str] = None
    published_at: datetime    # UTC
    category: Optional[str] = None
    raw_json: Dict[str, Any] = Field(default_factory=dict)


# ─── Normalized canonical article ─────────────────────────────────────────────

class NormalizedArticle(BaseModel):
    """Provider-agnostic normalized representation."""
    id: str                   # cuid assigned by storage
    title: str
    summary: Optional[str] = None
    url: str
    source: str
    author: Optional[str] = None
    published_at: datetime    # UTC — the authoritative look-ahead boundary
    crawled_at: datetime
    category: Optional[str] = None
    language: str = "ko"
    body_hash: Optional[str] = None
    canonical_id: Optional[str] = None
    is_canonical: bool = True


# ─── Entity mapping ───────────────────────────────────────────────────────────

ArticleScope = Literal["stock", "sector", "macro"]


class ArticleSymbolMap(BaseModel):
    article_id: str
    symbol: str
    company_name: Optional[str] = None
    scope: ArticleScope = "stock"
    sector: Optional[str] = None
    relevance: float = Field(default=1.0, ge=0.0, le=1.0)


# ─── Structured event extraction ──────────────────────────────────────────────

EventType = Literal[
    "earnings_beat", "earnings_miss",
    "guidance_up", "guidance_down",
    "large_contract", "share_buyback",
    "rights_offering", "convertible_bond",
    "ceo_change", "regulatory_probe",
    "lawsuit_loss", "lawsuit_win",
    "factory_fire", "product_launch", "product_failure",
    "dividend_increase", "dividend_cut",
    "mna", "delisting_risk", "accounting_issue",
    "analyst_upgrade", "analyst_downgrade",
    "macro_rate", "policy_change",
    "sector_tailwind", "sector_headwind",
    "general_positive", "general_negative", "general_neutral",
]

Sentiment = Literal["positive", "negative", "neutral"]
Horizon = Literal["intraday", "1d", "5d", "1m", "3m"]


class ExtractedEvent(BaseModel):
    article_id: str
    event_type: EventType
    sentiment: Sentiment
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    surprise: float = Field(default=0.0, ge=-1.0, le=1.0)
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    novelty: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    summary: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    affected_entities: List[str] = Field(default_factory=list)
    expected_horizon: Horizon = "1d"
    model_version: str = "v1"


# ─── Impact estimation ────────────────────────────────────────────────────────

ImpactDirection = Literal["up", "down", "neutral"]
RiskAlertLevel = Literal["none", "low", "medium", "high"]
SignalType = Literal["news_event", "news_sentiment", "news_risk_alert", "news_alpha_score"]
SignalDirection = Literal["long", "short", "neutral"]


class ImpactEstimate(BaseModel):
    article_id: str
    symbol: Optional[str] = None          # None for macro/sector news
    impact_direction: ImpactDirection
    impact_score: float = Field(ge=-1.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    expected_horizon: Horizon = "1d"
    expected_alpha_1d: Optional[float] = None
    expected_alpha_5d: Optional[float] = None
    volatility_jump_risk: Optional[float] = None
    risk_alert_level: RiskAlertLevel = "none"
    model_version: str = "v1"


class NewsSignalRecord(BaseModel):
    article_id: str
    symbol: str
    signal_type: SignalType
    value: float
    direction: SignalDirection
    confidence: float = Field(ge=0.0, le=1.0)
    valid_from: datetime          # = article.published_at  (no look-ahead)
    valid_until: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    model_version: str = "v1"


# ─── Ingestion log ────────────────────────────────────────────────────────────

class IngestionStats(BaseModel):
    provider: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: Literal["running", "success", "error"] = "running"
    fetched: int = 0
    deduplicated: int = 0
    inserted: int = 0
    error: Optional[str] = None


# ─── API response shapes ──────────────────────────────────────────────────────

class NewsItemResponse(BaseModel):
    """Full article with event + impact, returned by API."""
    id: str
    title: str
    summary: Optional[str] = None
    body: Optional[str] = None
    url: str
    source: str
    published_at: datetime
    category: Optional[str] = None
    symbols: List[str] = Field(default_factory=list)
    scope: Optional[ArticleScope] = None
    sector: Optional[str] = None
    # event fields (if analyzed)
    event_type: Optional[str] = None
    sentiment: Optional[str] = None
    severity: Optional[float] = None
    credibility: Optional[float] = None
    risk_flags: List[str] = Field(default_factory=list)
    # impact fields (if estimated)
    impact_direction: Optional[str] = None
    impact_score: Optional[float] = None
    confidence_score: Optional[float] = None
    risk_alert_level: Optional[str] = None
    expected_alpha_1d: Optional[float] = None


class NewsListResponse(BaseModel):
    items: List[NewsItemResponse]
    total: int
    page: int = 1
    page_size: int = 20


class NewsSignalResponse(BaseModel):
    symbol: str
    signals: List[NewsSignalRecord]
    as_of: datetime


class NewsIngestRequest(BaseModel):
    providers: Optional[List[str]] = None   # None = all configured
    symbols: Optional[List[str]] = None     # specific symbols → Google News per symbol
    max_per_provider: int = 50


class NewsIngestResponse(BaseModel):
    logs: List[IngestionStats]
    total_inserted: int


class NewsAnalyzeRequest(BaseModel):
    article_id: str
    force: bool = False    # re-analyze even if already done
