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

from engine.console_logging import console_logger
from engine.sector_mapper import MAPPING_RULES, NL_SAFE_TERMS

logger = console_logger(__name__, "UNIVERSE")

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
    _SECTOR_MAP_SOURCE.update({"source": None, "reason": None})
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


def resolve_single_etf_product(etf_theme: Optional[str]) -> Optional[dict]:
    """etf_theme이 특정 ETF 상품명과 정확히 일치하면 그 마스터 항목을 반환한다.

    "반도체"처럼 여러 ETF에 매칭되는 테마 키워드는 None — 지정된 단일 상품
    ("KODEX 반도체")만 단일 종목 취급 판단에 쓸 수 있다(filter_etf_by_theme의
    ① 정확 매칭과 동일 기준).
    """
    key = _etf_key(etf_theme or "")
    if not key:
        return None
    for e in _load_etf_master():
        if _etf_key(e["name"]) == key:
            return e
    return None


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


def _is_spac(name: str) -> bool:
    """스팩(기업인수목적회사) 종목명 판정 — "OO스팩", "OO제N호스팩" 등 항상 이름에
    "스팩"이 포함된다(리츠와 달리 접미사가 아니어도 이 어휘가 일반 사명에 우연히
    섞일 일이 없다 — 실측 232개 전량 확인). 백테스트/리밸런싱 유니버스에서 항상 배제한다."""
    return "스팩" in (name or "")


def _is_preferred(symbol: str) -> bool:
    """우선주 판정 — KRX 종목코드는 보통주가 항상 끝자리 '0'이고(표준 채번 규칙),
    우선주는 끝자리가 그 외 값이다(구형 숫자 5/7/9, '00088K' 같은 신형 영문 포함).
    백테스트/리밸런싱 유니버스에서 항상 배제한다(_load_sector_map의 동일 판정과 동일 규칙)."""
    return len(symbol or "") == 6 and symbol[-1] != "0"


