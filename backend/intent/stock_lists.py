"""업종·테마 소속 종목 목록 — '무엇을 사야 하나'와 분리된 '무엇이 속해 있나' 레인.

[규제 안전] CLAUDE.md는 객관적인 과거 데이터·분류 정보 표시를 허용하고, 금지하는 것은
추천·전망이다. "반도체 업종에 어떤 회사들이 있어?"는 **소속이라는 분류 사실**을 묻는
것이지 살 종목을 골라 달라는 것이 아니다 — 그런데 `STOCK_PICK` 라벨 하나가 둘을 같은
거절로 묶고 있었다(2026-08-11 커버리지 프로브: market_fact 목록 질문 2건 차단).

설계는 `stock_facts`(FR-SA-002c-9)와 같은 계약이다:

    LLM은 "어느 범위를 물었나"만 짧은 표기로 추출하고(list_scope),
    목록은 이 모듈이 정본 데이터에서 읽어 정해진 틀에 채운다.

축이 여는 것은 결정론 조회뿐이다 — 오판의 최악은 '소속 목록을 보여준다'이지 '이걸
사라고 말한다'가 아니다. 목록 정렬은 가나다순이다: 시가총액·수익률순은 객관적
데이터라도 '위에 있는 것이 더 좋다'는 암시를 만든다.

소속 정본:
  ① 시장·지수 — 코스피200은 지수 편입 캐시(kospi200-cache.json), 코스피·코스닥은
     종목 마스터의 market 필드(현재 상장 기준). "코스피 200 지수는 약 403개"처럼
     AI가 종수를 지어내던 환각(2026-08-11 실측)의 결정론 대체다
  ② 업종 — engine.universe_pit의 섹터 지도(지식그래프 SOT, 파일 폴백)
  ③ 테마 — engine.knowledge_graph.theme_listed_companies(그래프 조회만 — 검색 학습
     체인은 타지 않는다. 미등록 테마는 목록 없이 기존 안내로 강등)
"""

from __future__ import annotations

import logging
from typing import List, NamedTuple, Optional

logger = logging.getLogger(__name__)

# 표시 상한 — 목록이 수백 곳이면 채팅 버블이 스크롤 벽이 된다. 절단하는 것은
# **표시**뿐이며 총원은 항상 밝힌다(테마 유니버스 종수 상한 절단 금지와 충돌 없음 —
# 그 원칙은 백테스트 유니버스 구성에 대한 것이다).
_DISPLAY_LIMIT = 40


class Listing(NamedTuple):
    scope: str          # 정본 표기 (예: '반도체', 'HBM')
    kind: str           # '업종' | '테마'
    companies: List[tuple[str, str]]  # (이름, 종목코드) — 가나다순


def resolve_listing(term: str) -> Optional[Listing]:
    """LLM이 추출한 짧은 표기를 정본 소속 목록으로 해석한다. 실패는 None(지어내지 않는다).

    입력은 사용자 원문이 아니라 LLM 출력이다 — universe_resolver.resolve_sectors와
    같은 재배치 계약(지식 조회를 원문에서 수행하지 않는다).
    """
    if not isinstance(term, str) or not term.strip():
        return None
    term = term.strip()

    market_listing = _resolve_market_listing(term)
    if market_listing is not None:
        return market_listing
    sector_listing = _resolve_sector_listing(term)
    if sector_listing is not None:
        return sector_listing
    return _resolve_theme_listing(term)


# 시장·지수 표기 정규화 — 입력이 LLM 출력(짧은 표기)이므로 결정론 코드 소관이다.
# 공백·대소문자 변형('코스피 200'·'KOSPI200')만 흡수하는 닫힌 사전이며,
# 목록 밖 표기는 시장이 아닌 것으로 보고 업종·테마 해석으로 넘어간다.
_MARKET_KEYS = {
    "코스피200": ("kospi200", "코스피200", "지수"),
    "kospi200": ("kospi200", "코스피200", "지수"),
    "코스피": ("kospi", "코스피", "시장"),
    "kospi": ("kospi", "코스피", "시장"),
    "코스닥": ("kosdaq", "코스닥", "시장"),
    "kosdaq": ("kosdaq", "코스닥", "시장"),
}


