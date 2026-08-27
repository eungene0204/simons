"""미국 업종 분류 registry — GICS 섹터·산업 정본에서 종목 명부를 만든다.

**테마와 다른 축이다.** 두 축의 차이가 이 모듈이 따로 있는 이유다:

| | 분류(여기) | 테마(us_theme_catalog·us_term_grounding) |
|---|---|---|
| 정체 | 분류 체계의 **정본** — 모든 종목이 하나에 속한다 | 근거로 **관측된 소속 집합** |
| 근거 | 있음/없음이 아니라 정의 | 공시·ETF 보유 공시 등 증거가 필요 |
| 시점 | 현행 분류(이력 없음 — 소비자가 고지할 몫) | 소속 최초 관측일(first_known_date)을 함께 싣는다 |
| 해석 | 표기 정확 일치(결정론, LLM 불개입) | LLM 소속 심사 + 확정 게이트 |

입력은 **LLM이 뽑은 짧은 표현**이다(사용자 원문 아님 — 자연어 해석 구조 원칙 § 3-2).
정확 일치만 본다 — 부분 매칭은 오폭원("Bank"가 'Banks - Regional'에 닿는 일).

**표기 변종 병합**: 정본(us-stocks.json)의 산업 라벨에는 같은 업종의 표기 변종이 섞여
있다(실측 2026-08-27: 'Banks - Regional' 312 / 'Regional Banks' 6처럼 토큰이 같은 묶음
7건 + 약어 변종). 병합하지 않으면 같은 업종이 갈라져 명부에서 종목이 새어나간다.
토큰 다중집합이 같은 라벨은 결정론으로 병합하고(다수 라벨이 정본), 토큰이 다른 약어
변종만 큐레이션 별칭표(_LABEL_ALIASES)로 잇는다.

**엔진 필터가 아니라 명부 전개다**: 미국 업종 필터는 아직 백테스트 레인이 지원하지
않으므로(PROJECT_PLAN 잔여), 여기서는 분류에 속한 종목을 '지정 종목'으로 전개한다 —
추정이 섞이지 않은 정본 명부라 전개해도 조용한 확정이 아니다. 필터로 승격하는 것은
별건이다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from engine.console_logging import console_logger

logger = console_logger("us_industry_registry", "US-GICS")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_STOCKS_PATH = _BASE_DIR / "data" / "us-stocks.json"
_OHLCV_DIR = _BASE_DIR / "data" / "ohlcv-us"

# 토큰이 달라 자동 병합되지 않는 약어·개명 변종(큐레이션) — 값이 정본 라벨.
# GICS 개명('Airlines'→'Passenger Airlines')과 약어 표기가 여기 들어온다.
_LABEL_ALIASES = {
    "passenger airlines": "Airlines",
    "oil & gas exploration & production": "Oil & Gas E&P",
}

# 분류 명부가 지나치게 커지면 유니버스라기보다 시장 전체다 — 지수 유니버스로 안내하는
# 편이 정직하다(실측: Banks - Regional 312곳, Biotechnology 594곳까지는 명부로 의미가
# 있지만 섹터 단위 Financials 1,380곳은 KOSPI 전체를 '업종'이라 부르는 것과 같다).
_MAX_MEMBERS = 600


# 큐레이션 별칭(별칭 → 정본 라벨) — 분류 정본에 없는 표기를 잇는다. 대부분 한글 통칭이다.
# 출처: 시드 지식그래프에 있던 **산업명 중복 테마 11종**의 별칭을 이관한 것(2026-08-27).
# 그 테마들은 분류의 표본(항공사 4곳 vs 분류 18곳, 외식 5곳 vs 54곳)이라 삭제했고,
# 별칭만 여기로 옮겨 어느 표기로 부르든 같은 축(분류)에 닿게 했다 — 영문은 분류로,
# 한글은 시드 테마로 갈리던 상태가 "한 단어가 두 축에 걸치는" 문제였다.
_EXTRA_ALIASES = {
    "Semiconductor industry": "Semiconductors",
    "구리": "Copper",
    "구리 관련주": "Copper",
    "데이터센터 리츠": "Data Center REITs",
    "데이터센터 임대": "Data Center REITs",
    "레스토랑": "Restaurants",
    "반도체": "Semiconductors",
    "반도체 산업": "Semiconductors",
    "산업가스": "Industrial Gases",
    "산업가스주": "Industrial Gases",
    "외식": "Restaurants",
    "외식주": "Restaurants",
    "의료기기": "Medical Devices",
    "의료기기주": "Medical Devices",
    "철강": "Steel",
    "철강주": "Steel",
    "철도": "Railroads",
    "철도주": "Railroads",
    "태양광": "Solar",
    "태양광 에너지": "Solar",
    "태양광주": "Solar",
    "폐기물": "Waste Management",
    "폐기물 처리": "Waste Management",
    "폐기물 처리주": "Waste Management",
    "항공사": "Airlines",
    "항공주": "Airlines",
}

def _norm(text: str) -> str:
    """조회 정규화 키 — 공백 제거·소문자 + **'&'와 'and'를 같은 것으로 본다**.

    _token_key는 이미 'and'를 무시하는데 조회 키는 '&'를 그대로 둬서, 정본
    'Aerospace & Defense'와 입력 'aerospace and defense'가 갈렸다(2026-08-27 실측).
    그 결과 **GICS 산업명이 분류 축 가드를 빠져나가 테마로 학습됐고**(양방향 축 가드가
    무력화), /us "On ITA, the US aerospace and defense ETF …"가 ETF 상품 대신 방산주
    10곳 포트폴리오로 조립됐다. 표기 변종 판정이지 의미 해석이 아니다."""
    return (text or "").strip().lower().replace("&", "and").replace(" ", "")


def _token_key(label: str) -> tuple:
    """토큰 다중집합 — 순서·구분자·'and'('&' 포함)를 무시한 표기 동일성 판정."""
    return tuple(sorted(
        t for t in re.split(r"[^a-z0-9]+", (label or "").replace("&", " and ").lower())
        if t and t != "and"
    ))


class USIndustryRegistry:
    """읽기 전용 분류 뷰 — 별칭(정본 라벨·변종·한글 섹터명) → 종목 명부."""

    def __init__(self, index: dict[str, str], members: dict[str, list[str]]):
        self._index = index      # 정규화 별칭 → 정본 라벨
        self._members = members  # 정본 라벨 → 티커 목록

    def label_of(self, term: str) -> Optional[str]:
        """이 표현이 분류인가 — 정본 라벨 | None. 명부 크기와 무관한 **축 판정**이다.

        단수·복수 표기는 같은 분류로 본다("airline"→'Airlines') — LLM이 뽑은 표현의
        표기 변형일 뿐 다른 업종이 아니다. 정확 일치 기준은 그대로다(부분 매칭 없음)."""
        key = _norm(term)
        for variant in (key, f"{key}s", key[:-1] if key.endswith("s") else key):
            label = self._index.get(variant)
            if label is not None:
                return label
        return None

    def resolve(self, term: str) -> Optional[tuple[str, list[str]]]:
        """분류 명부 전개 — 라벨이 맞고 명부가 과대하지 않을 때만 (라벨, 티커)."""
        label = self.label_of(term)
        if label is None:
            return None
        symbols = self._members.get(label) or []
        if not symbols or len(symbols) > _MAX_MEMBERS:
            return None
        return label, symbols

    def member_count(self, label: str) -> int:
        return len(self._members.get(label) or [])

    @property
    def labels(self) -> list[str]:
        return sorted(self._members)


_CACHE: Optional[tuple[float, USIndustryRegistry]] = None


def _build() -> USIndustryRegistry:
    from engine.us_knowledge_graph import _GICS_SECTOR_KR  # 섹터 한글 표기(정본 한 벌)

    try:
        raw = json.loads(_STOCKS_PATH.read_text())
    except (OSError, ValueError):
        return USIndustryRegistry({}, {})
    stocks = raw.get("stocks", raw) if isinstance(raw, dict) else raw
    have = {p.split(".")[0] for p in os.listdir(_OHLCV_DIR)} if _OHLCV_DIR.exists() else set()

    # 1) 산업 라벨 수집 — 파케이 보유 종목만(백테스트할 수 없는 종목은 명부에 싣지 않는다)
    industry_rows: dict[str, list[str]] = {}
    sector_rows: dict[str, list[str]] = {}
    for s in stocks if isinstance(stocks, list) else []:
        symbol = s.get("symbol")
        if not symbol or (have and symbol not in have):
            continue
        industry = (s.get("industry") or "").strip()
        sector = (s.get("sector") or "").strip()
        if industry:
            industry_rows.setdefault(industry, []).append(symbol)
        if sector:
            sector_rows.setdefault(sector, []).append(symbol)

    # 2) 표기 변종 병합 — 토큰이 같으면 같은 업종, 종목 수가 많은 라벨이 정본
    canonical_of: dict[str, str] = {}
    by_token: dict[tuple, list[str]] = {}
    for label in industry_rows:
        by_token.setdefault(_token_key(label), []).append(label)
    for labels in by_token.values():
        winner = max(labels, key=lambda name: (len(industry_rows[name]), name))
        for label in labels:
            canonical_of[label] = winner
    for variant, canonical in _LABEL_ALIASES.items():
        for label in list(industry_rows):
            if _norm(label) == _norm(variant) and canonical in industry_rows:
                canonical_of[label] = canonical

    members: dict[str, list[str]] = {}
    for label, symbols in industry_rows.items():
        target = canonical_of.get(label, label)
        merged = members.setdefault(target, [])
        merged.extend(s for s in symbols if s not in merged)
    for label, symbols in sector_rows.items():
        members.setdefault(label, sorted(symbols))

    # 3) 별칭 인덱스 — 정본 라벨·병합된 변종·섹터 한글 표기. 정확 일치 전용.
    index: dict[str, str] = {}
    for label in members:
        index.setdefault(_norm(label), label)
    for variant, canonical in canonical_of.items():
        if canonical in members:
            index.setdefault(_norm(variant), canonical)
    for sector, korean in _GICS_SECTOR_KR.items():
        if sector in members:
            index.setdefault(_norm(korean), sector)
    for alias, canonical in _EXTRA_ALIASES.items():
        if canonical in members:
            index.setdefault(_norm(alias), canonical)

    logger.info("US 분류 registry: 산업 %d종(변종 병합 %d건)·섹터 %d종·별칭 %d개",
                len([m for m in members if m not in sector_rows]),
                sum(1 for k, v in canonical_of.items() if k != v),
                len(sector_rows), len(index))
    return USIndustryRegistry(index, members)


def get_registry() -> USIndustryRegistry:
    """분류 registry(mtime 캐시) — 정본 파일이 바뀌면 다음 조회에서 재구축."""
    global _CACHE
    try:
        mtime = _STOCKS_PATH.stat().st_mtime
    except OSError:
        return USIndustryRegistry({}, {})
    if _CACHE is None or _CACHE[0] != mtime:
        _CACHE = (mtime, _build())
    return _CACHE[1]


def _candidate_terms(term: str) -> list[str]:
    """한정어를 벗긴 표기 후보 — 테마 조회와 같은 규칙(축이 갈려도 정규화는 한 벌)."""
    from engine.us_knowledge_graph import theme_term_candidates

    return theme_term_candidates(term)


def classification_label(term: Optional[str]) -> Optional[str]:
    """이 표현이 분류 축인가 — 정본 라벨 | None(명부 크기와 무관한 축 판정)."""
    if not term or not isinstance(term, str):
        return None
    registry = get_registry()
    for candidate in _candidate_terms(term):
        label = registry.label_of(candidate)
        if label is not None:
            return label
    return None


def industry_members(label: Optional[str]) -> list[str]:
    """정본 라벨의 전체 종목 명부 — **필터용이라 크기 상한을 두지 않는다**.

    명부 전개(resolve_us_industry)는 지정 종목 목록을 만들기 때문에 과대 분류를 막아야
    했지만, 필터는 유니버스에 교집합을 적용하는 것이라 섹터 단위(1,000곳)도 정상이다."""
    if not label:
        return []
    registry = get_registry()
    return list(registry._members.get(label) or [])


def resolve_us_industry(term: Optional[str]) -> Optional[tuple[str, list[str]]]:
    """분류 표현 → (정본 라벨, 종목 명부). 분류 밖이거나 명부가 과대하면 None.

    **과대(None)와 분류 아님(None)을 구분해야 하는 호출부는 classification_label을
    함께 본다** — 섹터처럼 넓은 분류를 '분류 아님'으로 흘리면 테마 학습이 섹터어를
    공시에서 배우려 드는 엉뚱한 경로가 열린다."""
    if not term or not isinstance(term, str):
        return None
    registry = get_registry()
    for candidate in _candidate_terms(term):
        hit = registry.resolve(candidate)
        if hit is not None:
            return hit
    return None
