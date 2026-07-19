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
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from engine.sector_mapper import MAPPING_RULES, NL_SAFE_TERMS

_MASTER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock-master.json"
_KOREA_STOCKS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "korea-stocks.json"
_ETF_MASTER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "etf-master.json"

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
    _load_sector_map.cache_clear()
    _load_etf_master.cache_clear()
    _etf_symbol_set.cache_clear()


# ── ETF 유니버스 ─────────────────────────────────────────────────────────────
# ETF는 개별 주식과 분리된 독립 유니버스다(universe_id="etf"). 주식 유니버스와 절대
# 혼합하지 않으며, 기업 재무지표(PER·PBR 등)는 적용되지 않는다(universe_capabilities).
# 마스터는 scripts/build_etf_master.py가 FDR ETF/KR 목록 ∩ 로컬 OHLCV로 생성한다.
# 한계: 현재 상장 ETF만 담는다(상폐 ETF 미포함) — 엔진이 생존 편향 경고를 남긴다.


@lru_cache(maxsize=1)
def _load_etf_master() -> list[dict]:
    if not _ETF_MASTER_PATH.exists():
        return []
    return json.loads(_ETF_MASTER_PATH.read_text(encoding="utf-8")).get("etfs", [])


def is_etf_universe(universe_id: Optional[str]) -> bool:
    """universe_id가 ETF 유니버스인지 판정한다."""
    return bool(universe_id) and universe_id.strip().lower() == "etf"


@lru_cache(maxsize=1)
def _etf_symbol_set() -> frozenset[str]:
    return frozenset(e["symbol"] for e in _load_etf_master())


def is_etf_symbol(symbol: str) -> bool:
    """이 심볼이 ETF 마스터(상장·상폐 포함)에 속하는가.

    DataLoader가 종목당 무조건 시도하던 재무 enrichment(ROE 등)를 ETF에는 건너뛰기
    위한 판정 — ETF는 기업 재무제표가 없어 KIS 재무비율 API가 항상 빈 응답/오류만
    반환하므로, 판정 없이는 매 ETF 백테스트마다 헛된 API 호출과 로그 소음이 발생한다.
    """
    return symbol in _etf_symbol_set()


def resolve_etf_symbols(start: Optional[str], end: str) -> list[str]:
    """백테스트 창에서 가격 데이터가 존재하는 ETF 심볼 목록(as-of)."""
    lo = start or _DEFAULT_START_FLOOR
    return sorted(
        e["symbol"] for e in _load_etf_master() if _alive(e, lo, end)
    )


def etf_master_includes_delisted() -> bool:
    """ETF 마스터에 상폐 ETF가 백필돼 있는가 — 없으면 엔진이 생존 편향을 경고한다."""
    return any(e.get("delistingDate") for e in _load_etf_master())


def etf_name_map(symbols: Optional[list[str]] = None) -> dict[str, str]:
    """symbol -> ETF 이름 (symbols=None이면 전체)."""
    wanted = set(symbols) if symbols is not None else None
    return {
        e["symbol"]: e["name"]
        for e in _load_etf_master()
        if wanted is None or e["symbol"] in wanted
    }


def _etf_key(text: str) -> str:
    return (text or "").replace(" ", "").lower()


def filter_etf_by_theme(symbols: list[str], theme: str) -> list[str]:
    """ETF 심볼을 테마/이름 키워드로 필터링한다.

    정확한 상품명 일치("KODEX 200")가 있으면 그 종목만, 없으면 이름에 키워드가
    포함된 ETF 전체("반도체" → 반도체 ETF들)를 반환한다. 매칭 없으면 빈 리스트 —
    호출부가 전체 유니버스 유지 + 안내로 폴백한다(조용한 왜곡 방지).
    """
    key = _etf_key(theme)
    if not key:
        return []
    names = etf_name_map(symbols)
    exact = [s for s, n in names.items() if _etf_key(n) == key]
    if exact:
        return sorted(exact)
    return sorted(s for s, n in names.items() if key in _etf_key(n))


