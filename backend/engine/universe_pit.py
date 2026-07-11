"""
Point-in-time (survivorship-bias-free) universe resolution.

Reads data/stock-master.json (built by scripts/build_stock_master.py) and answers:
"for a backtest window [start, end], which symbols were alive and priceable —
including names that have since delisted?"

This replaces the legacy resolution that drew only from the *current* listed set
(korea-stocks.json / kospi200-cache.json), which silently excluded every stock
that delisted during the window and thereby inflated returns / understated risk.

Membership rule (grounded in real local price coverage):
    market matches AND hasOhlcv AND dataStart <= end AND dataEnd >= start

"대형주" / KOSPI200 is treated as a point-in-time top-N-by-market-cap subset of the
alive KOSPI names; the hard top-N gate is applied in the backtest engine (it needs
daily close prices), while this module supplies the alive-KOSPI superset and the
static share counts used to compute market cap.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_MASTER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock-master.json"
_KOREA_STOCKS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "korea-stocks.json"

# When a backtest has no explicit start (period=FULL), bound the lower edge here.
_DEFAULT_START_FLOOR = "2015-01-01"

# "대형주" / KOSPI200 point-in-time size cutoff.
LARGE_CAP_TOP_N = 200


@lru_cache(maxsize=1)
def _load_master() -> list[dict]:
    if not _MASTER_PATH.exists():
        return []
    return json.loads(_MASTER_PATH.read_text(encoding="utf-8")).get("stocks", [])


def reload_master() -> None:
    """Drop the cached master (call after regenerating the file)."""
    _load_master.cache_clear()


def parse_universe_markets(universe_id: Optional[str]) -> tuple[list[str], bool]:
    """universe_id ("kospi", "kospi200", "kosdaq_kospi", ...) -> (markets, is_large_cap).

    Returns ([], False) when the id is not a recognized market universe (e.g. a
    custom symbol set), signalling the caller to leave the symbol list untouched.
    """
    if not universe_id:
        return [], False
    tokens = {t for t in universe_id.lower().split("_") if t}
    if not tokens or not tokens <= {"kospi", "kosdaq", "kospi200"}:
        return [], False
    is_large_cap = "kospi200" in tokens
    markets: list[str] = []
    if "kospi" in tokens or "kospi200" in tokens:
        markets.append("KOSPI")
    if "kosdaq" in tokens:
        markets.append("KOSDAQ")
    return markets, is_large_cap


def _alive(stock: dict, start: str, end: str) -> bool:
    if not stock.get("hasOhlcv"):
        return False
    ds, de = stock.get("dataStart"), stock.get("dataEnd")
    if not ds or not de:
        return False
    return ds <= end and de >= start


def resolve_symbols(universe_id: Optional[str], start: Optional[str], end: str) -> Optional[list[str]]:
    """As-of symbol list for the window, or None if universe_id is not a market universe.

    For a large-cap (KOSPI200) universe this returns the alive-KOSPI superset; the
    engine then applies the point-in-time top-N market-cap gate.
    """
    markets, _ = parse_universe_markets(universe_id)
    if not markets:
        return None
    lo = start or _DEFAULT_START_FLOOR
    target = set(markets)
    symbols = [
        s["symbol"] for s in _load_master()
        if s.get("market") in target and _alive(s, lo, end)
    ]
    return sorted(symbols)


def get_shares(symbols: list[str]) -> dict[str, float]:
    """symbol -> listed shares (static, from master) for market-cap ranking."""
    wanted = set(symbols)
    out: dict[str, float] = {}
    for s in _load_master():
        if s["symbol"] in wanted and s.get("shares"):
            out[s["symbol"]] = float(s["shares"])
    return out


# ── 섹터 유니버스 ────────────────────────────────────────────────────────────
# 섹터 분류의 SOT는 korea-stocks.json의 sector 필드(sector_mapper 재분류 산출물)다.
# 주의: PIT 마스터(stock-master.json, 상장폐지 포함)에는 섹터가 없어, 섹터 필터는
# '현재 상장 종목' 기준 근사다 — 기간 중 상폐된 종목이 빠지므로 엔진이 경고를 남긴다.

# korea-stocks.json sector 필드의 전체 값(38개). 파서·프롬프트·검증이 공유하는 정본.
CANONICAL_SECTORS: tuple[str, ...] = (
    "IT 하드웨어", "가구/인테리어", "건설", "교육", "기계/장비", "기타 서비스",
    "기타 제조업", "디스플레이/부품", "목재", "미디어/엔터", "바이오/제약", "반도체",
    "반도체 소재", "부동산", "사료/축산", "소프트웨어/플랫폼", "수산", "수산가공",
    "시멘트", "식품/음료", "에너지/원자력", "욕실", "우주항공/방산", "운송/물류",
    "유통/상사", "은행/금융지주", "의료기기", "이차전지", "자동차", "자동차부품",
    "조선/해운", "종이", "증권/보험", "지주회사", "철강/금속", "통신/유틸리티",
    "화장품/패션", "화학",
)

# 사용자가 흔히 말하는 업종 표현 → 정본 섹터명. 모호하지 않은 통칭만 넣는다
# (핵심만 결정적으로 잡고 긴 꼬리는 LLM에 위임 — feedback_nl_parser_hybrid).
_SECTOR_SYNONYMS: dict[str, str] = {
    "2차전지": "이차전지", "배터리": "이차전지",
    "제약": "바이오/제약", "바이오": "바이오/제약", "바이오제약": "바이오/제약",
    "반도체소재": "반도체 소재",
    "it하드웨어": "IT 하드웨어",
    "소프트웨어": "소프트웨어/플랫폼", "플랫폼": "소프트웨어/플랫폼", "인터넷": "소프트웨어/플랫폼",
    "은행": "은행/금융지주", "금융지주": "은행/금융지주",
    "증권": "증권/보험", "보험": "증권/보험",
    "화장품": "화장품/패션", "패션": "화장품/패션", "의류": "화장품/패션",
    "식품": "식품/음료", "음료": "식품/음료",
    "엔터": "미디어/엔터", "엔터테인먼트": "미디어/엔터", "미디어": "미디어/엔터",
    "통신": "통신/유틸리티",
    "에너지": "에너지/원자력", "원자력": "에너지/원자력",
    "조선": "조선/해운", "해운": "조선/해운",
    "철강": "철강/금속",
    "방산": "우주항공/방산", "우주항공": "우주항공/방산", "항공우주": "우주항공/방산",
    "기계": "기계/장비",
    "디스플레이": "디스플레이/부품",
    "리츠": "부동산",
    "물류": "운송/물류", "운송": "운송/물류",
    "유통": "유통/상사",
    "제지": "종이",
    "완성차": "자동차",
    "지주": "지주회사",
    "헬스케어": "의료기기",
    # 'AI 관련주'는 이 분류 체계에서 소프트웨어/플랫폼에 속한다(sector_mapper MAPPING_RULES와 동일).
    "ai": "소프트웨어/플랫폼",
    "인공지능": "소프트웨어/플랫폼",
}


def _sector_key(text: str) -> str:
    """비교용 키 — 공백 제거·소문자화('반도체 소재'='반도체소재')."""
    return (text or "").replace(" ", "").lower()


_CANONICAL_BY_KEY = {_sector_key(s): s for s in CANONICAL_SECTORS}


def normalize_sector(raw: Optional[str]) -> Optional[str]:
    """사용자/LLM이 준 업종 표현을 정본 섹터명으로 정규화한다. 못 찾으면 None."""
    if not raw:
        return None
    key = _sector_key(raw)
    if key in _CANONICAL_BY_KEY:
        return _CANONICAL_BY_KEY[key]
    return _SECTOR_SYNONYMS.get(key)


@lru_cache(maxsize=1)
def _load_sector_map() -> dict[str, str]:
    if not _KOREA_STOCKS_PATH.exists():
        return {}
    stocks = json.loads(_KOREA_STOCKS_PATH.read_text(encoding="utf-8"))
    return {s["symbol"]: s["sector"] for s in stocks if s.get("symbol") and s.get("sector")}


def filter_by_sector(symbols: list[str], sector: str) -> list[str]:
    """심볼 목록을 정본 섹터명으로 필터링한다(섹터 미상 종목은 제외)."""
    canonical = normalize_sector(sector)
    if canonical is None:
        return []
    smap = _load_sector_map()
    return [s for s in symbols if smap.get(s) == canonical]


def get_delisting_dates(symbols: list[str]) -> dict[str, str]:
    """symbol -> delistingDate, only for names that actually delisted.

    Lets the engine label a forced exit at a delisted name's last trading day as
    "상장폐지" rather than the generic "데이터 종료".
    """
    wanted = set(symbols)
    return {
        s["symbol"]: s["delistingDate"]
        for s in _load_master()
        if s["symbol"] in wanted and s.get("delistingDate")
    }
