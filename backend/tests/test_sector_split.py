"""묶음 섹터 분할(2026-07-30) 회귀 — 신규 독립 섹터 + 구 이름 하위 호환.

분할 대상은 KSIC가 두 갈래를 깨끗하게 가르는 6쌍뿐이다. 나머지 12쌍은 분류 데이터가
구분을 주지 않아(에너지/원자력 — KSIC에 원자력 코드 없음) 의도적으로 남겨 뒀다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.universe_pit import (
    CANONICAL_SECTORS,
    LEGACY_COMBINED_SECTORS,
    expand_legacy_sector,
    filter_by_sector,
    normalize_sector,
    normalize_sector_value,
    _load_sector_map,
)

_KOREA_STOCKS = Path(__file__).resolve().parents[2] / "data" / "korea-stocks.json"

SPLIT_PAIRS = [
    ("증권/보험", "증권", "보험"),
    ("은행/금융지주", "은행", "금융지주"),
    ("조선/해운", "조선", "해운"),
    ("식품/음료", "식품", "음료"),
    ("소프트웨어/플랫폼", "소프트웨어", "플랫폼"),
    ("사료/축산", "사료", "축산"),
    ("화장품/패션", "화장품", "패션"),
    ("디스플레이/부품", "디스플레이", "전자부품"),
]


@pytest.mark.parametrize("legacy, side_a, side_b", SPLIT_PAIRS)
def test_split_sectors_are_independent_canonical_entries(legacy, side_a, side_b):
    assert side_a in CANONICAL_SECTORS
    assert side_b in CANONICAL_SECTORS
    assert legacy not in CANONICAL_SECTORS


@pytest.mark.parametrize("legacy, side_a, side_b", SPLIT_PAIRS)
def test_each_split_side_has_members(legacy, side_a, side_b):
    """양쪽 모두 실제 종목을 가져야 한다 — 빈 유니버스가 생기면 분할이 잘못된 것이다."""
    smap = _load_sector_map()
    symbols = list(smap)
    assert filter_by_sector(symbols, side_a), f"{side_a} 유니버스가 비었다"
    assert filter_by_sector(symbols, side_b), f"{side_b} 유니버스가 비었다"


@pytest.mark.parametrize("legacy, side_a, side_b", SPLIT_PAIRS)
def test_legacy_name_expands_to_both_new_sectors(legacy, side_a, side_b):
    assert expand_legacy_sector(legacy) == LEGACY_COMBINED_SECTORS[legacy]
    assert set(expand_legacy_sector(legacy)) == {side_a, side_b}


@pytest.mark.parametrize("legacy, side_a, side_b", SPLIT_PAIRS)
def test_legacy_name_yields_the_same_universe_as_before(legacy, side_a, side_b):
    """[하위 호환] 저장된 전략·백테스트가 구 섹터명을 들고 있어도 종목 집합이 같아야 한다."""
    symbols = list(_load_sector_map())
    union = set(filter_by_sector(symbols, side_a)) | set(filter_by_sector(symbols, side_b))
    assert set(filter_by_sector(symbols, legacy)) == union


@pytest.mark.parametrize("legacy, side_a, side_b", SPLIT_PAIRS)
def test_legacy_name_normalizes_to_a_two_sector_list(legacy, side_a, side_b):
    assert normalize_sector_value(legacy) == [side_a, side_b]


@pytest.mark.parametrize("_legacy, side_a, side_b", SPLIT_PAIRS)
def test_new_sector_names_resolve_to_themselves(_legacy, side_a, side_b):
    assert normalize_sector(side_a) == side_a
    assert normalize_sector(side_b) == side_b


def test_no_split_sector_remains_in_stock_data():
    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    present = {s.get("sector") for s in rows}
    for legacy, _a, _b in SPLIT_PAIRS:
        assert legacy not in present, f"{legacy}가 종목 데이터에 남아 있다"


def test_apparel_stays_out_of_cosmetics():
    """의류·섬유 기업이 화장품으로 넘어오면 안 된다(경계 회귀)."""
    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    for row in rows:
        if row.get("sector") == "화장품":
            assert row.get("industry") == "기타 화학제품 제조업", (
                f"{row.get('name')}: 화장품 섹터에 섬유·의류 코드가 들어왔다"
            )


def test_unsplit_combined_sectors_are_untouched():
    """분류 데이터가 두 갈래를 못 가르는 쌍은 그대로 유지된다 —
    근거 없는 종목 귀속을 만들지 않기 위한 의도적 보류다(임의 분할 방지 가드)."""
    for kept in ("에너지/원자력", "미디어/엔터", "기계/장비", "철강/금속",
                 "유통/상사", "바이오/제약"):
        assert kept in CANONICAL_SECTORS
        assert normalize_sector(kept) == kept


def test_display_membership_is_catalog_grounded():
    """디스플레이 귀속은 외부 큐레이션 카탈로그(+명시 보강)를 근거로 삼는다 —
    KSIC '전자부품 제조업' 한 코드로는 갈리지 않으므로, 근거 목록과 데이터가 일치해야 한다."""
    import sys
    from pathlib import Path as _P
    sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from scripts.split_combined_sectors import DISPLAY_SYMBOLS

    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    actual = {s["symbol"] for s in rows if s.get("sector") == "디스플레이"}
    assert actual == set(DISPLAY_SYMBOLS), (
        f"근거 목록 밖: {sorted(actual - set(DISPLAY_SYMBOLS))} / "
        f"데이터에 없음: {sorted(set(DISPLAY_SYMBOLS) - actual)}"
    )


def test_misregistered_stocks_left_electronic_parts():
    """KSIC '전자부품 제조업'으로 오등록됐던 종목은 실제 사업 섹터로 옮겨졌다."""
    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    by_name = {s["name"]: s.get("sector") for s in rows}
    for name, expected in (
        ("파미셀", "바이오/제약"), ("두산", "지주회사"), ("한화시스템", "우주항공/방산"),
        ("알에스오토메이션", "로봇"), ("캐프", "자동차부품"),
    ):
        assert by_name.get(name) == expected, f"{name}: {by_name.get(name)} != {expected}"


def test_travel_and_leisure_are_independent_sectors():
    """[2026-07-30] 관광·숙박·카지노가 미디어/엔터에 섞여 있었다 — MAPPING_RULES의
    관광 어휘가 미디어/엔터 버킷에 들어 있던 탓. 하나투어·강원랜드가 '미디어 업종'
    백테스트에 잡히던 문제."""
    assert "여행" in CANONICAL_SECTORS and "레저" in CANONICAL_SECTORS
    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    by_name = {s["name"]: s.get("sector") for s in rows}
    for name in ("하나투어", "모두투어", "노랑풍선", "참좋은여행", "롯데관광개발", "레드캡투어"):
        assert by_name.get(name) == "여행", f"{name}: {by_name.get(name)}"
    for name in ("강원랜드", "파라다이스", "GKL", "아난티", "모나용평", "서부T&D"):
        assert by_name.get(name) == "레저", f"{name}: {by_name.get(name)}"


def test_media_sector_no_longer_holds_tourism():
    """미디어/엔터에 여행사·숙박·유원지 KSIC가 남아 있으면 안 된다."""
    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    tourism = {
        "여행사 및 기타 여행보조 서비스업",
        "일반 및 생활 숙박시설 운영업",
        "유원지 및 기타 오락관련 서비스업",
    }
    leaked = [s["name"] for s in rows if s.get("sector") == "미디어/엔터" and s.get("industry") in tourism]
    assert not leaked, f"미디어/엔터에 관광업 잔존: {leaked}"


@pytest.mark.parametrize("term, expected", [
    ("관광", "여행"), ("여행", "여행"),
    ("호텔", "레저"), ("리조트", "레저"), ("숙박", "레저"), ("레저", "레저"),
])
def test_travel_leisure_synonyms(term, expected):
    assert normalize_sector(term) == expected


@pytest.mark.parametrize("term", ["카지노", "여행사"])
def test_curated_kg_concepts_are_not_shadowed_by_sector_synonyms(term):
    """지식그래프에 큐레이션 개념이 있는 용어는 섹터 동의어로 등록하지 않는다 —
    등록하면 KG 스캔 인덱스에서 제외돼(FR-STR-070 ③) 더 구체적인 개념 조회를 가린다."""
    from engine.knowledge_graph import get_graph

    assert normalize_sector(term) is None, f"{term}이 섹터로 잡히면 KG 개념이 가려진다"
    assert get_graph().find_concepts(f"{term} 관련주"), f"KG가 {term}을 개념으로 인식하지 못한다"


def test_bank_and_financial_holding_do_not_overlap():
    """예금취급기관(은행)과 금융 지주회사(금융지주)는 겹치지 않는다."""
    symbols = list(_load_sector_map())
    assert not set(filter_by_sector(symbols, "은행")) & set(filter_by_sector(symbols, "금융지주"))


def test_cosmetics_companies_are_in_the_cosmetics_sector():
    """[2026-07-30] '화장품/패션' 46종목에 화장품 기업이 0개였다 — KSIC에 화장품 코드가 없어
    국내 화장품사가 전부 '기타 화학제품 제조업'으로 화학 섹터에 들어가 있었다.
    사용자가 '화장품 업종'으로 백테스트하면 섬유·의류만 담긴 유니버스를 받았다."""
    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    by_name = {s["name"]: s.get("sector") for s in rows}
    for name in ("아모레퍼시픽", "LG생활건강", "코스맥스", "한국콜마", "클리오", "애경산업"):
        assert by_name.get(name) == "화장품", f"{name}가 화장품 섹터에 없다"


def test_cosmetics_ingredient_makers_stay_in_chemicals():
    """경계: 화장품 '원료·소재'사는 화학에 남는다 — 납품처가 화장품일 뿐 사업은 화학이다."""
    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    by_name = {s["name"]: s.get("sector") for s in rows}
    for name in ("선진뷰티사이언스", "지에프씨생명과학", "에이에스텍", "미원상사"):
        if name in by_name:
            assert by_name[name] == "화학", f"{name}는 화학에 있어야 한다"


def test_sector_overrides_match_stock_data():
    """OVERRIDDEN_SYMBOLS(재생성 경로)와 korea-stocks.json(현재 상장 SOT)이 어긋나면 안 된다.
    scripts/apply_sector_overrides.py가 맞추며, 이 테스트가 드리프트를 잡는다."""
    from engine.sector_mapper import OVERRIDDEN_SYMBOLS

    rows = json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    drift = [
        (s["symbol"], s.get("name"), s.get("sector"), OVERRIDDEN_SYMBOLS[s["symbol"]])
        for s in rows
        if s.get("symbol") in OVERRIDDEN_SYMBOLS
        and s.get("sector") != OVERRIDDEN_SYMBOLS[s["symbol"]]
    ]
    assert not drift, f"오버라이드와 불일치: {drift}"


def test_overrides_only_reference_canonical_sectors():
    from engine.sector_mapper import OVERRIDDEN_SYMBOLS

    unknown = {s for s in OVERRIDDEN_SYMBOLS.values() if s not in CANONICAL_SECTORS}
    assert not unknown, f"정본 목록에 없는 섹터: {sorted(unknown)}"


def test_financial_holding_is_distinct_from_general_holding():
    """금융지주는 기존 '지주회사'(일반 산업 지주)와 별개 섹터로 남는다."""
    assert "지주회사" in CANONICAL_SECTORS and "금융지주" in CANONICAL_SECTORS
    symbols = list(_load_sector_map())
    assert not set(filter_by_sector(symbols, "지주회사")) & set(filter_by_sector(symbols, "금융지주"))
