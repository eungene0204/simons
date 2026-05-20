"""Tests for news_v2.dedup — title normalization + hashing."""

from news_v2.dedup import (
    cosine,
    is_duplicate,
    near_duplicate,
    normalize_title,
    title_hash,
)


def test_normalize_strips_bracket_prefix():
    assert normalize_title("[속보] 삼성전자, 분기 최대 매출") == "삼성전자 분기 최대 매출"


def test_normalize_strips_agency_prefix():
    assert normalize_title("속보: SK하이닉스 신고가 경신") == "sk하이닉스 신고가 경신"


def test_normalize_collapses_whitespace_and_punct():
    assert normalize_title("삼성전자!!  분기  ‘최대’ 매출.") == "삼성전자 분기 최대 매출"


def test_normalize_empty():
    assert normalize_title("") == ""
    assert normalize_title("   ") == ""


def test_title_hash_is_stable_and_64hex():
    h = title_hash("삼성전자 분기 최대 매출")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    assert h == title_hash("삼성전자 분기 최대 매출")


def test_is_duplicate_across_noise():
    a = "[속보] 삼성전자, 분기 최대 매출 기록"
    b = "속보: 삼성전자 분기 최대 매출 기록!!!"
    assert is_duplicate(a, b)


def test_is_not_duplicate_when_meaning_differs():
    assert not is_duplicate("삼성전자 분기 최대 매출", "삼성전자 분기 적자 전환")


def test_cosine_identical():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_orthogonal():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_zero_vectors():
    assert cosine([], [1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_near_duplicate_threshold():
    assert near_duplicate([1.0, 0.0], [0.99, 0.05], threshold=0.92)
    assert not near_duplicate([1.0, 0.0], [0.5, 0.8], threshold=0.92)