def resolve_symbols(universe_id: Optional[str], start: Optional[str], end: str) -> Optional[list[str]]:
    """As-of symbol list for the window, or None if universe_id is not a market universe.

    For a large-cap (KOSPI200) universe this returns the alive-KOSPI superset; the
    engine then applies the point-in-time top-N market-cap gate. SPAC(기업인수목적회사)와
    우선주 종목은 여기서 항상 배제한다.
    """
    markets, _ = parse_universe_markets(universe_id)
    if not markets:
        return None
    lo = start or _DEFAULT_START_FLOOR
    target = set(markets)
    symbols = [
        s["symbol"] for s in _load_master()
        if s.get("market") in target and _alive(s, lo, end)
        and not _is_spac(s.get("name", "")) and not _is_preferred(s.get("symbol", ""))
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

# korea-stocks.json sector 필드의 전체 값(45개). 파서·프롬프트·검증이 공유하는 정본.
# '로봇'(2026-07-13 신설)은 KSIC 공식 분류에 없어 사명(로봇/로보틱스) 기준으로 분류된
# 독립 섹터다(sector_mapper.MAPPING_RULES["로봇"] 참조).
#
# 2026-07-30 묶음 섹터 분할: KSIC 산업분류가 두 갈래를 깨끗하게 가르는 6쌍만 독립
# 섹터로 나눴다(scripts/split_combined_sectors.py). 나머지 12쌍은 분류 데이터가 구분을
# 주지 않거나(에너지/원자력 — KSIC에 원자력 코드 없음, 미디어/엔터) 두 낱말이 포함·동의
# 관계라(철강⊂금속, 기계≈장비, 디스플레이/'부품') 분할하지 않았다.
CANONICAL_SECTORS: tuple[str, ...] = (
    "IT 하드웨어", "가구/인테리어", "건설", "교육", "금융지주", "기계/장비",
    "기타 서비스", "기타 제조업", "디스플레이", "로봇", "목재", "미디어/엔터",
    "바이오/제약", "반도체", "반도체 소재", "보험", "부동산", "사료", "소프트웨어",
    "레저",
    "수산", "수산가공", "시멘트", "식품", "에너지/원자력", "욕실", "우주항공/방산",
    "운송/물류", "여행", "유통/상사", "은행", "음료", "의료기기", "이차전지", "자동차",
    "자동차부품", "조선", "종이", "증권", "지주회사", "철강/금속", "축산",
    "전자부품", "통신/유틸리티", "패션", "플랫폼", "해운", "화장품", "화학",
)

# [하위 호환] 분할 전 구 섹터명 → 신규 두 섹터. 저장된 전략·백테스트 이력·PIT 유니버스
# 스냅샷이 구 이름을 그대로 들고 있으므로, 구 이름이 들어오면 두 신규 섹터의 합집합으로
# 해석해 과거 결과가 계속 재현되게 한다(사용자 결정 2026-07-30 — 하드 컷 대신 별칭 유지).
LEGACY_COMBINED_SECTORS: dict[str, tuple[str, str]] = {
    "증권/보험": ("증권", "보험"),
    "은행/금융지주": ("은행", "금융지주"),
    "조선/해운": ("조선", "해운"),
    "식품/음료": ("식품", "음료"),
    "소프트웨어/플랫폼": ("소프트웨어", "플랫폼"),
    "사료/축산": ("사료", "축산"),
    "화장품/패션": ("화장품", "패션"),
    "디스플레이/부품": ("디스플레이", "전자부품"),
}

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
    "인터넷": "플랫폼",  # 포털·정보매개 — 패키지/게임 개발사(소프트웨어)와 구분
    # '카지노'·'여행사'는 지식그래프에 큐레이션 개념(casino·travel-agency)이 있어
    # 여기 넣지 않는다 — 섹터 동의어로 등록하면 KG 스캔 인덱스에서 제외돼
    # (FR-STR-070 ③) 더 구체적인 개념 조회를 가린다.
    "관광": "여행",
    "호텔": "레저", "리조트": "레저", "숙박": "레저",
    # 은행·금융지주·증권·보험·식품·음료·조선·해운·소프트웨어·플랫폼·사료·축산은
    # 2026-07-30 분할로 전부 정본 섹터명이 됐다 — _CANONICAL_BY_KEY가 직접 잡으므로
    # 여기 동의어로 중복 기입하지 않는다(구 묶음명은 LEGACY_COMBINED_SECTORS 소관).
    "의류": "패션", "의복": "패션",  # 화장품·패션은 2026-07-30 분할로 정본명이 됐다
    "엔터": "미디어/엔터", "엔터테인먼트": "미디어/엔터", "미디어": "미디어/엔터",
    "통신": "통신/유틸리티",
    "에너지": "에너지/원자력", "원자력": "에너지/원자력",
    "철강": "철강/금속",
    "방산": "우주항공/방산", "우주항공": "우주항공/방산", "항공우주": "우주항공/방산",
    # '로봇'·'로보틱스'는 MAPPING_RULES 파생(NL_SAFE_TERMS)으로 자동 인식 — 여기 중복 기입 금지.
    "기계": "기계/장비", "기계장비": "기계/장비",
    "리츠": "부동산",
    "물류": "운송/물류", "운송": "운송/물류",
    "유통": "유통/상사",
    "제지": "종이",
    "완성차": "자동차",
    "지주": "지주회사",
    "헬스케어": "의료기기",
    # 'AI/인공지능'은 업종이 아니라 테마다(네이버 테마 '지능형로봇/인공지능(AI)') — NL
    # 오버라이드로 소프트웨어/플랫폼에 근사하면 결정적 섹터 확정이 테마 그라운딩 체인
    # (KG 테마 카탈로그·라이브 조회·검색 학습)을 막아 유니버스가 과대해진다(모든 소프트웨어
    # 업체가 AI를 하지 않는다 — 2026-07-27 교정). 재추가 금지. 종목 산업분류(sector_mapper
    # MAPPING_RULES)의 '인공지능'·'AI' 키워드는 사명 분류용이라 별개로 유지한다.
}


# LLM 프롬프트용 업종 주석 — 이름만으로는 분류 관례를 오해하기 쉬운 업종에만 붙인다.
# 실측 사고(2026-07-12): '전력설비 관련주'를 LLM이 이름 연상('전력→유틸리티')으로
# 통신/유틸리티(실제로는 통신사·한전 등 사업자 25종목)에 매핑 — 변압기·전력기기 제조사는
# 이 분류 체계에서 에너지/원자력, 전선 제조는 IT 하드웨어에 속한다.
_SECTOR_LLM_GLOSSES: dict[str, str] = {
    "통신/유틸리티": "통신사와 한국전력 등 전력·가스 판매 사업자만. 설비 제조는 아님",
    "에너지/원자력": "발전·원전 + 변압기·전력설비 등 전력기기 제조 포함",
    "IT 하드웨어": "통신·방송장비, 정밀기기, 컴퓨터, 전선 제조. 개별 전자부품은 전자부품 업종",
    "로봇": "로봇 전문기업(산업용·협동·서비스 로봇). 일반 자동화 설비·공작기계는 기계/장비",
}


