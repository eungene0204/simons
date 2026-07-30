"""표준산업분류(KSIC) 코드 기반 섹터 분류 회귀 — 사명 문자열 매칭 대체.

종전 분류는 KRX 업종 문자열 + **사명**을 이어붙여 키워드 부분 문자열 매칭을 했다.
메"가스"터디교육이 '가스'에 걸려 에너지/원자력이 되고, 사명에 '바이오'만 있으면
동물사료 회사가 바이오/제약이 되던 사고를 코드 기반으로 대체했다(2026-07-30).
"""

from __future__ import annotations

import pytest

from engine.ksic_sectors import KSIC_SECTOR, sector_for_code, sector_for_symbol
from engine.sector_mapper import MAPPING_RULES, get_sector_from_industry
from engine.universe_pit import CANONICAL_SECTORS


def test_table_only_references_canonical_sectors():
    unknown = {s for s in KSIC_SECTOR.values() if s not in CANONICAL_SECTORS}
    assert not unknown, f"정본 목록에 없는 섹터: {sorted(unknown)}"


@pytest.mark.parametrize(
    "code, expected",
    [
        ("20423", "화장품"),      # 화장품 제조업 — KRX 문자열은 '기타 화학제품'까지만 준다
        ("204", "화학"),          # 상위 분류는 화학 (하위 20423이 선점)
        ("2621", "디스플레이"),    # 표시장치 제조업
        ("262", "전자부품"),       # 상위 분류는 전자부품
        ("501", "해운"),          # 해상 운송업
        ("6491", "증권"),         # 신탁업 및 집합투자업 — 지주회사 아님
    ],
)
def test_longest_prefix_wins(code, expected):
    assert sector_for_code(code) == expected


@pytest.mark.parametrize("code", ["", None, "999", "  "])
def test_unknown_code_returns_none(code):
    assert sector_for_code(code) is None


@pytest.mark.parametrize(
    "symbol, name, industry, expected",
    [
        # 사명 부분 문자열 사고 — 메"가스"터디의 '가스'가 에너지/원자력에 걸리던 케이스
        ("215200", "메가스터디교육", "일반 교습 학원", "교육"),
        # 사명 '바이오' 오매칭 — 동물사료 회사가 바이오/제약이 되던 케이스
        ("353810", "이지바이오", "동물용 사료 및 조제식품 제조업", "사료"),
        # 해상운송이 운송/물류에 있던 케이스
        ("028670", "팬오션", "해상 운송업", "해운"),
        # 사명 '에너지'가 아니라 실제 등록 업종(화학)을 따른다
        ("011780", "금호석유화학", "기초 화학물질 제조업", "화학"),
    ],
)
def test_code_beats_name_substring(symbol, name, industry, expected):
    assert get_sector_from_industry(symbol, industry, name) == expected


def test_robot_still_classified_by_company_name():
    """로봇은 사명 기준 분류가 불가피하다 — 유일하게 남긴 예외.

    KSIC에 산업용 로봇 코드(2928)가 있기는 하지만 실제로 그 코드로 등록한 상장사는
    두산로보틱스 하나뿐이고, 나머지 로봇 기업은 일반 코드(292 특수 목적용 기계)로
    등록돼 있다 — 코드만으로는 기계/장비와 갈리지 않는다."""
    # 일반 코드로 등록한 로봇 기업: 코드로는 기계/장비, 사명 규칙이 로봇으로 잡는다
    assert sector_for_symbol("079900") == "기계/장비"        # 전진건설로봇 (KSIC 292)
    assert get_sector_from_industry("079900", "특수 목적용 기계 제조업", "전진건설로봇") == "로봇"
    # 산업용 로봇 코드(2928)로 등록한 기업은 코드만으로도 로봇이다
    assert sector_for_symbol("454910") == "로봇"             # 두산로보틱스


def test_symbol_override_beats_code():
    """개별 오버라이드가 코드보다 우선한다 — 등록 업종이 실제 주력과 다른 예외."""
    assert sector_for_symbol("005930") == "IT 하드웨어"  # DART 등록 = 통신·방송장비
    assert get_sector_from_industry("005930", "반도체", "삼성전자") == "반도체"


def test_name_matching_is_limited_to_robot():
    """사명 기준 선점은 로봇 하나뿐이어야 한다 — 다른 섹터를 추가하면
    메가스터디 유형의 부분 문자열 사고가 되살아난다."""
    import inspect

    source = inspect.getsource(get_sector_from_industry)
    priority = source.split("② 표준산업분류")[0]
    for sector in ("에너지/원자력", "바이오/제약", "소프트웨어", "교육"):
        assert f'"{sector}"' not in priority, f"{sector}가 사명 선점 구간에 있다"


def test_energy_vocab_no_longer_hijacks_names():
    """'가스'·'전기' 같은 짧은 일반어가 사명 안에서 우연히 걸리면 안 된다."""
    assert "가스" in MAPPING_RULES["에너지/원자력"]  # 어휘 자체는 유지(산업분류 문자열용)
    assert get_sector_from_industry("215200", "일반 교습 학원", "메가스터디교육") != "에너지/원자력"
