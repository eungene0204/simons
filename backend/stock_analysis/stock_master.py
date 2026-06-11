"""
종목 마스터(Ground Truth) 접근기.

`data/korea-stocks.json`(KOSPI+KOSDAQ 등록 종목)과 symbol_resolver의 별칭 맵을
하나의 정답 테이블로 합쳐 검증 하니스/회귀 테스트의 단일 소스로 제공한다.

컬럼: ticker · stock_name · market · aliases · normalized_name · sector

별칭/리졸버와 같은 소스를 재사용해(DRY) 마스터가 인식기와 어긋나지 않게 한다.
새 의존성 없이 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .symbol_resolver import _KOREAN_ALIASES, _load_stocks

_NORMALIZE_STRIP = re.compile(r"[\s\-_./()&]+")


def normalize_name(name: str) -> str:
    """비교용 정규화: 소문자 + 공백/구분기호 제거. (예: 'SK 하이닉스' → 'sk하이닉스')"""
    return _NORMALIZE_STRIP.sub("", (name or "").strip().lower())


@dataclass(frozen=True)
class MasterEntry:
    ticker: str
    stock_name: str
    market: str | None
    sector: str | None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    normalized_name: str = ""


@lru_cache(maxsize=1)
def _aliases_by_ticker() -> dict[str, tuple[str, ...]]:
    out: dict[str, list[str]] = {}
    for alias, ticker in _KOREAN_ALIASES.items():
        out.setdefault(ticker, []).append(alias)
    return {k: tuple(v) for k, v in out.items()}


@lru_cache(maxsize=1)
def load_master() -> tuple[MasterEntry, ...]:
    """전체 KOSPI+KOSDAQ 종목 마스터를 반환한다(정답 데이터)."""
    aliases = _aliases_by_ticker()
    entries: list[MasterEntry] = []
    for row in _load_stocks():
        ticker = str(row["symbol"]).strip()
        name = str(row["name"]).strip()
        entries.append(
            MasterEntry(
                ticker=ticker,
                stock_name=name,
                market=row.get("market"),
                sector=row.get("sector"),
                aliases=aliases.get(ticker, ()),
                normalized_name=normalize_name(name),
            )
        )
    return tuple(entries)


def by_ticker(ticker: str) -> MasterEntry | None:
    t = (ticker or "").strip()
    for entry in load_master():
        if entry.ticker == t:
            return entry
    return None
