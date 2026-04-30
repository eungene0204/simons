"""
Context-aware Strategy Advisor Agent — Pydantic schemas.

Input:  user_prompt + parsed_strategy + optional backtest_result + optional news_context
Output: structured review with scores, issues, recommendations, news analysis
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ─── Shared enums ─────────────────────────────────────────────────────────────

Severity = Literal["low", "medium", "high"]
OverfitRisk = Literal["low", "medium", "high"]
RiskLevel = Literal["low", "medium", "high"]
ImpactDirection = Literal["up", "down", "neutral"]
Sentiment = Literal["positive", "negative", "neutral"]
RiskAlertLevel = Literal["none", "low", "medium", "high"]


# ─── Input schemas ────────────────────────────────────────────────────────────

class BacktestSummary(BaseModel):
    """Minimal backtest result needed for advisor analysis."""
    cagr: Optional[float] = None           # e.g. 0.18 = 18%
    mdd: Optional[float] = None            # e.g. -0.32 = -32%
    sharpe: Optional[float] = None
    profit_factor: Optional[float] = None
    trade_count: Optional[int] = None
    win_rate: Optional[float] = None       # e.g. 0.55 = 55%


class NewsArticleSignal(BaseModel):
    """Single article-level signal from News Impact AI Agent."""
    event_type: str
    sentiment: Sentiment
    impact_direction: ImpactDirection = "neutral"
    impact_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)


class NewsContext(BaseModel):
    """Per-symbol aggregated news context from News Impact AI Agent."""
    symbol: str
    latest_alpha: float = Field(default=0.0)
    risk_alert_level: RiskAlertLevel = "none"
    articles: List[NewsArticleSignal] = Field(default_factory=list)


class AdvisorRequest(BaseModel):
    """Full input to the Strategy Advisor Agent."""
    user_prompt: str = Field(description="사용자가 입력한 원문 전략 설명")
    parsed_strategy: Dict[str, Any] = Field(description="NLStrategyParser가 반환한 ParsedStrategy dict")
    backtest_result: Optional[BacktestSummary] = None
    news_context: Optional[List[NewsContext]] = None


# ─── Output schemas ───────────────────────────────────────────────────────────

class Issue(BaseModel):
    """A single diagnosed problem with the strategy."""
    code: str                  # e.g. "NO_STOP_LOSS"
    severity: Severity
    message: str               # human-readable Korean explanation


class ProposedChange(BaseModel):
    """Structured DSL-level change to apply to ParsedStrategy."""
    field: str                 # e.g. "stop_loss_pct"
    action: Literal["set", "add", "remove", "modify"]
    value: Any = None
    description: str = ""


class Recommendation(BaseModel):
    """A single actionable improvement suggestion."""
    type: str                  # e.g. "risk_management", "filter", "validation"
    priority: int = Field(ge=1, le=5, description="1=most urgent")
    title: str
    reason: str
    proposed_change: Optional[ProposedChange] = None


class NewsAnalysis(BaseModel):
    """Aggregated interpretation of news signals across all symbols."""
    summary: str
    risk_level: RiskLevel
    key_events: List[str] = Field(default_factory=list)


class AIModelRecommendation(BaseModel):
    recommended: bool
    reason: str


class AdviceItem(BaseModel):
    """진단 + 해결 방법을 하나로 합친 조언 항목."""
    severity: Severity
    title: str
    body: str
    proposed_change: Optional[ProposedChange] = None


class AdvisorResponse(BaseModel):
    """Full output of the Strategy Advisor Agent."""
    strategy_score: float = Field(ge=0.0, le=100.0, description="종합 전략 점수 (0-100)")
    risk_score: float = Field(ge=0.0, le=100.0, description="리스크 점수 (높을수록 위험)")
    overfit_risk: OverfitRisk

    advice: List[AdviceItem] = Field(default_factory=list)

    news_analysis: Optional[NewsAnalysis] = None
    strategy_experiment_learning: Optional[Dict[str, Any]] = None
    suggested_experiments: List[str] = Field(default_factory=list)
    ai_model_recommendation: AIModelRecommendation
