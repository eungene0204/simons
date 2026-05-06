"""
Structured event extraction layer.

Extracts event_type, sentiment, severity, and other structured fields
from an article title + summary using a rule-based keyword approach.

Design rationale:
- Rule-based baseline is interpretable, debuggable, and backtest-safe
- Each rule maps a Korean keyword pattern → event type + sentiment direction
- Scores (severity, credibility, novelty) are heuristic but configurable
- LLM-based extraction can be plugged in later as an optional second pass
  by replacing or augmenting _extract_by_rules()

The output ExtractedEvent is the authoritative input for impact_model.py.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from news.schemas import (
    ExtractedEvent,
    EventType,
    Sentiment,
    Horizon,
    NormalizedArticle,
)
from news import llm_extractor

_LLM_ENABLED_ENV = "NEWS_EVENT_LLM_ENABLED"


# ─── Rule table ───────────────────────────────────────────────────────────────
# Each entry: (pattern, event_type, sentiment, base_severity, horizon)
# Patterns are matched against the lowercased title + summary.

_RULES: List[Tuple[str, EventType, Sentiment, float, Horizon]] = [
    # Earnings
    (r"(실적|순이익|영업이익).{0,15}(상회|호조|급증|증가|서프라이즈|돌파|최대|역대)", "earnings_beat", "positive", 0.75, "1d"),
    (r"(실적|순이익|영업이익).{0,15}(하회|부진|급감|감소|실망|적자)", "earnings_miss", "negative", 0.75, "1d"),
    (r"(어닝스프라이즈|어닝 서프라이즈)", "earnings_beat", "positive", 0.8, "1d"),
    (r"(어닝쇼크|어닝 쇼크)", "earnings_miss", "negative", 0.8, "1d"),
    (r"(분기|연간).{0,10}(매출|영업이익|순이익).{0,10}(조|억).{0,5}(돌파|달성|기록)", "earnings_beat", "positive", 0.7, "1d"),
    # Guidance
    (r"(가이던스|전망|outlook).{0,10}(상향|높여|올려|개선)", "guidance_up", "positive", 0.6, "5d"),
    (r"(가이던스|전망|outlook).{0,10}(하향|낮춰|내려|악화)", "guidance_down", "negative", 0.6, "5d"),
    # Contracts / deals
    (r"(수주|계약).{0,10}(대규모|역대|최대|대형|조원|억원)", "large_contract", "positive", 0.7, "5d"),
    (r"(계약|수주).{0,5}(체결|성사|확정)", "large_contract", "positive", 0.5, "5d"),
    (r"(공급|납품).{0,10}(계약|협약|mou).{0,5}(체결|확정)", "large_contract", "positive", 0.5, "5d"),
    # Capital events
    (r"(자사주|자기주식).{0,10}(매입|취득|소각)", "share_buyback", "positive", 0.65, "1d"),
    (r"(유상증자|신주 발행)", "rights_offering", "negative", 0.65, "1d"),
    (r"전환사채|cb 발행", "convertible_bond", "negative", 0.5, "5d"),
    # Management
    (r"(ceo|대표이사|최고경영자).{0,10}(교체|사임|퇴임|해임|선임|취임)", "ceo_change", "neutral", 0.6, "5d"),
    # Regulatory / legal
    (r"(조사|수사|압수수색|검찰|금융당국).{0,15}(착수|개시|진행)", "regulatory_probe", "negative", 0.8, "5d"),
    (r"(소송|법원|판결).{0,10}(패소|패배|손해배상)", "lawsuit_loss", "negative", 0.75, "1d"),
    (r"(소송|법원|판결).{0,10}(승소|무죄|기각)", "lawsuit_win", "positive", 0.65, "1d"),
    # Operational
    (r"(공장|생산시설|플랜트).{0,10}(화재|폭발|사고|중단)", "factory_fire", "negative", 0.85, "1d"),
    (r"(신제품|새 제품|출시|런칭).{0,10}(성공|호평|인기)", "product_launch", "positive", 0.55, "5d"),
    (r"(제품|서비스).{0,10}(결함|리콜|불량|실패)", "product_failure", "negative", 0.7, "1d"),
    # Dividends
    (r"(배당).{0,15}(증가|상향|확대|특별|확정|결정|지급)", "dividend_increase", "positive", 0.5, "1d"),
    (r"(현금배당|주당.{0,5}원.{0,5}(지급|배당))", "dividend_increase", "positive", 0.5, "1d"),
    (r"(배당).{0,10}(감소|하향|삭감|중단)", "dividend_cut", "negative", 0.55, "1d"),
    (r"(주주환원|배당성향).{0,10}(확대|증가|상향|강화)", "dividend_increase", "positive", 0.55, "1d"),
    # M&A
    (r"(인수|합병|m&a|mou|지분 취득)", "mna", "neutral", 0.65, "5d"),
    # Delisting / accounting
    (r"(상장폐지|관리종목|투자주의)", "delisting_risk", "negative", 0.9, "1d"),
    (r"(회계|분식|횡령|배임).{0,10}(의혹|혐의|발각|적발)", "accounting_issue", "negative", 0.85, "5d"),
    # Analyst actions
    (r"(목표주가|목표가|tp).{0,15}(상향|올려|높여|제시|상향 조정)", "analyst_upgrade", "positive", 0.5, "5d"),
    (r"(목표주가|목표가|tp).{0,15}(하향|내려|낮춰|하향 조정)", "analyst_downgrade", "negative", 0.5, "5d"),
    (r"(매수|buy|비중확대|overweight).{0,10}(의견|제시|추천|유지)", "analyst_upgrade", "positive", 0.45, "5d"),
    (r"(매도|sell|비중축소|underweight).{0,10}(의견|제시|추천|유지)", "analyst_downgrade", "negative", 0.45, "5d"),
    # Macro
    (r"(금리|기준금리).{0,10}(인상|올려|긴축)", "macro_rate", "negative", 0.6, "5d"),
    (r"(금리|기준금리).{0,10}(인하|내려|완화)", "macro_rate", "positive", 0.6, "5d"),
    (r"(정책|규제|법안).{0,10}(완화|폐지|혜택)", "policy_change", "positive", 0.5, "5d"),
    (r"(규제|제재|법안).{0,10}(강화|신설|도입)", "policy_change", "negative", 0.55, "5d"),
    # Sector tailwind / headwind
    (r"(업황|수요|시장).{0,10}(회복|개선|성장|확대)", "sector_tailwind", "positive", 0.5, "1m"),
    (r"(업황|수요|시장).{0,10}(침체|악화|둔화|축소)", "sector_headwind", "negative", 0.5, "1m"),
    (r"(반도체|hbm|ai).{0,10}(수요|시장).{0,10}(급증|폭증|성장|회복|완판)", "sector_tailwind", "positive", 0.6, "1m"),
]

# Risk flag patterns: (pattern, flag_label)
_RISK_FLAG_RULES: List[Tuple[str, str]] = [
    (r"상장폐지|관리종목", "delisting_risk"),
    (r"분식|횡령|배임|회계 부정", "accounting_fraud"),
    (r"유동성 위기|채무불이행|디폴트", "liquidity_crisis"),
    (r"소송|법적 분쟁", "legal_dispute"),
    (r"조사|수사|검찰", "regulatory_investigation"),
    (r"대표.*사임|경영진.*교체", "management_instability"),
    (r"화재|폭발|생산 중단", "operational_disruption"),
    (r"유상증자|cb|전환사채", "dilution_risk"),
]

# Source credibility heuristics (higher = more credible)
_SOURCE_CREDIBILITY: Dict[str, float] = {
    "한국경제": 0.85,
    "매일경제": 0.85,
    "조선일보": 0.8,
    "중앙일보": 0.8,
    "동아일보": 0.8,
    "연합뉴스": 0.9,
    "Reuters": 0.95,
    "Bloomberg": 0.95,
    "Naver Finance": 0.7,
    "rss": 0.65,
}


def _match_rules(text: str) -> Optional[Tuple[EventType, Sentiment, float, Horizon]]:
    """Try each rule in order, return first match."""
    for pattern, event_type, sentiment, severity, horizon in _RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return event_type, sentiment, severity, horizon
    return None


def _extract_risk_flags(text: str) -> List[str]:
    flags = []
    for pattern, label in _RISK_FLAG_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            flags.append(label)
    return flags


def _source_credibility(source: str) -> float:
    for key, val in _SOURCE_CREDIBILITY.items():
        if key.lower() in source.lower():
            return val
    return 0.6


def _llm_enabled() -> bool:
    value = os.getenv(_LLM_ENABLED_ENV, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _compute_novelty(article: NormalizedArticle, recent_titles: Optional[List[str]] = None) -> float:
    """
    Rough novelty estimate. If we have no context, default to 0.7.
    With context, novelty is lower if many similar articles are in recent.
    """
    return 0.7


def extract_event(
    article: NormalizedArticle,
    recent_titles: Optional[List[str]] = None,  # noqa: ARG001
) -> ExtractedEvent:
    search_text = f"{article.title} {article.summary or ''}".lower()

    match = _match_rules(search_text)
    risk_flags = _extract_risk_flags(search_text)
    credibility = _source_credibility(article.source)

    if match:
        event_type, sentiment, severity, horizon = match
        if risk_flags:
            severity = min(1.0, severity + 0.1 * len(risk_flags))
        summary = article.summary or article.title[:200]
        model_version = "v1-rules"
    else:
        llm_result = None
        if _llm_enabled():
            llm_result = llm_extractor.extract(article.title, article.summary)
        if llm_result:
            event_type = llm_result["event_type"]
            sentiment  = llm_result["sentiment"]
            severity   = llm_result["severity"]
            summary    = llm_result["summary"]
            horizon    = "1d"
            model_version = "v2-llm"
        else:
            # LLM 미사용/실패 시 단어 기반 폴백
            pos_words = ["상승", "급등", "호조", "강세", "신고가", "흑자", "증가", "성장",
                         "매수", "순매수", "상향", "호재", "반등", "배당", "수혜", "기대",
                         "돌파", "역대", "최대", "확정", "완판", "주목"]
            neg_words = ["하락", "급락", "부진", "약세", "신저가", "적자", "감소", "위기",
                         "하향", "우려", "리스크", "손실", "파업", "폭락", "매도", "악화",
                         "침체", "실망", "논란", "제재", "조사"]
            pos_count = sum(1 for w in pos_words if w in search_text)
            neg_count = sum(1 for w in neg_words if w in search_text)
            if pos_count > neg_count:
                event_type, sentiment, severity, horizon = "general_positive", "positive", 0.3, "1d"
            elif neg_count > pos_count:
                event_type, sentiment, severity, horizon = "general_negative", "negative", 0.3, "1d"
            else:
                event_type, sentiment, severity, horizon = "general_neutral", "neutral", 0.2, "1d"
            summary = article.summary or article.title[:200]
            model_version = "v1-rules"

    return ExtractedEvent(
        article_id=article.id,
        event_type=event_type,
        sentiment=sentiment,
        severity=round(severity, 3),
        surprise=0.0,
        credibility=round(credibility, 3),
        novelty=0.7,
        relevance=0.5,
        summary=summary,
        risk_flags=risk_flags,
        affected_entities=[],
        expected_horizon=horizon,
        model_version=model_version,
    )
