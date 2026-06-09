"""
종목명 ↔ 종목코드 해석기.

`data/korea-stocks.json`(symbol/name/market/sector/industry)을 1회 로드해
사용자 입력 문자열에서 종목을 식별한다. 대표 해외 종목은 작은 별칭 맵으로만
인식하되 코드는 티커로 둔다(국내 parquet 데이터가 없어 분석 단계에서
INSUFFICIENT_DATA로 처리된다).

새 의존성 없이 표준 라이브러리만 사용한다(KISS).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_STOCKS_JSON_PATH = Path(__file__).resolve().parents[2] / "data" / "korea-stocks.json"

# 분석 데이터(parquet)는 없지만 intent 분류에서 '종목 질문'으로 인식해야 하는 대표 해외 종목.
_OVERSEAS_ALIASES: dict[str, str] = {
    "엔비디아": "NVDA",
    "nvidia": "NVDA",
    "애플": "AAPL",
    "apple": "AAPL",
    "테슬라": "TSLA",
    "tesla": "TSLA",
    "마이크로소프트": "MSFT",
    "구글": "GOOGL",
    "아마존": "AMZN",
    "메타": "META",
}


@dataclass(frozen=True)
class StockRef:
    symbol: str
    name: str
    market: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    overseas: bool = False


@lru_cache(maxsize=1)
def _load_stocks() -> list[dict]:
    try:
        with _STOCKS_JSON_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return [row for row in data if isinstance(row, dict) and row.get("symbol") and row.get("name")]
    except Exception:
        logger.exception("korea-stocks.json 로드 실패: %s", _STOCKS_JSON_PATH)
        return []


@lru_cache(maxsize=1)
def _name_index() -> tuple[tuple[str, dict], ...]:
    """이름 길이 내림차순으로 정렬된 (name, row) 목록 — 가장 긴 이름이 우선 매칭된다."""
    rows = _load_stocks()
    indexed = [(str(row["name"]).strip(), row) for row in rows if len(str(row["name"]).strip()) >= 2]
    indexed.sort(key=lambda item: len(item[0]), reverse=True)
    return tuple(indexed)


@lru_cache(maxsize=1)
def _symbol_index() -> dict[str, dict]:
    return {str(row["symbol"]).strip(): row for row in _load_stocks()}


def resolve_by_symbol(symbol: str) -> Optional[StockRef]:
    if not symbol:
        return None
    row = _symbol_index().get(symbol.strip())
    if row is None:
        # 해외 티커(별칭 맵의 값)도 허용한다.
        if symbol.strip().upper() in set(_OVERSEAS_ALIASES.values()):
            return StockRef(symbol=symbol.strip().upper(), name=symbol.strip().upper(), overseas=True)
        return None
    return StockRef(
        symbol=str(row["symbol"]).strip(),
        name=str(row["name"]).strip(),
        market=row.get("market"),
        sector=row.get("sector"),
        industry=row.get("industry"),
    )


def _is_valid_boundary(text: str, pos: int, is_after: bool) -> bool:
    """주어진 위치가 종목명의 경계인지 검사한다.
    - is_after=False: pos 이전 문자가 경계 조건 만족?
    - is_after=True: pos 이후 문자가 경계 조건 만족?
    경계 조건: 문자가 없거나, 한글 글자가 아니거나, 조사/기호
    """
    if is_after:
        if pos >= len(text):
            return True
        ch = text[pos]
        # 한글 글자가 아니면 경계 (띄어쓰기, 기호 등)
        if not ('가' <= ch <= '힯'):  # 가-힣 범위만 체크
            return True
        # 한글 글자이더라도 조사(와, 은, 는, 이, 가, 을, 를, 도 등)면 경계로 본다
        if ch in '와을를이가도은는':
            return True
        return False
    else:
        if pos < 0:
            return True
        ch = text[pos]
        if not ('가' <= ch <= '힯'):
            return True
        return False


def find_in_text(text: str) -> list[StockRef]:
    """입력 문자열에서 등장하는 종목을 식별한다(가장 긴 이름 우선, 중복 제거)."""
    if not text:
        return []
    found: list[StockRef] = []
    seen: set[str] = set()
    remaining = text

    # 1) 국내 종목명(가장 긴 이름부터) — 단어 경계를 고려해 정확히 매칭 (대소문자 무시)
    remaining_lower = text.lower()
    for name, row in _name_index():
        # 대소문자 무시 substring 검색
        name_lower = name.lower()
        idx = 0
        while True:
            idx = remaining_lower.find(name_lower, idx)
            if idx == -1:
                break
            # 앞 경계 검사 (원본 텍스트 기준)
            before_valid = _is_valid_boundary(text, idx - 1, is_after=False)
            # 뒤 경계 검사 (원본 텍스트 기준)
            after_valid = _is_valid_boundary(text, idx + len(name), is_after=True)

            if before_valid and after_valid and row["symbol"] not in seen:
                found.append(
                    StockRef(
                        symbol=str(row["symbol"]).strip(),
                        name=name,
                        market=row.get("market"),
                        sector=row.get("sector"),
                        industry=row.get("industry"),
                    )
                )
                seen.add(row["symbol"])
                # 매칭된 부분만 공백으로 치환 (remaining_lower와 text 동시 갱신)
                remaining_lower = remaining_lower[:idx] + " " * len(name) + remaining_lower[idx + len(name):]
                text = text[:idx] + " " * len(name) + text[idx + len(name):]
                break  # 같은 종목명은 한 번만 추가
            idx += 1

    # 2) 6자리 종목코드 직접 입력
    for code in re.findall(r"\b\d{6}\b", remaining):
        if code not in seen and code in _symbol_index():
            ref = resolve_by_symbol(code)
            if ref:
                found.append(ref)
                seen.add(code)

    # 3) 대표 해외 종목 별칭
    lowered = text.lower()
    for alias, ticker in _OVERSEAS_ALIASES.items():
        if alias in lowered and ticker not in seen:
            found.append(StockRef(symbol=ticker, name=alias, overseas=True))
            seen.add(ticker)

    return found
