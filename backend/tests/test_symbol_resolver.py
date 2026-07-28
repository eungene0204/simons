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


def test_fuzzy_suggests_correct_stock_via_jamo_distance():
    # [FR-STR-068 오타] '삼서전자'(서↔성=종성 ㅇ 차이)는 자모거리로 삼성전자(1)가
    # 삼지전자(2)를 앞서 정답을 고른다 — 문자단위 difflib은 삼지전자를 오선택하던 함정.
    from stock_analysis.symbol_resolver import suggest_similar_stocks
    assert [r.name for r in suggest_similar_stocks("삼서전자")] == ["삼성전자"]
    assert [r.name for r in suggest_similar_stocks("카키오")] == ["카카오"]
    # 통칭(_KOREAN_ALIASES)의 오타도 등록명으로 정정한다('현디차'→현대차→현대자동차).
    assert [r.name for r in suggest_similar_stocks("현디차")] == ["현대자동차"]


def test_fuzzy_rejects_non_typos_and_vocab():
    # 확신 없는 후보는 반환하지 않는다 — 전략 어휘·업종어·짧은 토큰의 오발동 방지.
    from stock_analysis.symbol_resolver import suggest_similar_stocks
    for q in ["전략", "우량주", "저평가", "골든크로스", "모멘텀", "반도체", "포스크", "엘지화학"]:
        assert suggest_similar_stocks(q) == [], q


def test_detect_symbol_typo_clarification_reasks():
    from engine.nl_parser import detect_symbol_typo_clarification, ParsedStrategy
    q, chips = detect_symbol_typo_clarification(ParsedStrategy(description="x"), "삼서전자 전략을 만들자")
    assert q is not None and "삼성전자" in q
    assert chips == ["삼성전자 전략을 만들자"]  # 오타 토큰만 정정한 재제출 프롬프트
    # 조사가 붙은 토큰도 벗겨 매칭하고, 칩은 토큰 전체를 정정한다.
    q2, chips2 = detect_symbol_typo_clarification(ParsedStrategy(description="x"), "카키오로 골든크로스 전략")
    assert chips2 == ["카카오 골든크로스 전략"]


def test_detect_symbol_typo_no_reask_on_valid_input():
    from engine.nl_parser import detect_symbol_typo_clarification, ParsedStrategy
    # 정확 매칭 종목·업종·순수 전략 어휘는 되묻지 않는다.
    for t in ["삼성전자 전략을 만들자", "2차전지 전략을 만들자",
              "골든크로스 전략 만들어줘", "PBR 1 이하 저평가 종목"]:
        q, _ = detect_symbol_typo_clarification(ParsedStrategy(description="x"), t)
        assert q is None, t
    # 이미 종목이 해석된 경우(target_symbols)도 되묻지 않는다.
    q, _ = detect_symbol_typo_clarification(
        ParsedStrategy(description="x", target_symbols=["005930"]), "삼서전자 전략"
    )
    assert q is None


def test_symbol_typo_reask_skipped_for_etf_universe():
    """ETF 유니버스엔 '종목명'이 없다 — 자모 근접 매칭 되묻기는 전부 오발동이다.

    실측 사고(2026-07-27): "배당 ETF 중에서 …20일선을 이탈하면 청산" 요청이 '오아'·'일승'
    종목 오타 되묻기로 빠졌다(테마는 etf_theme로 이미 해석된 상태).
    """
    from engine.nl_parser import ParsedStrategy, detect_symbol_typo_clarification

    prompt = "배당 ETF 중에서 종가가 20일 이동평균선 위에 있는 상품만 4종목 담고 싶어요"
    q_stock, _ = detect_symbol_typo_clarification(
        ParsedStrategy(description="x", universe=["KOSPI"]), "카키오로 골든크로스 전략"
    )
    assert q_stock is not None  # 주식 유니버스에선 기존 동작 유지

    q_etf, chips = detect_symbol_typo_clarification(
        ParsedStrategy(description="x", universe=["ETF"], etf_theme="배당"), prompt
    )
    assert q_etf is None and chips is None
