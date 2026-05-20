"""
AI News Agent — produces summary / sentiment / impact / related_symbols.

Two implementations:
  - GeminiNewsAgent (preferred when GOOGLE_API_KEY is set)
  - HeuristicNewsAgent (always available — keyword + lexicon based)

Both share the AINewsAgent Protocol so callers (AnalysisService) can be tested
with a fake. A simple budget counter prevents runaway LLM costs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

from news_v2.config import Settings, get_settings
from news_v2.logging_setup import get_logger

log = get_logger(__name__)


@dataclass
class AgentResult:
    summary: str
    sentiment: str            # positive | neutral | negative
    sentiment_score: float    # -1.0 ~ 1.0
    impact_level: str         # low | medium | high
    market_effect: str
    related_symbols: list[str]


class AINewsAgent(Protocol):
    async def analyze(self, *, title: str, body: Optional[str], symbol: str) -> AgentResult: ...


# ─── Heuristic agent ───────────────────────────────────────────────────────────

_POSITIVE = {
    "급등", "상승", "호실적", "어닝서프라이즈", "흑자", "최대", "신고가", "수주", "계약",
    "수익", "성장", "확대", "돌파", "랠리", "투자", "버블", "기록", "흥행", "신제품",
}
_NEGATIVE = {
    "급락", "하락", "적자", "감원", "리콜", "소송", "벌금", "수사", "조사", "압수",
    "유출", "해킹", "추락", "악재", "감산", "감익", "쇼크", "위기", "파산", "디폴트",
}
_HIGH_IMPACT = {
    "어닝", "실적", "M&A", "인수", "합병", "유상증자", "감자", "분할", "퇴출", "상장폐지",
    "관리종목", "거래정지", "경영권", "최대주주",
}
_TICKER_RE = re.compile(r"\b(\d{6})\b")  # KR ticker


class HeuristicNewsAgent:
    """Cheap, deterministic fallback. No external calls."""

    async def analyze(self, *, title: str, body: Optional[str], symbol: str) -> AgentResult:
        text = f"{title}  {body or ''}"
        pos = sum(1 for kw in _POSITIVE if kw in text)
        neg = sum(1 for kw in _NEGATIVE if kw in text)
        signal = pos - neg
        if signal > 0:
            sentiment, score = "positive", min(0.2 + 0.2 * signal, 1.0)
        elif signal < 0:
            sentiment, score = "negative", max(-0.2 + 0.2 * signal, -1.0)
        else:
            sentiment, score = "neutral", 0.0

        impact_signal = sum(1 for kw in _HIGH_IMPACT if kw in text) + max(pos, neg)
        impact_level = "high" if impact_signal >= 3 else ("medium" if impact_signal >= 1 else "low")

        related = sorted({m.group(1) for m in _TICKER_RE.finditer(text) if m.group(1) != symbol})
        summary = (title or "").strip()
        market_effect = f"{sentiment} sentiment with {impact_level} expected impact"

        return AgentResult(
            summary=summary[:240],
            sentiment=sentiment,
            sentiment_score=float(score),
            impact_level=impact_level,
            market_effect=market_effect,
            related_symbols=related[:5],
        )


# ─── Gemini agent ──────────────────────────────────────────────────────────────


class GeminiNewsAgent:
    """LLM-backed analyzer. Calls Google Gemini via REST API (no SDK dep)."""

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.api_key = cfg.google_api_key
        self._budget_used = 0
        self._budget_day = datetime.now(timezone.utc).date()
        self._fallback = HeuristicNewsAgent()

    def _check_budget(self) -> bool:
        today = datetime.now(timezone.utc).date()
        if today != self._budget_day:
            self._budget_day = today
            self._budget_used = 0
        return self._budget_used < self.cfg.ai_daily_budget

    async def analyze(self, *, title: str, body: Optional[str], symbol: str) -> AgentResult:
        if not self.api_key or not self._check_budget():
            return await self._fallback.analyze(title=title, body=body, symbol=symbol)

        try:
            import httpx
        except ImportError:
            return await self._fallback.analyze(title=title, body=body, symbol=symbol)

        prompt = self._build_prompt(title=title, body=body, symbol=symbol)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-1.5-flash:generateContent?key={self.api_key}"
        )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    url,
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json"},
                    },
                )
                r.raise_for_status()
                payload = r.json()
            self._budget_used += 1
            return self._parse_response(payload, symbol)
        except Exception as e:
            log.warning("gemini_failed", symbol=symbol, error=str(e))
            return await self._fallback.analyze(title=title, body=body, symbol=symbol)

    @staticmethod
    def _build_prompt(*, title: str, body: Optional[str], symbol: str) -> str:
        body_text = (body or "")[:1500]
        return (
            "You are a financial news analyst. Analyze the following Korean stock-market news "
            f"for stock symbol {symbol}. Return STRICT JSON with keys: "
            'summary (string, <=200 chars, Korean), sentiment ("positive"|"neutral"|"negative"), '
            "sentiment_score (-1.0~1.0), impact_level (\"low\"|\"medium\"|\"high\"), "
            "market_effect (string, <=140 chars, Korean), related_symbols (array of 6-digit KR ticker strings).\n"
            f"TITLE: {title}\n\nBODY: {body_text}"
        )

    @staticmethod
    def _parse_response(payload: dict, symbol: str) -> AgentResult:
        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            text = "{}"
        import json

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {}

        sentiment = data.get("sentiment", "neutral")
        if sentiment not in {"positive", "neutral", "negative"}:
            sentiment = "neutral"
        impact = data.get("impact_level", "low")
        if impact not in {"low", "medium", "high"}:
            impact = "low"
        score = data.get("sentiment_score", 0.0)
        try:
            score = max(-1.0, min(1.0, float(score)))
        except (TypeError, ValueError):
            score = 0.0
        related = data.get("related_symbols") or []
        related = [
            str(s) for s in related if isinstance(s, (str, int)) and str(s) != symbol
        ][:5]
        return AgentResult(
            summary=str(data.get("summary", ""))[:240],
            sentiment=sentiment,
            sentiment_score=score,
            impact_level=impact,
            market_effect=str(data.get("market_effect", ""))[:200],
            related_symbols=related,
        )


# ─── factory ───────────────────────────────────────────────────────────────────


def build_agent(cfg: Optional[Settings] = None) -> AINewsAgent:
    cfg = cfg or get_settings()
    if cfg.ai_provider == "gemini" and cfg.google_api_key:
        return GeminiNewsAgent(cfg)
    return HeuristicNewsAgent()
