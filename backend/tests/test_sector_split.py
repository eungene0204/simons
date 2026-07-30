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


# ── 지식그래프: 섹터 노드(업종) vs 테마 노드 구분 ──────────────────────────────

def test_kg_sector_nodes_are_distinct_from_theme_nodes():
    """섹터는 전수 분류(모든 종목이 하나에 속함), 테마는 큐레이션된 부분집합이다.
    KG에서 category로 구분된다 — industry vs theme/theme_catalog."""
    from engine.knowledge_graph import get_graph

    graph = get_graph()
    sectors = {k: v for k, v in graph.nodes.items() if k.startswith("sector:")}
    assert len(sectors) == len(CANONICAL_SECTORS)
    assert all(v.get("category") == "industry" for v in sectors.values())
    themes = [v for v in graph.nodes.values() if v.get("category") in ("theme", "theme_catalog")]
    assert themes, "테마 노드가 있어야 대비가 성립한다"
    assert not any(v.get("category") == "industry" for v in themes)


def test_kg_sector_nodes_carry_metadata_derived_from_canonical_sources():
    """섹터 노드는 메타(동의어·KSIC 코드·종목 수·구성 안내)를 정본에서 파생해 담는다 —
    손으로 두 번 적지 않는다. 종목 소속 자체는 KG에 복제하지 않는다."""
    from engine.knowledge_graph import get_graph

    nodes = get_graph().nodes
    energy = nodes["sector:에너지/원자력"]
    assert energy["is_combined"] is True
    assert energy["member_count"] > 0
    assert "원자력" in energy["synonyms"] and "태양광" in energy["synonyms"]
    assert energy["ksic_codes"]
    assert "정유" in energy["composition_note"]        # 묶음 섹터는 구성 안내를 갖는다
    cosmetics = nodes["sector:화장품"]
    assert cosmetics["is_combined"] is False
    assert "composition_note" not in cosmetics         # 분할 완료 섹터는 안내 없음
    assert "20423" in cosmetics["ksic_codes"]          # 화장품 제조업 코드


def test_kg_is_the_sector_membership_sot():
    """[2026-07-30 정본 전환] 섹터 소속의 정본은 KG다.

    인터프리터가 지식을 찾는 곳이 KG이므로 "이 섹터에 어떤 종목이 있나"도 그래프로
    답할 수 있어야 한다 — 종전에는 소속이 korea-stocks.json에만 있어 KG가 몰랐다.
    (직전 커밋의 test_kg_sector_nodes_do_not_duplicate_stock_membership을 대체한다:
    '복제하면 어긋난다'는 우려는 파일을 파생 캐시로 강등해 해소했다.)"""
    from engine.knowledge_graph import get_graph
    from engine.universe_pit import _load_sector_map, _sector_map_from_graph

    from_graph = _sector_map_from_graph()
    assert from_graph, "KG에 belongs_to 소속 엣지가 없다"
    assert _load_sector_map() == from_graph, "filter_by_sector가 KG를 읽지 않는다"

    edges = [
        e for e in get_graph().edges
        if e.get("type") == "belongs_to" and str(e.get("source", "")).startswith("company:")
    ]
    assert len(edges) == len(from_graph)