# [사용자 노출] 묶음 섹터('A/B')의 구성 안내. 사용자가 묶음의 한쪽('원자력')을 말했을 때
# "그 업종은 따로 없고 이렇게 묶여 있으며 이런 것도 함께 들어 있다"를 밝히기 위한 문구다 —
# 조건이 조용히 넓어지는 것을 막는다(2026-07-30).
#
# 문구를 손으로 쓰는 이유: KSIC 코드명을 그대로 노출할 수 없다('전동기, 발전기 및 전기
# 변환·공급·제어 장치 제조업'). 종목 수는 결정론이 채우고 사람은 구성만 적는다 —
# LLM이 지어낼 여지를 두지 않는다(_SECTOR_LLM_GLOSSES와 같은 관례, 그쪽은 프롬프트용).
#
# 묶음의 성격이 셋으로 갈려 문구도 다르다:
#   ① 진짜 혼재 — 여러 갈래가 실제로 섞임. "~도 함께 들어 있습니다"
#   ② 사실상 한쪽뿐 — 이름만 묶음. "이름은 A/B지만 사실상 전부 A입니다"
#   ③ 두 낱말이 같은 분류 — 나눌 '나머지'가 없음. "B가 따로 있는 게 아니라 ~"
# 각 값은 "…묶여 있어요. " 뒤에 그대로 붙는 완결 문장이다(유형마다 어순이 달라
# 고정 접두사를 쓸 수 없다 — "이 업종에는 이름은 철강/금속이지만…"처럼 깨진다).
SECTOR_COMPOSITION_NOTES: dict[str, str] = {
    # ① 진짜 혼재
    "에너지/원자력": (
        "이 업종에는 원전 관련 기업 외에 변압기·발전기 같은 전력기기 제조사가 가장 많고, "
        "정유·도시가스 회사도 함께 들어 있습니다"
    ),
    "미디어/엔터": (
        "이 업종에는 방송·영화 제작사와 광고대행사, 출판사, 음반·매니지먼트사가 "
        "함께 들어 있습니다"
    ),
    "바이오/제약": "이 업종에는 의약품 제조사가 대부분이고, 신약 연구개발 기업도 함께 들어 있습니다",
    "유통/상사": "이 업종에는 종합상사·도매업과 백화점·편의점 같은 소매업이 함께 들어 있습니다",
    "우주항공/방산": (
        "이 업종에는 항공기·우주선 부품 제조와 무기 제조에 더해 "
        "항공사(여객 운송)도 함께 들어 있습니다"
    ),
    "운송/물류": "이 업종에는 화물·여객 운송과 창고·운송주선 같은 물류 서비스가 함께 들어 있습니다",
    "통신/유틸리티": (
        "이 업종에는 통신사와 전기·가스 공급 사업자, 전기·통신 공사업체가 함께 들어 있습니다"
        " — 전력설비를 만드는 제조사는 에너지/원자력에 있습니다"
    ),
    "가구/인테리어": "이 업종에는 가구 제조사와 조명·전구 제조사가 함께 들어 있습니다",
    # ② 사실상 한쪽뿐
    "철강/금속": "이름은 철강/금속이지만 사실상 전부 1차 철강 제조사입니다",
    # ③ 두 낱말이 같은 분류
    "기계/장비": (
        "'장비'가 따로 있는 게 아니라 특수·일반 목적용 기계 제조가 한 업종으로 묶여 있습니다"
    ),
}


def _topic_particle(word: str) -> str:
    """주제 조사(은/는)를 마지막 글자의 받침 유무로 고른다. 한글이 아니면 '은(는)'."""
    last = (word or "")[-1:]
    if not last or not ("가" <= last <= "힣"):
        return "은(는)"
    return "은" if (ord(last) - ord("가")) % 28 else "는"


