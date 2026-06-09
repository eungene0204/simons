"""Symbol resolver 테스트 — 종목명 추출."""

from __future__ import annotations

import pytest

from stock_analysis.symbol_resolver import find_in_text


def test_sk_hynix_not_confused_with_inix():
    # 이닉스는 SK하이닉스에 substring으로 포함되지만, 단어 경계를 고려해 구분된다.
    refs = find_in_text("SK하이닉스 사도 될까?")
    assert len(refs) == 1
    assert refs[0].symbol == "000660"
    assert refs[0].name == "SK하이닉스"


def test_inix_alone_is_recognized():
    refs = find_in_text("이닉스 관심 있어")
    assert len(refs) == 1
    assert refs[0].symbol == "452400"
    assert refs[0].name == "이닉스"


def test_both_found_when_both_mentioned():
    refs = find_in_text("SK하이닉스와 이닉스 중 뭐가 나아?")
    assert len(refs) == 2
    symbols = {r.symbol for r in refs}
    assert "000660" in symbols  # SK하이닉스
    assert "452400" in symbols  # 이닉스


def test_samsung_electronics_recognized():
    refs = find_in_text("지금 삼성전자 사도 될까?")
    assert len(refs) == 1
    assert refs[0].symbol == "005930"
    assert refs[0].name == "삼성전자"


def test_no_match_returns_empty():
    refs = find_in_text("요즘 시장 어떤 느낌이야?")
    assert len(refs) == 0


def test_numeric_code_matched():
    refs = find_in_text("000660 살까?")
    assert len(refs) == 1
    assert refs[0].symbol == "000660"


def test_case_insensitive_matching():
    # 소문자도 매칭되어야 함
    refs = find_in_text("sk하이닉스는 어떠?")
    assert len(refs) == 1
    assert refs[0].symbol == "000660"
    assert refs[0].name == "SK하이닉스"  # 원본 이름은 대문자


def test_case_insensitive_with_josa():
    # 소문자 + 조사도 매칭
    refs = find_in_text("삼성전자는 어때?")
    assert len(refs) == 1
    assert refs[0].symbol == "005930"