def extract_etf_theme(user_input: str) -> Optional[str]:
    """'ETF' 직전 토큰에서 테마/상품명 키워드를 자기검증 방식으로 추출한다.

    어휘집을 유지하는 대신, 후보 접미사가 실제 ETF 마스터 이름과 매칭되는지로
    유효성을 판정한다 — "미국 ETF"→'미국'(매칭 다수), "사는 ETF"→매칭 0이라 None.
    상품명 전체 매칭("KODEX 200")이 있으면 그것을 우선한다.
    """
    text = (user_input or "").lower()
    # ① 상품명 전체 매칭 — 입력에 마스터 이름이 통째로 들어 있으면 가장 긴 것을 채택.
    compact_input = _etf_key(text)
    best_name: Optional[str] = None
    for e in _load_etf_master():
        nk = _etf_key(e["name"])
        if len(nk) >= 5 and nk in compact_input:
            if best_name is None or len(nk) > len(_etf_key(best_name)):
                best_name = e["name"]
    if best_name:
        return best_name
    # ② 'ETF' 직전 토큰의 접미사 중 마스터 이름과 매칭되는 가장 긴 것.
    m = re.search(r"([가-힣a-z0-9&.\-]+)\s*(?:etf|이티에프)", text)
    if not m:
        return None
    token = m.group(1)
    all_names = [_etf_key(e["name"]) for e in _load_etf_master()]
    for k in range(len(token)):
        candidate = token[k:]
        if len(candidate) < 2:
            break
        ck = _etf_key(candidate)
        if any(ck in n for n in all_names):
            return candidate
    return None


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
# 상폐 종목은 PIT 마스터(stock-master.json)의 sector 백필(FDR KRX-DELISTING 업종명을
# 같은 매퍼로 분류 — scripts/backfill_delisted_sectors.py / build_stock_master.py)로
# 커버한다. 그래도 업종 미상으로 남는 종목은 필터에서 빠지므로, 엔진은 그런 종목이
# 실제로 있을 때만 생존 편향 경고를 남긴다(sector_unknown_symbols).

# korea-stocks.json sector 필드의 전체 값(39개). 파서·프롬프트·검증이 공유하는 정본.
# '로봇'(2026-07-13 신설)은 KSIC 공식 분류에 없어 사명(로봇/로보틱스) 기준으로 분류된
# 독립 섹터다(sector_mapper.MAPPING_RULES["로봇"] 참조).
CANONICAL_SECTORS: tuple[str, ...] = (
    "IT 하드웨어", "가구/인테리어", "건설", "교육", "기계/장비", "기타 서비스",
    "기타 제조업", "디스플레이/부품", "로봇", "목재", "미디어/엔터", "바이오/제약",
    "반도체", "반도체 소재", "부동산", "사료/축산", "소프트웨어/플랫폼", "수산",
    "수산가공", "시멘트", "식품/음료", "에너지/원자력", "욕실", "우주항공/방산",
    "운송/물류", "유통/상사", "은행/금융지주", "의료기기", "이차전지", "자동차",
    "자동차부품", "조선/해운", "종이", "증권/보험", "지주회사", "철강/금속",
    "통신/유틸리티", "화장품/패션", "화학",
)