def sector_composition_notice(raw: Optional[str], count: Optional[int] = None) -> Optional[str]:
    """사용자가 말한 업종 표현이 묶음 섹터로 넓어질 때 보여줄 안내문. 아니면 None.

    count(해당 섹터의 종목 수)는 호출부가 filter_by_sector 결과로 넘긴다 — 이 모듈이
    유니버스를 다시 계산하지 않게 해 PIT 시점·시장 조건을 호출부가 통제한다."""
    if not raw or not is_narrow_sector_approximation(raw):
        return None
    sector = normalize_sector(raw)
    note = SECTOR_COMPOSITION_NOTES.get(sector or "")
    if not note:
        return None
    tail = f"(총 {count}종목)" if count is not None else ""
    return (
        f"'{raw}'{_topic_particle(raw)} 별도 업종으로 분류돼 있지 않고 "
        f"{sector} 업종에 묶여 있어요. {note}{tail}."
    )


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


def is_narrow_sector_approximation(raw: Optional[str]) -> bool:
    """동의어 매칭이 사용자가 말한 것보다 넓은 섹터로 뭉뚱그렸는지 판정한다.

    normalize_sector는 정본 일치("반도체"→"반도체")와 동의어 근사("태양광"→"에너지/원자력")를
    구분 없이 같은 값으로 반환한다. 이 함수는 후자만 True로 걸러, classify_universe가 섹터
    확정 전에 더 구체적인 카탈로그 테마가 있는지 먼저 확인하게 한다.

    판정: 정본 그대로면 False. 그 외에 **묶음 섹터('A/B')로 매핑되면 항상 True**다 —
    묶음 섹터는 성격이 다른 둘 이상을 한 이름에 담고 있어서, 사용자가 그중 한쪽('원자력')을
    말했든 아예 다른 표현('태양광')을 썼든 실제로 개념이 넓어지기 때문이다.

    [2026-07-30 수정] 종전 판정은 "표현이 정본명 글자 안에 있으면 이름 표기 차이"로 보고
    False를 냈다. 그 근거였던 '은행'→'은행/금융지주'·'보험'→'증권/보험'은 묶음 섹터 분할로
    전부 정본명이 됐고, 남은 글자-포함 케이스는 전부 진짜 좁힘 요청이었다 — '원자력'(→72종목,
    정유·도시가스 포함)·'미디어'(→111)·'기계'(→217)가 조용히 넓어지고 있었다."""
    if not raw:
        return False
    key = _sector_key(raw)
    if key in _CANONICAL_BY_KEY:
        return False
    sector = _SECTOR_SYNONYMS.get(key)
    if not sector:
        return False
    if "/" in sector:
        return True
    return key not in _sector_key(sector)


def normalize_sector_value(raw) -> Optional[str | list[str]]:
    """sector 필드 값(str 또는 list)을 정규형으로 정규화한다(FR-STR-066 ⑦ 다중 섹터).

    정규형: 없음=None, 단일=str(기존 해시·직렬화와 바이트 동일 — 하위 호환), 2개 이상=list.
    각 항목은 normalize_sector로 정본화하고, 미지원 항목은 버리며, 순서 보존 dedup한다.
    """
    items = raw if isinstance(raw, list) else [raw]
    seen: list[str] = []
    for item in items:
        if not isinstance(item, (str, type(None))):
            continue
        for canonical in expand_legacy_sector(item):
            if canonical not in seen:
                seen.append(canonical)
    if not seen:
        return None
    return seen[0] if len(seen) == 1 else seen


_LEGACY_BY_KEY = {_sector_key(k): v for k, v in LEGACY_COMBINED_SECTORS.items()}


def expand_legacy_sector(raw: Optional[str]) -> tuple[str, ...]:
    """섹터 표현 하나를 정본 섹터 튜플로 편다.

    분할 전 구 묶음명('증권/보험')은 신규 두 섹터의 합집합으로 편다 — 저장된 전략·백테스트
    이력·PIT 스냅샷이 구 이름을 들고 있어도 같은 종목 집합이 나오게 하기 위함이다.
    그 외에는 normalize_sector 결과 0개 또는 1개."""
    if not raw:
        return ()
    legacy = _LEGACY_BY_KEY.get(_sector_key(raw))
    if legacy:
        return legacy
    canonical = normalize_sector(raw)
    return (canonical,) if canonical else ()


def sector_value_as_list(value) -> list[str]:
    """정규형 sector 값(None/str/list)을 항상 리스트로 펼친다(소비부 공용)."""
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [value]



