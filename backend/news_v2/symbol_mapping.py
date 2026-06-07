"""Symbol mapping helpers for the news tab cache pipeline."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class SymbolCandidate:
    symbol: str
    company_name: Optional[str]
    aliases: tuple[str, ...]
    sector_keywords: tuple[str, ...] = ()


DEFAULT_CANDIDATES: tuple[SymbolCandidate, ...] = (
    SymbolCandidate("005930", "삼성전자", ("삼성전자", "삼전", "삼전닉스"), ("반도체", "메모리", "HBM")),
    SymbolCandidate("005935", "삼성전자우", ("삼성전자우", "삼전우", "삼성전자 우선주"), ("우선주",)),
    SymbolCandidate("000660", "SK하이닉스", ("SK하이닉스", "하이닉스", "하닉", "삼전닉스"), ("반도체", "메모리", "HBM")),
    SymbolCandidate("035420", "NAVER", ("NAVER", "네이버"), ("플랫폼", "검색", "커머스")),
    SymbolCandidate("005380", "현대차", ("현대차", "현대자동차"), ("자동차", "전기차")),
    SymbolCandidate("051910", "LG화학", ("LG화학",), ("배터리", "화학")),
    SymbolCandidate("006400", "삼성SDI", ("삼성SDI", "삼성에스디아이"), ("배터리", "2차전지")),
    SymbolCandidate("000270", "기아", ("기아", "기아차"), ("자동차", "전기차")),
)

_TICKER_RE = re.compile(r"\b\d{6}\b")


def extract_tickers(text: str) -> list[str]:
    return sorted(set(_TICKER_RE.findall(text or "")))


def map_symbols_from_text(
    *,
    text: str,
    target_symbol: str,
    target_name: Optional[str],
    candidates: Iterable[SymbolCandidate] = DEFAULT_CANDIDATES,
) -> list[dict]:
    normalized_text = text or ""
    results: dict[str, dict] = {}

    def add(symbol: str, company_name: Optional[str], relevance: float, evidence: str) -> None:
        current = results.get(symbol)
        if current is None or relevance > current["relevance"]:
            results[symbol] = {
                "symbol": symbol,
                "company_name": company_name,
                "relevance": relevance,
                "evidence": evidence,
            }

    target_evidence = "target_symbol"
    target_relevance = 0.8
    if target_symbol in normalized_text:
        target_relevance = 1.0
        target_evidence = "target_ticker"
    elif target_name and target_name in normalized_text:
        target_relevance = 0.95
        target_evidence = "target_name"
    add(target_symbol, target_name, target_relevance, target_evidence)

    by_symbol = {candidate.symbol: candidate for candidate in candidates}
    for ticker in extract_tickers(normalized_text):
        candidate = by_symbol.get(ticker)
        add(ticker, candidate.company_name if candidate else None, 0.9, "ticker_match")

    for candidate in candidates:
        for alias in candidate.aliases:
            if alias and alias in normalized_text:
                add(candidate.symbol, candidate.company_name, 0.88, f"alias:{alias}")
                break

    # Sector keywords intentionally fan out to several symbols.
    for candidate in candidates:
        for keyword in candidate.sector_keywords:
            if keyword and keyword in normalized_text:
                add(candidate.symbol, candidate.company_name, 0.55, f"sector:{keyword}")
                break

    return sorted(results.values(), key=lambda item: (-item["relevance"], item["symbol"]))