def _resolve_market_listing(term: str) -> Optional[Listing]:
    key = term.replace(" ", "").lower()
    hit = _MARKET_KEYS.get(key)
    if hit is None:
        return None
    market_id, display, kind = hit
    try:
        from engine.universe_pit import _load_master

        master = {
            s["symbol"]: s
            for s in _load_master()
            if not s.get("delistingDate")
        }
        if market_id == "kospi200":
            symbols = _kospi200_symbols()
            # 편입 캐시에 있어도 마스터에서 상폐된 종목은 제외한다(캐시 시차 방어).
            members = [s for s in symbols if s in master]
        else:
            wanted = "KOSPI" if market_id == "kospi" else "KOSDAQ"
            members = [s for s, rec in master.items() if rec.get("market") == wanted]
        if not members:
            return None
        companies = sorted(((master[s]["name"], s) for s in members), key=lambda c: c[0])
        return Listing(scope=display, kind=kind, companies=companies)
    except Exception:  # noqa: BLE001 — 조회 실패가 대화를 깨뜨리면 안 된다
        logger.debug("시장 목록 조회 실패 | term=%s", term, exc_info=True)
        return None


def _kospi200_symbols() -> List[str]:
    """코스피200 편입 종목 — 백테스트 유니버스와 같은 캐시가 정본이다."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "data" / "kospi200-cache.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("symbols") or [])


def _resolve_sector_listing(term: str) -> Optional[Listing]:
    try:
        from engine.universe_pit import _load_master, expand_legacy_sector, filter_by_sector

        canonicals = expand_legacy_sector(term)
        if not canonicals:
            return None
        # 현재 상장 종목만 — 상폐 종목을 '속해 있다'고 보여주면 분류 사실이 아니라 오보다.
        master = {
            s["symbol"]: s["name"]
            for s in _load_master()
            if not s.get("delistingDate")
        }
        members = filter_by_sector(list(master), list(canonicals))
        if not members:
            return None
        companies = sorted(((master[s], s) for s in members), key=lambda c: c[0])
        return Listing(scope=" · ".join(canonicals), kind="업종", companies=companies)
    except Exception:  # noqa: BLE001 — 조회 실패가 대화를 깨뜨리면 안 된다
        logger.debug("업종 목록 조회 실패 | term=%s", term, exc_info=True)
        return None


def _resolve_theme_listing(term: str) -> Optional[Listing]:
    try:
        from engine.knowledge_graph import theme_listed_companies

        hit = theme_listed_companies(term)
        if not hit or not hit.get("companies"):
            return None
        companies = sorted(
            {(c["name"], c["symbol"]) for c in hit["companies"] if c.get("symbol")},
            key=lambda c: c[0],
        )
        if not companies:
            return None
        return Listing(scope=hit.get("term") or term, kind="테마", companies=companies)
    except Exception:  # noqa: BLE001
        logger.debug("테마 목록 조회 실패 | term=%s", term, exc_info=True)
        return None


def _object_particle(word: str) -> str:
    """받침 유무로 을/를을 고른다(stock_facts._topic_particle과 같은 관례)."""
    last = word[-1] if word else ""
    if not ("가" <= last <= "힣"):
        return "을(를)"
    return "을" if (ord(last) - ord("가")) % 28 else "를"


def listing_answer(listing: Listing, count_only: bool = False) -> str:
    """소속 사실 문장. **LLM이 짓지 않는다** — 정본 목록을 정해진 틀에 채운다.

    [규제 안전] 소속이라는 분류 사실에서 끝난다. 어느 회사가 유망한지·주도주가
    무엇인지 같은 선별·평가는 붙이지 않으며, 정렬은 가나다순이다(순위 암시 방지).

    count_only=True('몇 종목?'처럼 종수만 물은 발화)면 회사명 나열을 생략한다 —
    1,800곳짜리 시장에 40개 이름을 붙이면 답이 소음이 된다. 사실은 같고 표시만 다르다.
    """
    total = len(listing.companies)
    lead = (
        f"'{listing.scope}' {listing.kind}에 속한 상장사는 현재 총 {total}곳입니다"
    )
    if count_only:
        body = f"{lead}. (플랫폼 보유 데이터 기준)\n\n"
    else:
        shown = listing.companies[:_DISPLAY_LIMIT]
        names = ", ".join(f"{name}({symbol})" for name, symbol in shown)
        more = f" 외 {total - len(shown)}곳" if total > len(shown) else ""
        body = f"{lead} (가나다순).\n\n{names}{more}\n\n"
    subject = "이 값은" if count_only else "이 목록은"
    return (
        body
        + f"{subject} {listing.kind} 소속이라는 분류 정보를 그대로 보여드리는 것이며, "
        "특정 종목의 매수 추천이 아닙니다. "
        f"이 {listing.kind}{_object_particle(listing.kind)} 대상으로 하는 전략을 "
        "만들어 과거 데이터에서 검증해보실 수 있어요."
    )