def test_kg_membership_covers_delisted_and_preferred_shares():
    """상폐 종목과 우선주가 소속에서 빠지면 섹터 유니버스에 생존 편향·누락이 생긴다
    (FR-STR-066 ④-1). 실측 회귀: 오버레이가 상폐를 버려 에너지/원자력 72→66,
    우선주 상속을 빠뜨려 다시 72→66이 됐다."""
    import json as _json
    from pathlib import Path as _P

    from engine.universe_pit import filter_by_sector, _load_sector_map

    master = _json.loads(
        (_P(__file__).resolve().parents[2] / "data" / "stock-master.json").read_text(encoding="utf-8")
    )["stocks"]
    smap = _load_sector_map()
    delisted_with_sector = [s["symbol"] for s in master if s.get("delistingDate") and s.get("sector")]
    assert delisted_with_sector, "상폐 종목 sector 백필이 없다면 이 가드는 무의미하다"
    covered = [s for s in delisted_with_sector if s in smap]
    assert len(covered) == len(delisted_with_sector), (
        f"소속에서 빠진 상폐 종목 {len(delisted_with_sector) - len(covered)}건"
    )
    preferred = [s for s in smap if len(s) == 6 and s[-1] != "0"]
    assert preferred, "우선주가 소속에 하나도 없다 — 모주 상속이 누락됐다"
    # 대표 실측치: 상폐·우선주가 모두 들어와야 나오는 숫자
    assert len(filter_by_sector(list(smap), "에너지/원자력")) == 72


def test_stock_file_sector_is_a_derived_cache_of_the_kg():
    """korea-stocks.json의 sector 필드는 정본이 아니라 파생 캐시다(참조부 71곳 호환).
    KG와 어긋나면 잡는다 — 어긋난 채로 두면 어느 쪽이 맞는지 알 수 없다."""
    import json as _json

    from engine.universe_pit import _sector_map_from_graph

    rows = _json.loads(_KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows["stocks"]
    graph_map = _sector_map_from_graph()
    drift = [
        (r["symbol"], r.get("name"), r.get("sector"), graph_map.get(r["symbol"]))
        for r in rows
        if r.get("sector") and graph_map.get(r["symbol"]) != r["sector"]
    ]
    assert not drift, f"KG와 파일 캐시 불일치 {len(drift)}건: {drift[:3]}"


def test_kg_concept_edges_follow_sector_moves():
    """섹터를 옮기면 개념 엣지도 따라가야 한다 — 카지노를 레저로 옮겼는데
    casino 엣지가 미디어/엔터를 가리키고 있었다(2026-07-30)."""
    from engine.knowledge_graph import get_graph, resolve_sector_from_text

    assert resolve_sector_from_text("카지노 관련주") == "레저"
    assert resolve_sector_from_text("여행사 관련주") == "여행"
    assert get_graph().issues == [], "시드 엣지가 존재하지 않는 노드를 참조한다"


def test_sector_map_source_reports_the_canonical_path():
    """정상 상태에서는 정본(지식그래프)에서 읽었다고 보고해야 한다."""
    from engine.universe_pit import sector_map_source

    assert sector_map_source() == {"source": "graph", "reason": None}


def test_fallback_to_file_cache_is_not_silent(monkeypatch, caplog):
    """KG를 못 읽으면 파일로 폴백하되 **조용히 넘기지 않는다**.

    정본이 아닌 데이터로 유니버스가 확정되면 결과가 달라지므로, 출처와 사유를 남겨
    엔진이 사용자에게 고지할 수 있어야 한다(backtest_engine의 warnings)."""
    import logging

    from engine import knowledge_graph as kg
    from engine import universe_pit as u

    def boom():
        raise RuntimeError("KG 로드 실패 재현")

    monkeypatch.setattr(kg, "get_graph", boom)
    u.reload_master()
    try:
        with caplog.at_level(logging.WARNING):
            smap = u._load_sector_map()
        source = u.sector_map_source()
        assert source["source"] == "files"
        assert "KG 로드 실패 재현" in (source["reason"] or "")
        assert smap, "폴백 결과가 비었다 — KG 문제로 백테스트가 아예 막히면 안 된다"
    finally:
        monkeypatch.undo()
        u.reload_master()


def test_engine_warns_when_sector_source_is_not_canonical():
    """폴백 시 엔진이 사용자 경고를 추가하도록 배선돼 있어야 한다."""
    import inspect

    import backtest_engine

    source = inspect.getsource(backtest_engine)
    assert "sector_map_source()" in source
    assert "정본(지식그래프)이 아니라 파일 캐시에서" in source
