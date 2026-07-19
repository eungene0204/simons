"""유니버스별 지원 팩터 레지스트리 — Universe에 따라 쓸 수 있는 데이터가 다르다.

ETF는 여러 기업을 묶은 상품이라 개별 기업 재무제표에서 계산되는 지표(PER·PBR·ROE·
부채비율 등)를 전략 조건으로 쓸 수 없다. 가격·거래량에서 파생되는 기술적 지표는 전부
쓸 수 있다. 전략 생성·수정 시 이 레지스트리로 팩터를 검증하고, 미지원 팩터는 조용히
무시하지 않고 사용자에게 이유를 설명한 뒤 대안을 제안한다(detect_etf_factor_conflict).

향후 확장(미국주식·채권·선물 등)은 여기에 유니버스 항목을 추가하는 방식으로 관리한다 —
LLM은 전략 생성 전에 반드시 유니버스에 맞는 팩터만 사용하도록 검증해야 하며, 지원하지
않는 팩터를 임의로 생성하거나 조용히 제거해서는 안 된다.
"""
from __future__ import annotations

from typing import Iterable, Optional

# FundamentalFilter.metric 중 가격·거래량에서 파생돼 유니버스와 무관하게 계산 가능한 지표.
# trading_value(일평균 거래대금)는 OHLCV 파생이라 ETF에서도 유효하다.
# market_cap은 ETF에선 순자산총액(AUM)이라 '기업 시가총액'과 의미가 달라 제외한다.
_PRICE_DERIVED_METRICS: frozenset[str] = frozenset({"trading_value"})

# 유니버스 종류 → 지원 팩터 클래스. 주식 유니버스(KOSPI/KOSDAQ/KOSPI200)는 전부 지원.
_UNIVERSE_KIND_SUPPORT: dict[str, dict[str, bool]] = {
    "STOCK": {"fundamental": True, "technical": True},
    "ETF": {"fundamental": False, "technical": True},
}


def universe_kind(universe: Optional[Iterable[str]]) -> str:
    """ParsedStrategy.universe → 유니버스 종류("ETF" | "STOCK")."""
    if universe and "ETF" in set(universe):
        return "ETF"
    return "STOCK"


def is_etf_strategy(universe: Optional[Iterable[str]]) -> bool:
    return universe_kind(universe) == "ETF"


def fundamental_metric_supported(universe: Optional[Iterable[str]], metric: str) -> bool:
    """해당 유니버스에서 이 재무 지표를 전략 조건으로 쓸 수 있는가."""
    if _UNIVERSE_KIND_SUPPORT[universe_kind(universe)]["fundamental"]:
        return True
    return metric in _PRICE_DERIVED_METRICS


def unsupported_fundamental_metrics(
    universe: Optional[Iterable[str]], metrics: Iterable[str]
) -> list[str]:
    """유니버스가 지원하지 않는 재무 지표만 골라 반환한다(입력 순서 보존·중복 제거)."""
    seen: list[str] = []
    for m in metrics:
        if not fundamental_metric_supported(universe, m) and m not in seen:
            seen.append(m)
    return seen