# 섹터 소속을 어디서 읽었는지 — 폴백이 조용히 도는 것을 막기 위한 출처 기록.
# 정본(KG)이 아닌 경로로 백테스트가 돌면 사용자가 알아야 한다(엔진이 경고로 노출).
_SECTOR_MAP_SOURCE: dict[str, Optional[str]] = {"source": None, "reason": None}


def sector_map_source() -> dict[str, Optional[str]]:
    """마지막으로 로드한 섹터 소속의 출처. {"source": "graph"|"files", "reason": str|None}.

    source="files"면 정본(KG)을 못 읽어 파생 캐시로 폴백한 것이다 — 호출부(엔진)가
    사용자에게 고지해야 한다. 아직 로드 전이면 source=None."""
    if _SECTOR_MAP_SOURCE["source"] is None:
        _load_sector_map()
    return dict(_SECTOR_MAP_SOURCE)


def _sector_map_from_graph() -> dict[str, str]:
    """지식그래프의 belongs_to 엣지에서 symbol → 섹터를 읽는다(정본 경로).

    실패는 **조용히 넘기지 않는다** — 예외는 스택과 함께 로그로 남기고 사유를
    _SECTOR_MAP_SOURCE에 기록해 엔진이 사용자에게 고지할 수 있게 한다. 그래도 빈 dict를
    반환해 호출부가 파일로 폴백하는 것은 유지한다(KG 문제로 백테스트가 아예 막히면 안 된다).
    순환 import를 피하려고 지연 import한다(knowledge_graph가 universe_pit을 참조한다)."""
    try:
        from engine.knowledge_graph import get_graph

        graph = get_graph()
    except Exception as exc:  # noqa: BLE001 — 폴백은 하되 침묵하지 않는다
        logger.exception("섹터 소속 정본(지식그래프) 로드 실패 — 파일 캐시로 폴백")
        _SECTOR_MAP_SOURCE["reason"] = f"지식그래프 로드 실패: {type(exc).__name__}: {exc}"
        return {}
    smap: dict[str, str] = {}
    for edge in graph.edges:
        if edge.get("type") != "belongs_to":
            continue
        source, target = str(edge.get("source", "")), str(edge.get("target", ""))
        if source.startswith("company:") and target.startswith("sector:"):
            smap[source.split(":", 1)[1]] = target.split(":", 1)[1]
    if not smap:
        _SECTOR_MAP_SOURCE["reason"] = (
            "지식그래프에 섹터 소속 엣지가 없습니다 — data/kg-sector-membership.json 미생성"
            "(backend/scripts/build_sector_membership.py --apply)"
        )
    return smap


def sector_map_from_files() -> dict[str, str]:
    """symbol → 섹터를 원본 파일에서 병합한다 — 소속 오버레이 생성과 부트스트랩 폴백의
    **공용 구현**(같은 병합 규칙을 두 곳에 적지 않는다).

    ① 마스터(상폐 종목 sector 백필)를 깔고 ② korea-stocks.json(현재 상장)으로 덮은 뒤
    ③ 우선주(끝자리≠0)에 모주(prefix+'0') 섹터를 상속한다 — 섹터 분류는 회사 단위인데
    korea-stocks.json은 보통주만 담아 우선주가 전부 미상이 된다.
    """
    smap: dict[str, str] = {
        s["symbol"]: s["sector"] for s in _load_master() if s.get("symbol") and s.get("sector")
    }
    if _KOREA_STOCKS_PATH.exists():
        stocks = json.loads(_KOREA_STOCKS_PATH.read_text(encoding="utf-8"))
        rows = stocks if isinstance(stocks, list) else stocks.get("stocks", [])
        smap.update({s["symbol"]: s["sector"] for s in rows if s.get("symbol") and s.get("sector")})
    for s in _load_master():
        sym = s.get("symbol") or ""
        if len(sym) == 6 and sym[-1] != "0" and sym not in smap:
            parent = smap.get(sym[:5] + "0")
            if parent:
                smap[sym] = parent
    return smap