# 사용자 통칭 → 정본 섹터명 '오버라이드'. 여기에는 MAPPING_RULES(산업분류 어휘)에 없거나
# 그와 다르게 불러야 하는 '사용자 전용 통칭'만 손으로 넣는다(2차전지·리츠·AI 등). MAPPING_RULES에
# 이미 있는 모호하지 않은 산업어(로봇·태양광 등)는 아래 _derive_mapper_nl_synonyms가 자동
# 파생하므로 여기 중복 기입하지 않는다 — 정본을 손으로 두 번 적지 않아 두 어휘집이 어긋날 수 없다.
# 키는 _sector_key 형태(공백 제거·소문자)로 적는다. 모호하지 않은 통칭만(긴 꼬리는 LLM 위임).
_SECTOR_SYNONYM_OVERRIDES: dict[str, str] = {
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
    # '로봇'·'로보틱스'는 MAPPING_RULES 파생(NL_SAFE_TERMS)으로 자동 인식 — 여기 중복 기입 금지.
    "기계": "기계/장비", "기계장비": "기계/장비",
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


# LLM 프롬프트용 업종 주석 — 이름만으로는 분류 관례를 오해하기 쉬운 업종에만 붙인다.
# 실측 사고(2026-07-12): '전력설비 관련주'를 LLM이 이름 연상('전력→유틸리티')으로
# 통신/유틸리티(실제로는 통신사·한전 등 사업자 25종목)에 매핑 — 변압기·전력기기 제조사는
# 이 분류 체계에서 에너지/원자력, 전선 제조는 IT 하드웨어에 속한다.
_SECTOR_LLM_GLOSSES: dict[str, str] = {
    "통신/유틸리티": "통신사와 한국전력 등 전력·가스 판매 사업자만. 설비 제조는 아님",
    "에너지/원자력": "발전·원전 + 변압기·전력설비 등 전력기기 제조 포함",
    "IT 하드웨어": "전자부품·전선 제조 포함",
    "로봇": "로봇 전문기업(산업용·협동·서비스 로봇). 일반 자동화 설비·공작기계는 기계/장비",
}


def sectors_for_llm_prompt() -> str:
    """LLM 매핑 프롬프트용 지원 업종 목록 — 혼동되기 쉬운 업종엔 짧은 관례 주석을 붙인다."""
    return ", ".join(
        f"{s}({_SECTOR_LLM_GLOSSES[s]})" if s in _SECTOR_LLM_GLOSSES else s
        for s in CANONICAL_SECTORS
    )


def _sector_key(text: str) -> str:
    """비교용 키 — 공백 제거·소문자화('반도체 소재'='반도체소재')."""
    return (text or "").replace(" ", "").lower()


_CANONICAL_BY_KEY = {_sector_key(s): s for s in CANONICAL_SECTORS}


def _derive_mapper_nl_synonyms() -> dict[str, str]:
    """MAPPING_RULES(산업분류 어휘)에서 NL_SAFE_TERMS로 opt-in한 산업어만 골라
    {정규화 키 → 정본 섹터명}을 파생한다. 정본을 손으로 중복 기입하지 않으므로 NL 인식과
    종목 분류가 어긋날 수 없다. 각 용어가 정확히 하나의 정본 섹터에만 매핑되는지 검증한다
    (둘 이상이면 모호 → import 시점에 fail-fast)."""
    canonical = set(CANONICAL_SECTORS)
    term_to_sectors: dict[str, set[str]] = {}
    for sector, terms in MAPPING_RULES.items():
        if sector not in canonical:
            continue
        for term in terms:
            term_to_sectors.setdefault(term, set()).add(sector)
    derived: dict[str, str] = {}
    for term in NL_SAFE_TERMS:
        sectors = term_to_sectors.get(term)
        if not sectors or len(sectors) != 1:
            raise ValueError(
                f"NL_SAFE_TERMS 용어 {term!r}는 정확히 하나의 정본 섹터에 매핑돼야 한다(현재: {sectors})"
            )
        derived[_sector_key(term)] = next(iter(sectors))
    return derived


# 파생(MAPPING_RULES 산업어) + 오버라이드(사용자 전용 통칭). 충돌 시 오버라이드가 우선한다.
_SECTOR_SYNONYMS: dict[str, str] = {**_derive_mapper_nl_synonyms(), **_SECTOR_SYNONYM_OVERRIDES}


def normalize_sector(raw: Optional[str]) -> Optional[str]:
    """사용자/LLM이 준 업종 표현을 정본 섹터명으로 정규화한다. 못 찾으면 None."""
    if not raw:
        return None
    key = _sector_key(raw)
    if key in _CANONICAL_BY_KEY:
        return _CANONICAL_BY_KEY[key]
    return _SECTOR_SYNONYMS.get(key)


def normalize_sector_value(raw) -> Optional[str | list[str]]:
    """sector 필드 값(str 또는 list)을 정규형으로 정규화한다(FR-STR-066 ⑦ 다중 섹터).

    정규형: 없음=None, 단일=str(기존 해시·직렬화와 바이트 동일 — 하위 호환), 2개 이상=list.
    각 항목은 normalize_sector로 정본화하고, 미지원 항목은 버리며, 순서 보존 dedup한다.
    """
    items = raw if isinstance(raw, list) else [raw]
    seen: list[str] = []
    for item in items:
        canonical = normalize_sector(item) if isinstance(item, (str, type(None))) else None
        if canonical and canonical not in seen:
            seen.append(canonical)
    if not seen:
        return None
    return seen[0] if len(seen) == 1 else seen


def sector_value_as_list(value) -> list[str]:
    """정규형 sector 값(None/str/list)을 항상 리스트로 펼친다(소비부 공용)."""
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]


