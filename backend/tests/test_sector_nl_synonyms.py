"""섹터 어휘집 무모순 가드.

섹터 표현은 두 곳에서 정의된다:
  1) sector_mapper.MAPPING_RULES — '종목 산업분류 문자열 → 섹터'(빌드타임 종목 분류)
  2) universe_pit._SECTOR_SYNONYMS — '사용자 자연어 → 섹터'(런타임 NL 인식)
둘은 같은 정본(CANONICAL_SECTORS)을 공유하므로 어긋나면 사고가 난다(예: '로봇'이 (1)엔
있는데 (2)엔 없어 '지원 목록에 없는 섹터'로 안내되던 버그). 이 테스트는 두 어휘집이
'불일치'할 수 없음을 구조적으로 강제한다 — NL 동의어는 MAPPING_RULES에서 파생되고,
어떤 산업어든 NL이 인식하면 반드시 MAPPING_RULES와 같은 정본으로 정규화돼야 한다.
"""
from collections import defaultdict

from engine.sector_mapper import MAPPING_RULES, NL_SAFE_TERMS
from engine.universe_pit import CANONICAL_SECTORS, normalize_sector, _SECTOR_SYNONYMS


def _term_to_canonicals() -> dict[str, set[str]]:
    canonical = set(CANONICAL_SECTORS)
    mapping: dict[str, set[str]] = defaultdict(set)
    for sector, terms in MAPPING_RULES.items():
        if sector not in canonical:
            continue
        for term in terms:
            mapping[term].add(sector)
    return mapping


def test_nl_recognition_never_contradicts_stock_classification():
    """어떤 산업어(MAPPING_RULES)든 NL이 인식하면 반드시 같은 섹터로 정규화돼야 한다.

    미인식(None)은 허용된다(LLM 폴백에 위임). 하지만 '다른 섹터로 인식'은 금지 —
    그건 종목 분류와 사용자 인식이 서로 다른 섹터를 가리킨다는 뜻이라 사고다.
    """
    canonical = set(CANONICAL_SECTORS)
    contradictions = []
    for sector, terms in MAPPING_RULES.items():
        if sector not in canonical:
            continue
        for term in terms:
            got = normalize_sector(term)
            if got is not None and got != sector:
                contradictions.append((term, got, sector))
    assert not contradictions, f"NL 인식과 종목 분류가 불일치: {contradictions}"


def test_nl_safe_terms_map_to_exactly_one_canonical():
    """opt-in한 안전 산업어는 각각 정확히 하나의 정본 섹터에만 속해야 한다(모호어 승격 방지)."""
    term_map = _term_to_canonicals()
    for term in NL_SAFE_TERMS:
        sectors = term_map.get(term, set())
        assert len(sectors) == 1, f"{term!r}는 단일 정본이어야 하는데 {sectors}"


def test_nl_safe_terms_are_recognized():
    """승격한 안전 산업어는 결정적으로 인식돼야 한다(로봇 미인식 버그 회귀 방지)."""
    term_map = _term_to_canonicals()
    for term in NL_SAFE_TERMS:
        expected = next(iter(term_map[term]))
        assert normalize_sector(term) == expected, f"{term!r} 미인식/오인식"


def test_robot_sector_now_resolves_without_unsupported_notice():
    """실측 버그 회귀: '로봇 섹터도 추가해줘'가 인식되고 미지원 안내가 뜨지 않는다.

    (2026-07-13 로봇이 기계/장비 동의어에서 독립 정본 섹터로 승격 — 사명 기준 분류.)"""
    from engine.nl_parser import _extract_sector, build_unsupported_concept_notice

    assert _extract_sector("로봇 섹터도 추가해줘") == "로봇"
    assert _extract_sector("로보틱스 관련주") == "로봇"
    assert _extract_sector("공장자동화 관련 종목") == "기계/장비"
    assert build_unsupported_concept_notice("로봇 섹터도 추가해줘") is None


def test_generic_industry_words_stay_unrecognized():
    """분류표엔 있지만 일반어라 NL 인식에 넣으면 거짓 양성이 나는 용어는 미인식이어야 한다.

    (예: '투자'→증권/보험, '금속'→화학, '설비/장비/데이터'). 이들은 '투자금 1억으로'
    같은 비섹터 문장을 섹터 필터로 오인식시키므로 결정적 인식에서 반드시 빠져야 한다.
    """
    from engine.nl_parser import _extract_sector

    for word in ["투자", "금속", "설비", "장비", "데이터", "소재", "발전", "서비스", "제조업", "가공"]:
        assert normalize_sector(word) is None, f"{word!r}가 섹터로 인식됨(거짓 양성 위험)"
    # 실제 비섹터 문장이 섹터로 오인식되지 않는다.
    assert _extract_sector("투자금 1억으로 바꿔줘") is None
    assert _extract_sector("데이터 3년 백테스트") is None
