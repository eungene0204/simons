"""
engine/sector_mapper.get_sector_from_industry() 회귀 테스트.

2026-07-05 사고: KRX KIND 업종 데이터에서 지주회사(홀딩스)는 실제 영위 사업과
무관하게 "기타 금융업"/"회사 본부 및 경영 컨설팅 서비스업"으로 등록되는데,
과거 매핑 규칙의 "지주"/"기타 금융" 키워드가 이를 그대로 잡아 SK·GS·한진칼·
롯데지주 등 산업 지주회사 191개가 전부 "은행/금융지주"로 잘못 표시되었다.
"메리츠화재"처럼 회사명에 "리츠"가 우연히 포함되어 "부동산"으로 오분류되는
문제도 함께 발견되어 수정했다.
"""

from engine.sector_mapper import get_sector_from_industry


def test_industrial_holding_company_is_not_bank_or_financial_holding():
    """산업 지주회사는 은행/금융지주가 아니라 지주회사로 분류되어야 한다."""
    for symbol, name in [
        ("034730", "SK"),
        ("078930", "GS"),
        ("180640", "한진칼"),
        ("004990", "롯데지주"),
        ("001040", "CJ"),
        ("003550", "LG"),
    ]:
        assert get_sector_from_industry(symbol, "기타 금융업", name) == "지주회사"


def test_genuine_financial_holding_company_stays_bank_sector():
    """실제 은행/금융 지주회사는 은행/금융지주로 유지되어야 한다 (OVERRIDDEN_SYMBOLS)."""
    for symbol, name in [
        ("316140", "우리금융지주"),
        ("055550", "신한지주"),
        ("105560", "KB금융"),
        ("086790", "하나금융지주"),
        ("138040", "메리츠금융지주"),
    ]:
        assert get_sector_from_industry(symbol, "기타 금융업", name) == "은행/금융지주"


def test_securities_and_brokerage_industry_text_routes_to_securities_sector():
    """'금융 지원 서비스업'(증권사 KSIC 텍스트)은 은행/금융지주가 아니라 증권/보험으로 분류되어야 한다."""
    assert get_sector_from_industry("039490", "금융 지원 서비스업", "키움증권") == "증권/보험"
    assert get_sector_from_industry("006800", "금융 지원 서비스업", "미래에셋증권") == "증권/보험"


def test_venture_capital_named_with_investment_keyword_routes_to_securities_sector():
    assert get_sector_from_industry("041190", "기타 금융업", "우리기술투자") == "증권/보험"
    assert get_sector_from_industry("023760", "기타 금융업", "한국캐피탈") == "증권/보험"


def test_reit_suffix_does_not_collide_with_meritz_group_name():
    """'메리츠'는 '리츠'를 부분 문자열로 포함하지만 REIT가 아니므로 부동산으로 분류되면 안 된다."""
    assert get_sector_from_industry("000060", None, "메리츠화재") != "부동산"
    assert get_sector_from_industry("138040", "기타 금융업", "메리츠금융지주") != "부동산"


def test_real_reit_company_name_suffix_maps_to_real_estate():
    for symbol, name in [
        ("395400", "SK리츠"),
        ("330590", "롯데리츠"),
        ("293940", "신한알파리츠"),
    ]:
        assert get_sector_from_industry(symbol, None, name) == "부동산"


def test_manufacturing_industry_text_is_not_downgraded_to_generic_service():
    """'OO 제조업'은 '업'으로 끝나지만 서비스가 아니라 기타 제조업으로 남아야 한다."""
    assert get_sector_from_industry("000000", "가정용 기기 제조업", "테스트가전") == "기타 제조업"
    assert get_sector_from_industry("000000", "무기 및 총포탄 제조업", "테스트회사") == "기타 제조업"


def test_non_manufacturing_service_industry_falls_back_to_other_service():
    assert get_sector_from_industry("000000", "경비, 경호 및 탐정업", "테스트경비") == "기타 서비스"