@lru_cache(maxsize=1)
def _load_sector_map() -> dict[str, str]:
    """symbol → 정본 섹터. **정본은 지식그래프**다(2026-07-30 전환).

    인터프리터가 지식을 찾는 곳이 KG이므로 섹터 소속도 KG가 권위여야 한다 — 종전에는
    소속이 korea-stocks.json에만 있어 `related_universe('원자력')`이 빈 결과를 냈다.
    KG의 `company -belongs_to→ sector` 엣지(data/kg-sector-membership.json 오버레이)를
    읽고, 오버레이가 없는 환경(신규 클론·부트스트랩)에서만 파일로 폴백한다.
    """
    _SECTOR_MAP_SOURCE["reason"] = None
    smap = _sector_map_from_graph()
    if smap:
        _SECTOR_MAP_SOURCE["source"] = "graph"
        return smap
    _SECTOR_MAP_SOURCE["source"] = "files"
    logger.warning(
        "섹터 소속을 정본(지식그래프)이 아니라 파일 캐시에서 읽습니다 — %s",
        _SECTOR_MAP_SOURCE["reason"] or "사유 불명",
    )
    return sector_map_from_files()


def filter_by_sector(symbols: list[str], sector: str | list[str]) -> list[str]:
    """심볼 목록을 정본 섹터명(단일 또는 복수의 합집합)으로 필터링한다(섹터 미상 종목은 제외).

    분할 전 구 묶음명('증권/보험')이 들어와도 신규 두 섹터의 합집합으로 편다 —
    저장된 백테스트가 같은 종목 집합으로 재현되게 하기 위함이다."""
    canonicals = {
        c for s in sector_value_as_list(sector) for c in expand_legacy_sector(s)
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


# ── 신규 상장 유니버스 (FR-STR-073) ──────────────────────────────────────────
# "2026년 신규 상장 종목"은 **상장일이 그 구간에 속하는 종목 집합(코호트)**이다. 종목의
# 상장일 하나만 보면 결정되므로 정적 심볼 필터로 충분하다 — 섹터 필터와 같은 자리에서
# 같은 방식으로 걸러진다. 상장 이전 구간은 애초에 가격 데이터가 없어(available_df)
# look-ahead가 생기지 않고, 상폐 종목도 상장일을 갖고 있어(마스터의 KRX-DELISTING 백필)
# 생존 편향 없이 당시 신규 상장 종목이 그대로 포함된다.


def first_listed_date(stock: dict) -> Optional[str]:
    """이 종목이 '처음 상장한 날'의 최선 추정(YYYY-MM-DD). 근거가 없으면 None.

    상장일(listingDate)과 로컬 가격 데이터 시작일(dataStart) 중 **이른 쪽**을 쓴다.
    두 값이 갈리는 경우는 이전상장·재상장이다 — KIND 상장법인목록의 상장일은 '현재
    시장에 상장한 날'이라, 코넥스→코스닥으로 옮겨온 종목(실측: 지에프씨생명과학
    listingDate=2025-06-30이지만 2022-12-23부터 거래)이 신규 상장으로 오인된다.
    반대로 상장일이 없는 소수 종목은 dataStart가 상한 없는 하한 역할을 한다(로컬
    백필 시작일이라 실제 상장일보다 늦을 수 없다).
    """
    candidates = [d for d in (stock.get("listingDate"), stock.get("dataStart")) if d]
    return min(candidates) if candidates else None


def first_listed_dates(symbols: list[str]) -> dict[str, str]:
    """symbol -> 최초 상장일. 상장일을 추정할 수 없는 종목은 키 자체가 없다."""
    wanted = set(symbols)
    out: dict[str, str] = {}
    for s in _load_master():
        if s.get("symbol") in wanted:
            listed = first_listed_date(s)
            if listed:
                out[s["symbol"]] = listed
    return out


def filter_by_listing_window(
    symbols: list[str], listing_from: Optional[str], listing_to: Optional[str]
) -> tuple[list[str], list[str]]:
    """상장일이 [listing_from, listing_to] 구간에 속하는 종목만 남긴다(양끝 포함).

    반환: (대상 심볼, 상장일 미상으로 제외된 심볼). 경계가 None이면 그쪽은 무제한이다
    ("2026년 상장"=둘 다, "최근 1년 내 상장"=하한만).

    상장일 미상 종목은 조용히 통과시키지 않고 제외한 뒤 보고한다 — 통과시키면 신규
    상장이 아닌 종목이 섞이고, 침묵하면 사용자가 왜곡을 알 길이 없다.
    """
    dates = first_listed_dates(symbols)
    kept = [
        s for s in symbols
        if s in dates
        and (listing_from is None or dates[s] >= listing_from)
        and (listing_to is None or dates[s] <= listing_to)
    ]
    unknown = [s for s in symbols if s not in dates]
    return kept, unknown


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