@lru_cache(maxsize=1)
def _load_sector_map() -> dict[str, str]:
    # 마스터(상폐 종목 sector 백필)를 깔고 korea-stocks.json(현재 상장 SOT)으로 덮는다.
    smap: dict[str, str] = {
        s["symbol"]: s["sector"] for s in _load_master() if s.get("symbol") and s.get("sector")
    }
    if _KOREA_STOCKS_PATH.exists():
        stocks = json.loads(_KOREA_STOCKS_PATH.read_text(encoding="utf-8"))
        smap.update(
            {s["symbol"]: s["sector"] for s in stocks if s.get("symbol") and s.get("sector")}
        )
    # 우선주(끝자리≠0, '00088K' 신형 포함)는 모주(prefix+'0')의 섹터를 물려받는다 —
    # 섹터 분류는 회사 단위인데 korea-stocks.json은 보통주만 담아 우선주가 전부 미상이 된다.
    for s in _load_master():
        sym = s.get("symbol") or ""
        if len(sym) == 6 and sym[-1] != "0" and sym not in smap:
            parent = smap.get(sym[:5] + "0")
            if parent:
                smap[sym] = parent
    return smap


def filter_by_sector(symbols: list[str], sector: str | list[str]) -> list[str]:
    """심볼 목록을 정본 섹터명(단일 또는 복수의 합집합)으로 필터링한다(섹터 미상 종목은 제외)."""
    canonicals = {
        c for c in (normalize_sector(s) for s in sector_value_as_list(sector)) if c is not None
    }
    if not canonicals:
        return []
    smap = _load_sector_map()
    return [s for s in symbols if smap.get(s) in canonicals]


def sector_unknown_delisted(symbols: list[str]) -> list[str]:
    """섹터 분류가 없어 어떤 섹터 필터에서도 빠지는 '상장폐지' 심볼들 — 엔진이 생존 편향
    경고를 낼 근거다. 현재 상장 종목의 분류 공백(신규 상장 등)은 생존 편향이 아니므로
    여기 포함하지 않는다(korea-stocks.json 갱신 시 자연 치유)."""
    smap = _load_sector_map()
    delisted = {s["symbol"] for s in _load_master() if s.get("delistingDate")}
    return [s for s in symbols if s not in smap and s in delisted]


def get_delisting_dates(symbols: list[str]) -> dict[str, str]:
    """symbol -> delistingDate, only for names that actually delisted.

    Lets the engine label a forced exit at a delisted name's last trading day as
    "상장폐지" rather than the generic "데이터 종료". 주식 마스터와 ETF 마스터
    (상폐 백필분)를 함께 본다 — 심볼 공간이 겹치지 않아 병합이 안전하다.
    """
    wanted = set(symbols)
    dates = {
        s["symbol"]: s["delistingDate"]
        for s in _load_master()
        if s["symbol"] in wanted and s.get("delistingDate")
    }
    dates.update({
        e["symbol"]: e["delistingDate"]
        for e in _load_etf_master()
        if e["symbol"] in wanted and e.get("delistingDate")
    })
    return dates
