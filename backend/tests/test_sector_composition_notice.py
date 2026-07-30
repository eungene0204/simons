"""묶음 섹터 구성 안내(2026-07-30) — 조건이 조용히 넓어지는 것을 막는다.

사용자가 묶음 섹터의 한쪽('원자력')을 말하면 그 업종이 따로 없다는 사실과 함께 무엇이
같이 들어 있는지 밝힌다. 종전에는 아무 말 없이 72종목(정유·도시가스 포함)을 줬다.
"""

from __future__ import annotations

import pytest

from engine.universe_pit import (
    CANONICAL_SECTORS,
    SECTOR_COMPOSITION_NOTES,
    filter_by_sector,
    is_narrow_sector_approximation,
    normalize_sector,
    sector_composition_notice,
    _load_sector_map,
)

# 묶음 섹터의 '한쪽만' 부르는 표현 — 전부 넓어짐으로 감지돼야 한다.
HALF_TERMS = [
    ("원자력", "에너지/원자력"),
    ("에너지", "에너지/원자력"),
    ("미디어", "미디어/엔터"),
    ("엔터", "미디어/엔터"),
    ("철강", "철강/금속"),
    ("기계", "기계/장비"),
    ("통신", "통신/유틸리티"),
    ("물류", "운송/물류"),
]


@pytest.mark.parametrize("term, expected_sector", HALF_TERMS)
def test_half_of_combined_sector_is_flagged_as_widening(term, expected_sector):
    """묶음의 한쪽만 말하면 개념이 넓어진다 — 글자가 정본명에 들어 있어도 마찬가지.
    2026-07-30 이전에는 '원자력'⊂'에너지원자력'이라는 이유로 False였다."""
    assert normalize_sector(term) == expected_sector
    assert is_narrow_sector_approximation(term) is True


@pytest.mark.parametrize(
    "term",
    ["반도체", "증권", "보험", "은행", "조선", "해운", "로봇", "건설", "화장품", "패션", "디스플레이", "전자부품"],
)
def test_canonical_sector_names_are_not_flagged(term):
    """정본 섹터명 그대로면 넓어지지 않는다(오탐 방지)."""
    assert is_narrow_sector_approximation(term) is False
    assert sector_composition_notice(term) is None


def test_non_name_approximation_still_flagged():
    """정본명에 글자가 없는 근사('태양광'→에너지/원자력)는 기존대로 감지된다."""
    assert is_narrow_sector_approximation("태양광") is True


def test_unknown_term_is_not_flagged():
    assert is_narrow_sector_approximation("듣도보도못한말") is False
    assert sector_composition_notice("듣도보도못한말") is None


@pytest.mark.parametrize("term, expected_sector", HALF_TERMS)
def test_notice_names_the_bundle_and_its_contents(term, expected_sector):
    notice = sector_composition_notice(term, count=42)
    assert notice is not None
    assert term in notice
    assert expected_sector in notice
    assert "42종목" in notice


def test_notice_without_count_omits_the_number():
    notice = sector_composition_notice("원자력")
    assert notice is not None and "종목" not in notice


@pytest.mark.parametrize("term, particle", [("원자력", "'원자력'은"), ("기계", "'기계'는")])
def test_topic_particle_matches_final_consonant(term, particle):
    assert particle in (sector_composition_notice(term) or "")


def test_every_remaining_combined_sector_has_a_note():
    """묶음 섹터가 남아 있으면 반드시 구성 안내가 있어야 한다 —
    새 묶음 섹터를 추가하고 안내를 빠뜨리면 조용히 넓어지는 경로가 다시 생긴다."""
    combined = {s for s in CANONICAL_SECTORS if "/" in s}
    assert combined, "묶음 섹터가 하나도 없다면 이 가드는 갱신돼야 한다"
    assert combined <= set(SECTOR_COMPOSITION_NOTES), (
        f"구성 안내 누락: {sorted(combined - set(SECTOR_COMPOSITION_NOTES))}"
    )


def test_notes_do_not_describe_split_sectors():
    """분할이 끝난 섹터에는 구성 안내가 남아 있으면 안 된다(낡은 문구 방지)."""
    for sector in SECTOR_COMPOSITION_NOTES:
        assert sector in CANONICAL_SECTORS, f"{sector}는 더 이상 정본 섹터가 아니다"


def test_nuclear_notice_warns_about_oil_and_gas():
    """실제 사고 재현: '원자력'을 물으면 정유·도시가스가 섞여 있음을 밝혀야 한다."""
    notice = sector_composition_notice("원자력", count=len(filter_by_sector(list(_load_sector_map()), "원자력")))
    assert notice is not None
    assert "정유" in notice and "도시가스" in notice
