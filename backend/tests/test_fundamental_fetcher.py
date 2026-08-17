"""
fundamental_fetcher 모듈 유닛 테스트.
Naver Finance 스크래핑 없이 파싱/enrichment 로직을 검증한다.
"""

import pandas as pd
import pytest

import engine.fundamental_fetcher as ff_mod
from engine.fundamental_fetcher import (
    _compute_derived_annual_metrics,
    _fetch_cash_flow_from_dart,
    _merge_fundamental_records,
    _parse_dart_activity_cash_flow,
    _parse_dart_capex,
    _parse_dart_operating_cash_flow,
    _parse_dart_owner_net_income,
    _parse_dart_total_equity,
    _parse_kis_financial_ratio_output,
    _parse_kis_income_statement,
    _parse_fundamentals,
    _parse_number,
    _read_cache,
    _write_cache,
    _is_recently_confirmed_empty,
    _write_negative_cache,
    enrich_ohlcv_with_fundamentals,
    fetch_fundamentals,
)

# ── _parse_number ──

def test_parse_number_normal():
    assert _parse_number("52,002") == 52002.0

def test_parse_number_negative():
    assert _parse_number("-12,517") == -12517.0

def test_parse_number_empty():
    assert _parse_number("") is None

def test_parse_number_dash():
    assert _parse_number("-") is None

def test_parse_number_no_comma():
    assert _parse_number("6564") == 6564.0


# ── _parse_fundamentals ──

_SAMPLE_HTML = """
<html><body>
<table>
<tr><th>주요재무정보</th><th colspan="4">최근 연간 실적</th><th colspan="6">최근 분기 실적</th></tr>
<tr><td>2023.12</td><td>2024.12</td><td>2025.12</td><td>2026.12(E)</td>
    <td>2024.12</td><td>2025.03</td><td>2025.06</td><td>2025.09</td><td>2025.12</td><td>2026.03(E)</td></tr>
<tr><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td>
    <td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td><td>IFRS연결</td></tr>
<tr><td>매출액</td><td>100</td><td>200</td><td>300</td><td>400</td>
    <td>50</td><td>55</td><td>60</td><td>65</td><td>70</td><td>75</td></tr>
<tr><td>ROE(지배주주)</td><td>4.15</td><td>9.03</td><td>10.85</td><td>44.98</td>
    <td>9.03</td><td>9.03</td><td>9.03</td><td>9.03</td><td>9.03</td><td></td></tr>
<tr><td>부채비율</td><td>25.10</td><td>30.20</td><td>35.30</td><td>40.40</td>
    <td>30.20</td><td>30.20</td><td>30.20</td><td>30.20</td><td>30.20</td><td></td></tr>
<tr><td>EPS(원)</td><td>2,131</td><td>4,950</td><td>6,564</td><td>36,119</td>
    <td>1,115</td><td>1,186</td><td>733</td><td>1,783</td><td>2,864</td><td>5,298</td></tr>
<tr><td>BPS(원)</td><td>52,002</td><td>57,981</td><td>63,997</td><td>99,649</td>
    <td>57,981</td><td>59,059</td><td>58,135</td><td>60,632</td><td>63,997</td><td></td></tr>
</table>
</body></html>
"""


def test_parse_fundamentals_extracts_annual_data():
    result = _parse_fundamentals(_SAMPLE_HTML)
    assert result is not None
    assert len(result) == 3  # 2023.12, 2024.12, 2025.12 (2026.12(E) 제외)

    # 2023.12
    assert result[0]["year_end"] == "2023-12-31"
    assert result[0]["eps"] == 2131.0
    assert result[0]["bps"] == 52002.0

    # 2024.12
    assert result[1]["year_end"] == "2024-12-31"
    assert result[1]["eps"] == 4950.0
    assert result[1]["bps"] == 57981.0

    # 2025.12
    assert result[2]["year_end"] == "2025-12-31"
    assert result[2]["eps"] == 6564.0
    assert result[2]["bps"] == 63997.0


def test_parse_fundamentals_excludes_estimates():
    result = _parse_fundamentals(_SAMPLE_HTML)
    # 2026.12(E) 포함되지 않아야 함
    year_ends = [r["year_end"] for r in result]
    assert "2026-12-31" not in year_ends


def test_parse_fundamentals_no_table():
    html = "<html><body><p>No data</p></body></html>"
    assert _parse_fundamentals(html) is None


# ── _parse_kis_financial_ratio_output ──

def test_parse_kis_financial_ratio_output_extracts_roe_eps_bps():
    result = _parse_kis_financial_ratio_output([
        {
            "stac_yymm": "202512",
            "roe_val": "10.85",
            "eps": "6564.00",
            "bps": "63997.00",
            "lblt_rate": "35.30",
        },
        {
            "stac_yymm": "202412",
            "roe_val": "9.03",
            "eps": "4950.00",
            "bps": "57981.00",
            "lblt_rate": "30.20",
        },
    ])

    assert result == [
        {"year_end": "2025-12-31", "eps": 6564.0, "bps": 63997.0, "roe_or_gpa": 10.85, "debt_ratio": 35.3},
        {"year_end": "2024-12-31", "eps": 4950.0, "bps": 57981.0, "roe_or_gpa": 9.03, "debt_ratio": 30.2},
    ]


# ── _parse_kis_income_statement (영업이익률) ──

def test_parse_kis_income_statement_computes_operating_margin():
    # 영업이익률 = 영업이익(bsop_prti) / 매출액(sale_account) * 100
    result = _parse_kis_income_statement([
        {"stac_yymm": "202512", "sale_account": "3007700.00", "bsop_prti": "326600.00"},
        {"stac_yymm": "202412", "sale_account": "2589900.00", "bsop_prti": "65700.00"},
    ])
    assert result == {
        "2025-12-31": {"operating_margin": 10.86, "ebit": 326600.0, "_revenue": 3007700.0},
        "2024-12-31": {"operating_margin": 2.54, "ebit": 65700.0, "_revenue": 2589900.0},
    }


def test_parse_kis_income_statement_skips_zero_or_missing_sales():
    result = _parse_kis_income_statement([
        {"stac_yymm": "202312", "sale_account": "0.00", "bsop_prti": "100.0"},  # 매출 0 → 스킵
        {"stac_yymm": "202212", "sale_account": "1000.0", "bsop_prti": ""},      # 영업이익 결측 → 스킵
    ])
    assert result == {}


# ── OpenDART PCR source parsing ──

def test_parse_dart_operating_cash_flow_prefers_canonical_account():
    result = _parse_dart_operating_cash_flow([
        {
            "sj_div": "CF",
            "account_id": "dart_AdjustmentsForAssetsLiabilitiesOfOperatingActivities",
            "account_nm": "영업활동으로 인한 자산부채의 변동",
            "thstrm_amount": "1,000",
            "rcept_no": "20250311001085",
        },
        {
            "sj_div": "CF",
            "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
            "account_nm": "영업활동 현금흐름",
            "thstrm_amount": "73,000,000,000,000",
            "rcept_no": "20250311001085",
        },
    ])

    assert result == {
        "operating_cash_flow": 73_000_000_000_000.0,
        "available_from": "2025-03-11",
    }


# ── OpenDART CAPEX / 자본총계 source parsing (실측: 2026-07-21, 삼성전자 fnlttSinglAcntAll.json) ──

_DART_CF_BS_FIXTURE = [
    {
        "sj_div": "CF",
        "account_id": "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "account_nm": "유형자산의 취득",
        "thstrm_amount": "57,611,292,000,000",
    },
    {
        "sj_div": "CF",
        "account_id": "ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
        "account_nm": "무형자산의 취득",
        "thstrm_amount": "2,922,875,000,000",
    },
    {
        "sj_div": "CF",
        "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
        "account_nm": "영업활동현금흐름",
        "thstrm_amount": "44,137,427,000,000",
    },
    {
        "sj_div": "BS",
        "account_id": "ifrs-full_Equity",
        "account_nm": "자본총계",
        "thstrm_amount": "363,677,865,000,000",
    },
    {
        "sj_div": "BS",
        "account_id": "ifrs-full_EquityAttributableToOwnersOfParent",
        "account_nm": "지배기업 소유주지분",
        "thstrm_amount": "353,233,775,000,000",
    },
]


def test_parse_dart_capex_sums_ppe_and_intangible_purchases():
    assert _parse_dart_capex(_DART_CF_BS_FIXTURE) == pytest.approx(60_534_167_000_000.0)


def test_parse_dart_capex_missing_returns_none():
    assert _parse_dart_capex([{"sj_div": "CF", "account_id": "other", "account_nm": "기타"}]) is None


def test_parse_dart_total_equity_reads_equity_not_parent_attributable():
    assert _parse_dart_total_equity(_DART_CF_BS_FIXTURE) == pytest.approx(363_677_865_000_000.0)


def test_parse_dart_total_equity_preserves_negative_sign_for_capital_impairment():
    rows = [{"sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계", "thstrm_amount": "-5,000,000"}]
    assert _parse_dart_total_equity(rows) == pytest.approx(-5_000_000.0)


def test_fetch_cash_flow_from_dart_falls_back_to_separate_statements(monkeypatch):
    import engine.fundamental_fetcher as ff

    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00126380")
    monkeypatch.setattr(ff, "dart_fiscal_month", lambda symbol, corp_code: "12")

    def fake_fetch(path, params):
        if path == "list.json":
            return {"status": "013"}  # 원공시 접수일 조회 실패 → 클램프 생략 경로
        if path == "fnlttSinglAcntAll.json" and params["fs_div"] == "CFS":
            return {"status": "013"}
        if path == "fnlttSinglAcntAll.json":
            return {
                "status": "000",
                "list": [{
                    "sj_div": "CF",
                    "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
                    "account_nm": "영업활동현금흐름",
                    "thstrm_amount": "100,000",
                    "rcept_no": "20250331000001",
                }],
            }
        raise AssertionError(f"unexpected DART path: {path}")

    monkeypatch.setattr(ff, "_fetch_dart_json", fake_fetch)

    assert _fetch_cash_flow_from_dart("005930", 2024, 2024) == [{
        "year_end": "2024-12-31",
        "available_from": "2025-03-31",
        "operating_cash_flow": 100_000.0,
    }]


def test_fetch_cash_flow_from_dart_also_captures_capex_and_total_equity(monkeypatch):
    """같은 fnlttSinglAcntAll.json 응답에서 CAPEX·자본총계도 추가 API 호출 없이 함께 담긴다."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00126380")

    fixture_with_receipt = [{**row, "rcept_no": "20250331000001"} for row in _DART_CF_BS_FIXTURE]

    def fake_fetch(path, params):
        return {"status": "000", "list": fixture_with_receipt}

    monkeypatch.setattr(ff, "_fetch_dart_json", fake_fetch)

    result = _fetch_cash_flow_from_dart("005930", 2024, 2024)
    assert result == [{
        "year_end": "2024-12-31",
        "available_from": "2025-03-31",
        "operating_cash_flow": 44_137_427_000_000.0,
        "capex": pytest.approx(60_534_167_000_000.0),
        "total_equity": pytest.approx(363_677_865_000_000.0),
    }]


# ── OpenDART 지배주주순이익 (실측: 2026-08-06, 12종목 2023년 fnlttSinglAcntAll.json) ──
#
# 표기 실측: 계정ID는 12/12 동일하지만 account_nm은 "지배기업의 소유주에게 귀속되는
# 당기순이익(손실)"(삼성전자)·"지배기업소유주지분"(현대차)·"지배기업소유주"(클래시스)·
# "지배주주순이익"(엔씨소프트)으로 갈리고, 섹션도 IS 5 / CIS 7로 갈렸다.
_DART_OWNER_NET_INCOME_IS_ROW = {
    "sj_div": "IS",
    "account_id": "ifrs-full_ProfitLossAttributableToOwnersOfParent",
    "account_nm": "지배기업의 소유주에게 귀속되는 당기순이익(손실)",
    "thstrm_amount": "14,473,401,000,000",
}
# SK하이닉스 실측: 같은 CIS 섹션 안에서 '당기순이익 귀속'과 '총포괄손익 귀속'이 사실상
# 같은 이름을 쓴다 — 이름으로 매칭하면 포괄손익을 순이익으로 오인한다.
_DART_OWNER_CIS_FIXTURE = [
    {
        "sj_div": "CIS",
        "account_id": "ifrs-full_ProfitLossAttributableToOwnersOfParent",
        "account_nm": "지배기업의 소유주지분",
        "thstrm_amount": "-9,112,428,000,000",
    },
    {
        "sj_div": "CIS",
        "account_id": "ifrs-full_ComprehensiveIncomeAttributableToOwnersOfParent",
        "account_nm": "지배기업 소유주지분",
        "thstrm_amount": "-8,000,000,000,000",
    },
]


def test_parse_dart_owner_net_income_reads_income_statement_section():
    assert _parse_dart_owner_net_income(
        [*_DART_CF_BS_FIXTURE, _DART_OWNER_NET_INCOME_IS_ROW]
    ) == pytest.approx(14_473_401_000_000.0)


def test_parse_dart_owner_net_income_reads_comprehensive_income_section():
    """제출본에 따라 CIS 섹션에 실린다 — 두 섹션 모두 인정해야 한다(적자면 음수 보존)."""
    assert _parse_dart_owner_net_income(_DART_OWNER_CIS_FIXTURE) == pytest.approx(
        -9_112_428_000_000.0
    )


def test_parse_dart_owner_net_income_ignores_comprehensive_income_row():
    """이름이 거의 같은 '총포괄손익 귀속' 행을 순이익으로 오인하면 안 된다(계정ID 정확 일치)."""
    only_comprehensive = [_DART_OWNER_CIS_FIXTURE[1]]
    assert _parse_dart_owner_net_income(only_comprehensive) is None


def test_parse_dart_owner_net_income_accepts_legacy_taxonomy_prefix():
    """2018년 사업보고서까지는 계정ID 접두가 'ifrs_'다 — 신형만 보면 2015~2018이 조용히
    결측된다(삼성전자 실측: 2018=ifrs_, 2019=ifrs-full_)."""
    legacy = [{
        "sj_div": "IS",
        "account_id": "ifrs_ProfitLossAttributableToOwnersOfParent",
        "account_nm": "지배기업의 소유주에게 귀속되는 당기순이익(손실)",
        "thstrm_amount": "43,890,877,000,000",
    }]
    assert _parse_dart_owner_net_income(legacy) == pytest.approx(43_890_877_000_000.0)


def test_parse_dart_owner_net_income_ignores_legacy_comprehensive_income_row():
    """구 택소노미에서도 총포괄손익 귀속 행(ifrs_ComprehensiveIncome…)은 잡지 않는다."""
    legacy_comprehensive = [{
        "sj_div": "CIS",
        "account_id": "ifrs_ComprehensiveIncomeAttributableToOwnersOfParent",
        "account_nm": "지배기업 소유주지분",
        "thstrm_amount": "43,882,473,000,000",
    }]
    assert _parse_dart_owner_net_income(legacy_comprehensive) is None


def test_parse_dart_owner_net_income_missing_returns_none():
    """별도재무제표(OFS)에는 지배/비지배 구분 자체가 없어 결측이 정상이다."""
    assert _parse_dart_owner_net_income(_DART_CF_BS_FIXTURE) is None


# ── 정본 계정ID가 없는 제출본의 검산 구제 (실측: 2026-08-07, 90종목 표본 원인 분류) ──
#
# 검산 = 지배 + 비지배 = 당기순이익(ProfitLoss). 통과하지 못하면 결측으로 남긴다 —
# 이름이 비슷한 다른 개념(총포괄손익·중단영업 있는 계속영업손익)을 몰래 넣지 않기 위함이다.

def _row(sj_div, account_id, account_nm, amount):
    return {"sj_div": sj_div, "account_id": account_id,
            "account_nm": account_nm, "thstrm_amount": amount}


def test_parse_dart_owner_net_income_accepts_continuing_ops_when_checksum_holds():
    """부국증권 2024 실측 — 중단영업이 없으면 계속영업손익 귀속 = 당기순이익 귀속."""
    rows = [
        _row("CIS", "ifrs-full_IncomeFromContinuingOperationsAttributableToOwnersOfParent",
             "1. 지배기업의 소유주에게 귀속될 계속영업손익", "30,945,550,007"),
        _row("CIS", "ifrs-full_ProfitLossFromContinuingOperationsAttributableToNoncontrollingInterests",
             "2. 비지배지분에 귀속될 계속영업손익", "7,004,743"),
        _row("CIS", "ifrs-full_ProfitLoss", "VIII. 당기순이익", "30,952,554,750"),
    ]
    assert _parse_dart_owner_net_income(rows) == pytest.approx(30_945_550_007.0)


def test_parse_dart_owner_net_income_rejects_continuing_ops_when_discontinued_exists():
    """중단영업이 있어 합이 당기순이익과 어긋나면 개념이 다른 값이므로 채택하지 않는다."""
    rows = [
        _row("CIS", "ifrs-full_IncomeFromContinuingOperationsAttributableToOwnersOfParent",
             "지배기업의 소유주에게 귀속될 계속영업손익", "30,000,000,000"),
        _row("CIS", "ifrs-full_ProfitLossFromContinuingOperationsAttributableToNoncontrollingInterests",
             "비지배지분에 귀속될 계속영업손익", "1,000,000,000"),
        _row("CIS", "ifrs-full_ProfitLoss", "당기순이익", "45,000,000,000"),  # 중단영업 14조 포함
    ]
    assert _parse_dart_owner_net_income(rows) is None


def test_parse_dart_owner_net_income_accepts_continuing_ops_without_nci_row():
    """비지배 귀속 행이 아예 없으면 비지배=0이다 — 소유주 값 단독 검산(003530 실측)."""
    rows = [
        _row("CIS", "ifrs-full_IncomeFromContinuingOperationsAttributableToOwnersOfParent",
             "지배기업의 소유주에게 귀속되는 당기순이익", "102,010,000,000"),
        _row("CIS", "ifrs-full_ComprehensiveIncomeFromContinuingOperationsAttributableToOwnersOfParent",
             "지배기업의 소유주에게 귀속되는 당기총포괄이익", "361,220,000,000"),
        _row("CIS", "ifrs-full_ProfitLoss", "당기순이익", "102,010,000,000"),
    ]
    assert _parse_dart_owner_net_income(rows) == pytest.approx(102_010_000_000.0)


def test_parse_dart_owner_net_income_picks_untagged_pair_that_passes_checksum():
    """069330 실측 — 총포괄 쌍과 순이익 쌍이 계정ID 없이 나란히 실린다. 검산이 가른다."""
    rows = [
        _row("CIS", "-표준계정코드 미사용-", "지배기업소유주지분총포괄이익(손실)", "9,999,999,999"),
        _row("CIS", "-표준계정코드 미사용-", "비지배지분총포괄손익(손실)", "-1,111,111,111"),
        _row("CIS", "ifrs-full_ProfitLoss", "당기순이익(손실)", "1,285,612,509"),
        _row("CIS", "-표준계정코드 미사용-", "지배기업소유주지분순이익(손실)", "1,364,078,931"),
        _row("CIS", "ifrs-full_ProfitLossAttributableToNoncontrollingInterests",
             "비지배지분순이익(손실)", "-78,466,422"),
    ]
    assert _parse_dart_owner_net_income(rows) == pytest.approx(1_364_078_931.0)


def test_parse_dart_owner_net_income_rejects_untagged_comprehensive_only():
    """045660 실측 — 계정ID 없는 행이 총포괄 귀속뿐이면 합이 안 맞아 결측으로 남긴다."""
    rows = [
        _row("CIS", "-표준계정코드 미사용-", "지배기업소유주지분", "383,433,148"),
        _row("CIS", "-표준계정코드 미사용-", "비지배지분", "-57,998,878"),
        _row("CIS", "ifrs-full_ProfitLoss", "당기순이익", "393,882,122"),
    ]
    assert _parse_dart_owner_net_income(rows) is None


def test_parse_dart_owner_net_income_uses_profit_loss_when_no_minority_interest():
    """003690 실측 — 비지배지분이 없으면 귀속 행을 싣지 않는다(자본총계 = 지배기업소유주지분)."""
    rows = [
        _row("CIS", "ifrs-full_ProfitLoss", "당기순이익", "322,041,488,493"),
        _row("BS", "ifrs-full_Equity", "자본총계", "3,683,421,777,221"),
        _row("BS", "ifrs-full_EquityAttributableToOwnersOfParent", "지배주주지분", "3,683,421,777,221"),
    ]
    assert _parse_dart_owner_net_income(rows) == pytest.approx(322_041_488_493.0)


def test_parse_dart_owner_net_income_no_minority_accepts_explicit_zero_nci():
    """065370 실측 — 비지배지분을 0으로 명시한 제출본."""
    rows = [
        _row("CIS", "ifrs-full_ProfitLoss", "당기순이익", "1,454,510,181"),
        _row("BS", "ifrs-full_Equity", "자본총계", "30,864,651,221"),
        _row("BS", "ifrs-full_NoncontrollingInterests", "비지배지분", "0"),
    ]
    assert _parse_dart_owner_net_income(rows) == pytest.approx(1_454_510_181.0)


def test_parse_dart_owner_net_income_refuses_profit_loss_when_minority_exists():
    """비지배지분이 실재하는데 귀속 행이 없으면 지배분을 알 수 없다 — 총액으로 때우지 않는다."""
    rows = [
        _row("CIS", "ifrs-full_ProfitLoss", "당기순이익", "50,000,000,000"),
        _row("BS", "ifrs-full_Equity", "자본총계", "300,000,000,000"),
        _row("BS", "ifrs-full_NoncontrollingInterests", "비지배지분", "12,000,000,000"),
    ]
    assert _parse_dart_owner_net_income(rows) is None


def test_parse_dart_owner_net_income_prefers_canonical_over_checksum_fallback():
    """정본 계정ID가 있으면 검산 폴백을 타지 않는다(순서 회귀)."""
    rows = [
        _row("IS", "ifrs-full_ProfitLossAttributableToOwnersOfParent",
             "지배기업의 소유주에게 귀속되는 당기순이익(손실)", "14,473,401,000,000"),
        _row("IS", "ifrs-full_ProfitLoss", "당기순이익", "15,487,100,000,000"),
        _row("BS", "ifrs-full_NoncontrollingInterests", "비지배지분", "0"),
    ]
    assert _parse_dart_owner_net_income(rows) == pytest.approx(14_473_401_000_000.0)


def test_fetch_cash_flow_from_dart_also_captures_owner_net_income(monkeypatch):
    """같은 fnlttSinglAcntAll.json 응답에서 지배주주순이익도 추가 API 호출 없이 담긴다."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00126380")

    rows = [
        {**row, "rcept_no": "20250331000001"}
        for row in (*_DART_CF_BS_FIXTURE, _DART_OWNER_NET_INCOME_IS_ROW)
    ]
    monkeypatch.setattr(ff, "_fetch_dart_json", lambda path, params: {"status": "000", "list": rows})

    record = _fetch_cash_flow_from_dart("005930", 2024, 2024)[0]
    assert record["_owner_net_income_raw"] == pytest.approx(14_473_401_000_000.0)


def test_compute_derived_metrics_converts_owner_net_income_to_eok():
    """DART raw 원 단위 → 억원(금액 관례). 내부 키는 저장 레코드에 남지 않는다."""
    result = _compute_derived_annual_metrics(
        [{"year_end": "2023-12-31", "_owner_net_income_raw": 14_473_401_000_000.0}]
    )
    assert result[0]["owner_net_income"] == pytest.approx(144_734.0)
    assert "_owner_net_income_raw" not in result[0]


def test_compute_derived_metrics_owner_net_income_preserves_negative_sign():
    result = _compute_derived_annual_metrics(
        [{"year_end": "2023-12-31", "_owner_net_income_raw": -9_112_428_000_000.0}]
    )
    assert result[0]["owner_net_income"] == pytest.approx(-91_124.3)


def test_owner_net_income_is_distinct_from_consolidated_net_income():
    """net_income(연결 전체)과 owner_net_income(지배 귀속)은 서로 다른 지표다.

    삼성전자 2023 실측: 전체 154,843억 = 지배 144,734 + 비지배 10,137.
    한쪽이 다른 쪽을 덮어쓰면 지주회사에서 수천억~수조 단위로 어긋난다.
    """
    result = _compute_derived_annual_metrics([{
        "year_end": "2023-12-31",
        "net_margin": 5.98, "_revenue": 2_589_355.0,
        "_owner_net_income_raw": 14_473_401_000_000.0,
    }])
    assert result[0]["net_income"] == pytest.approx(154_843.4, abs=0.1)
    assert result[0]["owner_net_income"] == pytest.approx(144_734.0)


# ── OpenDART 투자·재무활동 현금흐름 (실측: 2026-08-05, 11종목 fnlttSinglAcntAll.json) ──

def test_parse_dart_activity_cash_flow_reads_investing_and_financing_totals():
    """계정ID로 투자·재무활동 총계를 뽑는다 (실측값: 삼성전자 2024 연결)."""
    rows = [
        {
            "sj_div": "CF",
            "account_id": "ifrs-full_CashFlowsFromUsedInInvestingActivities",
            "account_nm": "투자활동현금흐름",
            "thstrm_amount": "-85,381,702,000,000",
            "rcept_no": "20250311001085",
        },
        {
            "sj_div": "CF",
            "account_id": "ifrs-full_CashFlowsFromUsedInFinancingActivities",
            "account_nm": "재무활동현금흐름",
            "thstrm_amount": "-7,797,243,000,000",
            "rcept_no": "20250311001085",
        },
    ]

    investing = _parse_dart_activity_cash_flow(
        rows, ff_mod._DART_INVESTING_CASH_FLOW_ACCOUNT_ID, ff_mod._DART_INVESTING_CASH_FLOW_NAMES
    )
    financing = _parse_dart_activity_cash_flow(
        rows, ff_mod._DART_FINANCING_CASH_FLOW_ACCOUNT_ID, ff_mod._DART_FINANCING_CASH_FLOW_NAMES
    )

    assert investing == {"amount": -85_381_702_000_000.0, "available_from": "2025-03-11"}
    assert financing == {"amount": -7_797_243_000_000.0, "available_from": "2025-03-11"}


def test_parse_dart_activity_cash_flow_ignores_lookalike_subtotal():
    """포스코인터내셔널 실측 함정: '영업활동에서창출된현금흐름'(이자·법인세 차감 전 소계)을
    총계로 오인하지 않고, 계정ID가 일치하는 총계 행을 고른다."""
    rows = [
        {
            "sj_div": "CF",
            "account_id": "ifrs-full_CashFlowsFromUsedInOperations",
            "account_nm": "영업활동에서창출된현금흐름",
            "thstrm_amount": "1,205,694,724,000",
            "rcept_no": "20250311000001",
        },
        {
            "sj_div": "CF",
            "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
            "account_nm": "영업활동으로인한현금흐름",
            "thstrm_amount": "876,881,370,000",
            "rcept_no": "20250311000001",
        },
    ]

    assert _parse_dart_operating_cash_flow(rows) == {
        "operating_cash_flow": 876_881_370_000.0,
        "available_from": "2025-03-11",
    }


def test_parse_dart_activity_cash_flow_falls_back_to_net_flow_name():
    """계정ID가 비어 있어도 '…순현금흐름' 표기(신한지주·클래시스 실측)를 인식한다."""
    rows = [{
        "sj_div": "CF",
        "account_id": "",
        "account_nm": "투자활동 순현금흐름",
        "thstrm_amount": "148,533,000,000",
        "rcept_no": "20250311000002",
    }]

    parsed = _parse_dart_activity_cash_flow(
        rows, ff_mod._DART_INVESTING_CASH_FLOW_ACCOUNT_ID, ff_mod._DART_INVESTING_CASH_FLOW_NAMES
    )
    assert parsed == {"amount": 148_533_000_000.0, "available_from": "2025-03-11"}


def test_fetch_cash_flow_from_dart_captures_all_three_activities(monkeypatch):
    """3분류가 한 응답에서 모두 담긴다 — 추가 API 호출 없음."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00126380")

    rows = [
        {"sj_div": "CF", "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
         "account_nm": "영업활동현금흐름", "thstrm_amount": "72,982,621,000,000",
         "rcept_no": "20250311001085"},
        {"sj_div": "CF", "account_id": "ifrs-full_CashFlowsFromUsedInInvestingActivities",
         "account_nm": "투자활동현금흐름", "thstrm_amount": "-85,381,702,000,000",
         "rcept_no": "20250311001085"},
        {"sj_div": "CF", "account_id": "ifrs-full_CashFlowsFromUsedInFinancingActivities",
         "account_nm": "재무활동현금흐름", "thstrm_amount": "-7,797,243,000,000",
         "rcept_no": "20250311001085"},
    ]
    calls = []

    def fake_fetch(path, params):
        calls.append(path)
        if path == "list.json":
            return {"status": "013"}
        return {"status": "000", "list": rows}

    monkeypatch.setattr(ff, "_fetch_dart_json", fake_fetch)

    assert _fetch_cash_flow_from_dart("005930", 2024, 2024) == [{
        "year_end": "2024-12-31",
        "available_from": "2025-03-11",
        "operating_cash_flow": 72_982_621_000_000.0,
        "investing_cash_flow": -85_381_702_000_000.0,
        "financing_cash_flow": -7_797_243_000_000.0,
    }]
    # 연도당 fnlttSinglAcntAll.json 1회 — 3분류 추가로 호출이 늘지 않았다.
    assert calls.count("fnlttSinglAcntAll.json") == 1


def test_fetch_cash_flow_from_dart_omits_missing_activity_buckets(monkeypatch):
    """투자·재무활동이 없는 제출본은 키 자체를 넣지 않는다(0으로 날조 금지)."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00126380")
    monkeypatch.setattr(ff, "dart_fiscal_month", lambda symbol, corp_code: "12")

    def fake_fetch(path, params):
        if path == "list.json":
            return {"status": "013"}
        return {"status": "000", "list": [{
            "sj_div": "CF",
            "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
            "account_nm": "영업활동현금흐름",
            "thstrm_amount": "100,000",
            "rcept_no": "20250331000001",
        }]}

    monkeypatch.setattr(ff, "_fetch_dart_json", fake_fetch)

    result = _fetch_cash_flow_from_dart("005930", 2024, 2024)
    assert "investing_cash_flow" not in result[0]
    assert "financing_cash_flow" not in result[0]


def test_fetch_dart_original_filing_dates_prefers_earliest_original(monkeypatch):
    """정정공시가 있어도 연도별 최초(원공시) 접수일을 고른다.

    2026-08-07 이전에는 '(YYYY.12)'만 매핑해 비12월 결산 보고서를 통째로 버렸다 —
    그 회사들만 정정일 오염 클램프에서 빠지던 결함이라, 이제 결산월과 무관하게 매핑한다.
    """
    import engine.fundamental_fetcher as ff

    def fake_fetch(path, params):
        assert path == "list.json"
        return {
            "status": "000",
            "total_count": 3,
            "list": [
                {"report_nm": "[기재정정]사업보고서 (2020.12)", "rcept_dt": "20230317"},
                {"report_nm": "사업보고서 (2020.12)", "rcept_dt": "20210318"},
                {"report_nm": "사업보고서 (2021.03)", "rcept_dt": "20210630"},
            ],
        }

    monkeypatch.setattr(ff, "_fetch_dart_json", fake_fetch)

    assert ff._fetch_dart_original_filing_dates("00126380") == {
        2020: "2021-03-18",   # 정정본 2023-03-17이 아니라 원공시
        2021: "2021-06-30",   # 결산월이 12가 아니어도 버리지 않는다
    }


def test_fetch_cash_flow_from_dart_clamps_available_from_to_original_filing(monkeypatch):
    """fnlttSinglAcntAll의 rcept_no가 정정본이어도 available_from은 원공시 접수일로
    클램프된다(2026-08-04 사고: 정정일 오염으로 PIT 참조가 수년 뒤로 밀림)."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00126380")
    monkeypatch.setattr(ff, "dart_fiscal_month", lambda symbol, corp_code: "12")

    def fake_fetch(path, params):
        if path == "list.json":
            return {
                "status": "000",
                "total_count": 1,
                "list": [{"report_nm": "사업보고서 (2020.12)", "rcept_dt": "20210318"}],
            }
        if path == "fnlttSinglAcntAll.json":
            return {
                "status": "000",
                "list": [{
                    "sj_div": "CF",
                    "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
                    "account_nm": "영업활동현금흐름",
                    "thstrm_amount": "100,000",
                    "rcept_no": "20230317000001",
                }],
            }
        raise AssertionError(f"unexpected DART path: {path}")

    monkeypatch.setattr(ff, "_fetch_dart_json", fake_fetch)

    assert _fetch_cash_flow_from_dart("005930", 2020, 2020) == [{
        "year_end": "2020-12-31",
        "available_from": "2021-03-18",
        "operating_cash_flow": 100_000.0,
    }]


def test_merge_fundamental_records_combines_kis_and_dart_fields():
    result = _merge_fundamental_records(
        [{"year_end": "2024-12-31", "eps": 5000.0}],
        [{
            "year_end": "2024-12-31",
            "available_from": "2025-03-11",
            "operating_cash_flow": 1_000_000.0,
        }],
    )

    assert result == [{
        "year_end": "2024-12-31",
        "eps": 5000.0,
        "available_from": "2025-03-11",
        "operating_cash_flow": 1_000_000.0,
    }]


# ── _compute_derived_annual_metrics ──

def test_compute_derived_metrics_fcf_is_ocf_minus_capex():
    result = _compute_derived_annual_metrics([
        {"year_end": "2024-12-31", "operating_cash_flow": 1000.0, "capex": 300.0},
    ])
    assert result[0]["fcf"] == pytest.approx(700.0)


def test_compute_derived_metrics_ev_ebit_derived_from_ev_ebitda_and_ebit():
    result = _compute_derived_annual_metrics([
        {"year_end": "2024-12-31", "ebitda": 100.0, "ev_ebitda": 8.0, "ebit": 80.0},
    ])
    # EV = ev_ebitda * ebitda = 800; EV/EBIT = 800/80 = 10
    assert result[0]["ev"] == pytest.approx(800.0)
    assert result[0]["ev_ebit"] == pytest.approx(10.0)


def test_compute_derived_metrics_ev_ebit_skipped_when_ebitda_nonpositive():
    """ebitda<=0이면 EV 자체를 역산할 수 없어 ev/ev_ebit 모두 만들지 않는다."""
    result = _compute_derived_annual_metrics([
        {"year_end": "2024-12-31", "ebitda": -50.0, "ev_ebitda": 8.0, "ebit": 80.0},
    ])
    assert "ev" not in result[0]
    assert "ev_ebit" not in result[0]


def test_compute_derived_metrics_stores_net_income_in_eok():
    """당기순이익(억원)은 성장률 계산 후 버리지 않고 저장한다(2026-08-03 절대 금액 필터).

    순이익률(%) x 매출액(억원) 재계산 값이며, net_income_growth 재계산도 이 값을 쓴다."""
    result = _compute_derived_annual_metrics([
        {"year_end": "2023-12-31", "_revenue": 10000.0, "net_margin": 10.0},
        {"year_end": "2024-12-31", "_revenue": 12000.0, "net_margin": 10.0},
    ])
    assert result[0]["net_income"] == pytest.approx(1000.0)
    assert result[1]["net_income"] == pytest.approx(1200.0)
    assert result[1]["net_income_growth"] == pytest.approx(20.0)
    # 내부 컴포넌트(_revenue)는 여전히 저장하지 않는다
    assert "_revenue" not in result[0]


def test_compute_derived_metrics_normal_growth_for_profit_to_profit():
    result = _compute_derived_annual_metrics([
        {"year_end": "2023-12-31", "eps": 1000.0},
        {"year_end": "2024-12-31", "eps": 1200.0},
    ])
    assert result[1]["eps_growth"] == pytest.approx(20.0)
    assert "eps_growth_status" not in result[1]


def test_compute_derived_metrics_turnaround_status_for_eps():
    result = _compute_derived_annual_metrics([
        {"year_end": "2023-12-31", "eps": -500.0},
        {"year_end": "2024-12-31", "eps": 300.0},
    ])
    assert "eps_growth" not in result[1]
    assert result[1]["eps_growth_status"] == "TURNAROUND"


def test_compute_derived_metrics_operating_income_growth_recomputed_locally_not_from_kis():
    """KIS가 준 operating_income_growth(왜곡 가능)는 로컬 재계산 결과로 대체되거나(부호전환 시)
    상태코드로 바뀐다 — raw ebit 기반 재계산이 신뢰 소스가 된다."""
    result = _compute_derived_annual_metrics([
        {"year_end": "2023-12-31", "ebit": -100.0},
        {"year_end": "2024-12-31", "ebit": 50.0, "operating_income_growth": 999.0},  # KIS 원값(왜곡)
    ])
    assert "operating_income_growth" not in result[1]
    assert result[1]["operating_income_growth_status"] == "TURNAROUND"


def test_compute_derived_metrics_net_income_growth_uses_net_margin_times_revenue():
    result = _compute_derived_annual_metrics([
        {"year_end": "2023-12-31", "net_margin": 10.0, "_revenue": 1000.0},  # net_income=100
        {"year_end": "2024-12-31", "net_margin": 12.0, "_revenue": 1000.0},  # net_income=120
    ])
    assert result[1]["net_income_growth"] == pytest.approx(20.0)
    assert "_net_income" not in result[1]
    assert "_revenue" not in result[1]


def test_compute_derived_metrics_loss_narrowed_and_widened():
    narrowed = _compute_derived_annual_metrics([
        {"year_end": "2023-12-31", "ebitda": -100.0},
        {"year_end": "2024-12-31", "ebitda": -40.0},
    ])
    assert narrowed[1]["ebitda_growth_status"] == "LOSS_NARROWED"

    widened = _compute_derived_annual_metrics([
        {"year_end": "2023-12-31", "operating_cash_flow": -40.0},
        {"year_end": "2024-12-31", "operating_cash_flow": -100.0},
    ])
    assert widened[1]["ocf_growth_status"] == "LOSS_WIDENED"


def test_compute_derived_metrics_first_record_has_no_growth():
    result = _compute_derived_annual_metrics([
        {"year_end": "2024-12-31", "eps": 1000.0},
    ])
    assert "eps_growth" not in result[0]
    assert "eps_growth_status" not in result[0]


# ── enrich_ohlcv_with_fundamentals ──

def _make_ohlcv_df(dates, close_prices):
    """테스트용 간단한 OHLCV DataFrame 생성."""
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "open": close_prices,
        "high": close_prices,
        "low": close_prices,
        "close": close_prices,
        "volume": [1000] * len(dates),
    })


def test_enrich_adds_per_pbr_columns():
    # 2024-04-01 이후 = 2023.12 결산 데이터 적용 (결산일 + 90일)
    dates = ["2024-04-01", "2024-06-01", "2024-12-01"]
    close = [50000.0, 60000.0, 70000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 2000.0, "bps": 50000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    assert "per" in result.columns
    assert "pbr" in result.columns
    assert "eps" in result.columns
    assert "bps" in result.columns
    assert "roe_or_gpa" in result.columns
    assert "debt_ratio" in result.columns

    # PER = close / EPS = 50000 / 2000 = 25.0
    assert result.iloc[0]["per"] == pytest.approx(25.0)
    # PBR = close / BPS = 50000 / 50000 = 1.0
    assert result.iloc[0]["pbr"] == pytest.approx(1.0)
    assert pd.isna(result.iloc[0]["roe_or_gpa"])
    assert pd.isna(result.iloc[0]["debt_ratio"])


def test_enrich_respects_publish_delay():
    """결산일 + 90일 이전에는 해당 연도 데이터가 적용되지 않아야 함."""
    # 2023-12-31 결산 + 90일 = 2024-03-30 (effective date)
    # 2024-03-29: 미공시, 2024-03-30: 공시일 (>= effective_date)
    dates = ["2024-02-01", "2024-03-29", "2024-03-30"]
    close = [50000.0, 50000.0, 50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 2000.0, "bps": 50000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    # 2024-02-01, 2024-03-29: 아직 미공시 → NaN
    assert pd.isna(result.iloc[0]["per"])
    assert pd.isna(result.iloc[1]["per"])
    # 2024-03-30: 공시 후 → 값 있음
    assert result.iloc[2]["per"] == pytest.approx(25.0)


def test_enrich_pcr_starts_on_actual_dart_filing_date():
    dates = ["2025-03-10", "2025-03-11", "2025-04-01"]
    df = _make_ohlcv_df(dates, [50_000.0, 50_000.0, 60_000.0])
    df["market_cap"] = [50_000.0, 50_000.0, 60_000.0]
    fundamentals = [{
        "year_end": "2024-12-31",
        "available_from": "2025-03-11",
        "operating_cash_flow": 1_000_000_000_000.0,
    }]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    assert pd.isna(result.iloc[0]["pcr"])
    assert result.iloc[1]["pcr"] == pytest.approx(5.0)
    assert result.iloc[2]["pcr"] == pytest.approx(6.0)
    assert result.iloc[1]["operating_cash_flow"] == pytest.approx(1_000_000_000_000.0)


def test_enrich_pcr_ignores_non_positive_operating_cash_flow():
    df = _make_ohlcv_df(["2025-03-11"], [50_000.0])
    df["market_cap"] = [50_000.0]
    fundamentals = [{
        "year_end": "2024-12-31",
        "available_from": "2025-03-11",
        "operating_cash_flow": -1_000_000_000_000.0,
    }]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    assert pd.isna(result.iloc[0]["pcr"])


def test_enrich_forward_fill_updates_with_new_fiscal_year():
    """새로운 결산 데이터가 공시되면 PER/PBR이 업데이트되어야 함."""
    dates = ["2024-04-01", "2025-04-01"]
    close = [50000.0, 50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 2000.0, "bps": 50000.0},
        {"year_end": "2024-12-31", "eps": 5000.0, "bps": 60000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    # 2024-04-01: 2023.12 데이터 → PER = 50000/2000 = 25
    assert result.iloc[0]["per"] == pytest.approx(25.0)
    # 2025-04-01: 2024.12 데이터 → PER = 50000/5000 = 10
    assert result.iloc[1]["per"] == pytest.approx(10.0)


def test_enrich_forward_fills_roe_or_gpa():
    dates = ["2024-04-01", "2025-04-01"]
    close = [50000.0, 50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "roe_or_gpa": 4.15},
        {"year_end": "2024-12-31", "roe_or_gpa": 9.03},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    assert result.iloc[0]["roe_or_gpa"] == pytest.approx(4.15)
    assert result.iloc[1]["roe_or_gpa"] == pytest.approx(9.03)


def test_enrich_forward_fills_debt_ratio():
    dates = ["2024-04-01", "2025-04-01"]
    close = [50000.0, 50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "debt_ratio": 45.5},
        {"year_end": "2024-12-31", "debt_ratio": 38.2},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)

    assert result.iloc[0]["debt_ratio"] == pytest.approx(45.5)
    assert result.iloc[1]["debt_ratio"] == pytest.approx(38.2)


def test_enrich_negative_eps_produces_nan_per():
    """적자 기업(순이익<0)의 PER은 금융적으로 무의미하므로 계산하지 않고 NaN이어야 함.

    이전에는 음수 PER(-50.0)을 그대로 계산했으나, 적자 기업의 PER은 금융적으로 해석
    불가능하다는 요구사항에 따라 null 처리로 변경됨.
    """
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": -1000.0, "bps": 50000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)
    assert pd.isna(result.iloc[0]["per"])
    # PBR은 BPS가 양수라 정상 계산되어야 함(PER만 무효화됨을 확인)
    assert result.iloc[0]["pbr"] == pytest.approx(1.0)


def test_enrich_capital_impairment_produces_nan_pbr_and_roe():
    """자본잠식(BPS<=0)이면 PBR과 ROE 모두 NaN이어야 함."""
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 1000.0, "bps": -5000.0, "roe_or_gpa": 180.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)
    assert pd.isna(result.iloc[0]["pbr"])
    assert pd.isna(result.iloc[0]["roe_or_gpa"])
    # PER은 EPS가 양수라 정상 계산되어야 함(PBR/ROE만 무효화됨을 확인)
    assert result.iloc[0]["per"] == pytest.approx(50.0)


def test_enrich_roe_uses_total_equity_over_bps_when_available():
    """total_equity가 있으면 BPS 대신 total_equity 부호로 ROE 유효성을 판정한다."""
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "bps": 50000.0, "roe_or_gpa": 10.0, "total_equity": -1.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)
    assert pd.isna(result.iloc[0]["roe_or_gpa"])


def test_enrich_forward_fills_ev_ebit_and_growth_status():
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {
            "year_end": "2023-12-31",
            "ev_ebit": 12.5,
            "eps_growth_status": "TURNAROUND",
        },
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)
    assert result.iloc[0]["ev_ebit"] == pytest.approx(12.5)
    assert result.iloc[0]["eps_growth_status"] == "TURNAROUND"


def test_enrich_zero_eps_produces_nan_per():
    """EPS가 0이면 PER은 NaN이어야 함 (0 나누기 방지)."""
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    fundamentals = [
        {"year_end": "2023-12-31", "eps": 0.0, "bps": 50000.0},
    ]

    result = enrich_ohlcv_with_fundamentals(df, fundamentals)
    assert pd.isna(result.iloc[0]["per"])
    assert result.iloc[0]["pbr"] == pytest.approx(1.0)


def test_enrich_empty_fundamentals_no_change():
    """fundamentals가 비어있으면 원본 DataFrame이 반환되어야 함."""
    dates = ["2024-04-01"]
    close = [50000.0]
    df = _make_ohlcv_df(dates, close)

    result = enrich_ohlcv_with_fundamentals(df, [])
    assert "per" not in result.columns

    result2 = enrich_ohlcv_with_fundamentals(df, None)
    assert "per" not in result2.columns


# ── Naver ROE 파싱 ──

def test_parse_fundamentals_extracts_roe():
    """Naver Finance HTML에서 ROE 값이 파싱되어야 함."""
    result = _parse_fundamentals(_SAMPLE_HTML)
    assert result is not None
    # 2023.12
    assert result[0].get("roe_or_gpa") == 4.15
    # 2024.12
    assert result[1].get("roe_or_gpa") == 9.03
    # 2025.12
    assert result[2].get("roe_or_gpa") == 10.85


def test_parse_fundamentals_extracts_debt_ratio():
    result = _parse_fundamentals(_SAMPLE_HTML)
    assert result is not None
    assert result[0].get("debt_ratio") == 25.10
    assert result[1].get("debt_ratio") == 30.20
    assert result[2].get("debt_ratio") == 35.30


def test_parse_fundamentals_roe_excluded_for_estimates():
    """추정치(E) 연도의 ROE는 포함되지 않아야 함."""
    result = _parse_fundamentals(_SAMPLE_HTML)
    # 2026.12(E) → 제외됨
    year_ends = [r["year_end"] for r in result]
    assert "2026-12-31" not in year_ends


_SAMPLE_HTML_NO_ROE = """
<html><body>
<table>
<tr><th>주요재무정보</th><th colspan="2">최근 연간 실적</th></tr>
<tr><td>2023.12</td><td>2024.12</td></tr>
<tr><td>EPS(원)</td><td>1,000</td><td>2,000</td></tr>
<tr><td>BPS(원)</td><td>10,000</td><td>20,000</td></tr>
</table>
</body></html>
"""


def test_parse_fundamentals_no_roe_row():
    """ROE 행이 없는 HTML에서는 roe_or_gpa가 결과에 포함되지 않아야 함."""
    result = _parse_fundamentals(_SAMPLE_HTML_NO_ROE)
    assert result is not None
    for entry in result:
        assert "roe_or_gpa" not in entry


# ── 캐시 read/write ──

def test_cache_write_and_read(tmp_path, monkeypatch):
    """캐시 write 후 read가 동일한 데이터를 반환해야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    fundamentals = [
        {"year_end": "2024-12-31", "eps": 5000.0, "bps": 60000.0, "roe_or_gpa": 9.03},
    ]
    _write_cache("005930", fundamentals)
    result = _read_cache("005930")
    assert result == fundamentals


def test_cache_expired(tmp_path, monkeypatch):
    """만료된 캐시는 None을 반환해야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ff, "_CACHE_MAX_AGE_DAYS", 0)

    fundamentals = [{"year_end": "2024-12-31", "roe_or_gpa": 9.03}]
    _write_cache("005930", fundamentals)

    # fetched_at을 과거로 수정
    import json
    cache_file = tmp_path / "005930.json"
    data = json.loads(cache_file.read_text())
    data["fetched_at"] = "2020-01-01T00:00:00"
    cache_file.write_text(json.dumps(data))

    result = _read_cache("005930")
    assert result is None


def test_cache_missing_symbol(tmp_path, monkeypatch):
    """캐시에 없는 종목은 None을 반환해야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    result = _read_cache("999999")
    assert result is None


# ── negative 캐시 (조회 실패 반복 방지) ──

def test_negative_cache_write_and_read(tmp_path, monkeypatch):
    """실패를 기록하면 TTL 이내에는 '최근 확인된 실패'로 인식돼야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    assert _is_recently_confirmed_empty("088980") is False
    _write_negative_cache("088980")
    assert _is_recently_confirmed_empty("088980") is True


def test_negative_cache_expired(tmp_path, monkeypatch):
    """TTL이 지난 negative 캐시는 더 이상 유효하지 않아야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ff, "_NEGATIVE_CACHE_TTL_DAYS", 0)

    _write_negative_cache("088980")

    import json
    cache_file = tmp_path / "088980.nodata.json"
    data = json.loads(cache_file.read_text())
    data["checked_at"] = "2020-01-01T00:00:00"
    cache_file.write_text(json.dumps(data))

    assert _is_recently_confirmed_empty("088980") is False


def test_fetch_fundamentals_skips_network_when_recently_confirmed_empty(tmp_path, monkeypatch):
    """REITs처럼 KIS/Naver 둘 다 실패하는 종목은 negative 캐시 TTL 내에서 재조회하지 않아야 함."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    kis_calls = {"n": 0}
    naver_calls = {"n": 0}

    def _fail_kis(symbol):
        kis_calls["n"] += 1
        return None

    class _FakeResp:
        status_code = 404
        text = ""

    def _fail_naver(*a, **k):
        naver_calls["n"] += 1
        return _FakeResp()

    monkeypatch.setattr(ff, "_fetch_fundamentals_from_kis", _fail_kis)
    monkeypatch.setattr(ff, "_fetch_cash_flow_from_dart", lambda symbol: None)
    monkeypatch.setattr(ff.requests, "get", _fail_naver)

    # 첫 호출: KIS+Naver 실패 → negative 캐시 기록
    result1 = fetch_fundamentals("088980", retry=0)
    assert result1 is None
    assert kis_calls["n"] == 1
    assert naver_calls["n"] == 1

    # 두 번째 호출: negative 캐시가 있으니 KIS/Naver를 다시 호출하지 않아야 함
    result2 = fetch_fundamentals("088980", retry=0)
    assert result2 is None
    assert kis_calls["n"] == 1
    assert naver_calls["n"] == 1


# ── DART 일일 허용량 소진(status 020) — 완성본으로 캐시하지 않는다 (2026-08-04 사고) ──

def test_fetch_cash_flow_from_dart_raises_on_quota_exhausted(monkeypatch):
    """한도 소진은 '데이터 없음'(None)이 아니라 예외다 — 부분 결과를 완성본으로 흘리지 않는다."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00126380")
    monkeypatch.setattr(ff, "dart_fiscal_month", lambda symbol, corp_code: "12")

    def fake_fetch(path, params):
        if path == "list.json":
            return {"status": "020", "message": "요청 제한을 초과하였습니다."}
        return {"status": "020", "message": "요청 제한을 초과하였습니다."}

    monkeypatch.setattr(ff, "_fetch_dart_json", fake_fetch)

    with pytest.raises(ff.DartQuotaExhausted):
        _fetch_cash_flow_from_dart("005930", 2024, 2024)


def test_fetch_fundamentals_marks_cache_dart_pending_on_quota_and_retries_next_day(tmp_path, monkeypatch):
    """한도 소진 시 KIS 값은 dart_pending 캐시로 남기되, 다음 날엔 만료로 취급해 다시 받는다.

    2026-08-04 전수 백필에서 04시경 한도가 바닥난 뒤 ~420종목이 DART 항목(지배주주순이익·
    현금흐름·FCF) 없이 90일짜리 완성본으로 캐시돼 이후 백필이 전부 건너뛰었다.
    """
    import json

    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)

    kis_records = [{"year_end": "2024-12-31", "eps": 5000.0, "bps": 60000.0, "roe_or_gpa": 9.0}]
    monkeypatch.setattr(ff, "_fetch_fundamentals_from_kis", lambda symbol: [dict(r) for r in kis_records])

    def _quota(symbol):
        raise ff.DartQuotaExhausted(symbol)

    monkeypatch.setattr(ff, "_fetch_cash_flow_from_dart", _quota)

    result = fetch_fundamentals("005930", retry=0)
    assert result and result[0]["eps"] == 5000.0  # KIS 값은 그대로 쓴다

    payload = json.loads((tmp_path / "005930.json").read_text())
    assert payload["dart_pending"] is True
    assert ff.is_dart_pending("005930") is True
    # 당일: 한도가 바닥난 DART를 다시 두드리지 않도록 캐시를 그대로 읽는다
    assert _read_cache("005930") == result

    # 다음 날: 만료로 취급 → fetch가 다시 받는다
    payload["fetched_at"] = (pd.Timestamp.now() - pd.Timedelta(days=1)).isoformat()
    (tmp_path / "005930.json").write_text(json.dumps(payload))
    assert _read_cache("005930") is None

    # 완성되면 플래그가 사라진다
    monkeypatch.setattr(ff, "_fetch_cash_flow_from_dart", lambda symbol: [
        {"year_end": "2024-12-31", "available_from": "2025-03-31", "operating_cash_flow": 1e8},
    ])
    result2 = fetch_fundamentals("005930", retry=0)
    assert result2[0]["operating_cash_flow"] == 1e8
    assert "dart_pending" not in json.loads((tmp_path / "005930.json").read_text())
    assert ff.is_dart_pending("005930") is False


# ── KIS 분기 행 혼입 제거 (실측: 2026-08-07, 현대차 stac_yymm 202603 + 202512 …) ──

def test_drop_kis_interim_records_removes_leading_quarter_row():
    """연간을 요청해도 KIS가 끼워 보내는 최신 분기 한 행을 걷어낸다."""
    from engine.fundamental_fetcher import drop_kis_interim_records

    records = [
        {"year_end": "2026-03-31", "eps": 8800.0, "net_income": 25_863.6},
        {"year_end": "2025-12-31", "eps": 35_331.0, "net_income": 103_743.8},
        {"year_end": "2024-12-31", "eps": 32_000.0},
    ]
    kept = drop_kis_interim_records(records)
    assert [r["year_end"] for r in kept] == ["2025-12-31", "2024-12-31"]


def test_drop_kis_interim_records_respects_non_december_fiscal_year():
    """3월 결산 회사는 3월이 정상이고 끼어든 12월 행이 분기다(월 최빈값 판정)."""
    from engine.fundamental_fetcher import drop_kis_interim_records

    records = [
        {"year_end": "2025-12-31", "eps": 500.0},   # 끼어든 분기
        {"year_end": "2025-03-31", "eps": 2000.0},
        {"year_end": "2024-03-31", "eps": 1800.0},
        {"year_end": "2023-03-31", "eps": 1600.0},
    ]
    kept = drop_kis_interim_records(records)
    assert [r["year_end"] for r in kept] == ["2025-03-31", "2024-03-31", "2023-03-31"]


def test_drop_kis_interim_records_keeps_single_record():
    """레코드가 하나뿐이면 분기인지 판별할 근거가 없으므로 그대로 둔다."""
    from engine.fundamental_fetcher import drop_kis_interim_records

    records = [{"year_end": "2026-03-31", "eps": 8800.0}]
    assert drop_kis_interim_records(records) == records


def test_fiscal_month_is_the_modal_month():
    from engine.fundamental_fetcher import fiscal_month

    assert fiscal_month(["2026-03-31", "2025-12-31", "2024-12-31"]) == "12"
    assert fiscal_month(["2025-12-31", "2025-03-31", "2024-03-31"]) == "03"
    assert fiscal_month([]) is None


def test_kis_interim_row_is_dropped_before_growth_is_computed(monkeypatch):
    """분기 행이 성장률 체인에 남으면 직전 '연간'과 비교돼 -75%가 찍힌다(현대차 실측)."""
    import engine.fundamental_fetcher as ff

    annual_only = ff.drop_kis_interim_records([
        {"year_end": "2026-03-31", "net_margin": 5.6, "_revenue": 461_000.0},
        {"year_end": "2025-12-31", "net_margin": 5.57, "_revenue": 1_862_547.0},
        {"year_end": "2024-12-31", "net_margin": 7.55, "_revenue": 1_752_312.0},
    ])
    out = ff._compute_derived_annual_metrics(annual_only)
    assert [r["year_end"] for r in out] == ["2024-12-31", "2025-12-31"]
    # 마지막 레코드의 증가율은 연간 대 연간이므로 -75% 근처가 아니어야 한다.
    assert out[-1]["net_income_growth"] > -50


# ── net_income 정본을 DART 당기순이익으로 교체 (2026-08-07) ──

def test_dart_profit_loss_overrides_kis_derived_net_income():
    """KIS 재계산본(net_margin x 매출)보다 DART 원값이 이긴다 — 저마진 연도 오차 제거."""
    result = _compute_derived_annual_metrics([{
        "year_end": "2025-12-31",
        "net_margin": 0.01, "_revenue": 7_000.0,          # KIS 재계산 → 0.7억
        "_profit_loss_raw": 21_000_000_000.0,             # DART 원값 → 210.0억
    }])
    assert result[0]["net_income"] == pytest.approx(210.0)


def test_kis_derived_net_income_kept_when_dart_absent():
    """2015년 이전·별도재무제표만 있는 구간은 KIS 재계산본을 그대로 남긴다."""
    result = _compute_derived_annual_metrics([
        {"year_end": "2012-12-31", "net_margin": 10.0, "_revenue": 1_000.0},
    ])
    assert result[0]["net_income"] == pytest.approx(100.0)


def test_dart_sourced_net_income_and_owner_come_from_the_same_statement():
    """두 값 모두 DART 손익계산서 원값이라 KIS 재계산본과 섞이지 않는다.

    **`owner_net_income <= net_income`은 성립하지 않는다** — 비지배지분 손익이 음수면
    (적자 자회사의 소수주주 몫) 지배주주순이익이 전체보다 크다. 실측 2026-08-08: 삼천리
    2016년 지배 345.4억 + 비지배 -144.9억 = 전체 200.6억, 카카오 2023년 전체 -1.82조 중
    지배 -1.01조. 전수 18,071 레코드 중 5,777건이 이 형태이며 라이브 검산 6/6 통과했다.
    성립하는 관계는 **지배 + 비지배 = 전체** 하나뿐이니 부등호로 검증하지 말 것.
    """
    result = _compute_derived_annual_metrics([{
        "year_end": "2023-12-31",
        "net_margin": 5.98, "_revenue": 2_589_355.0,   # KIS 재계산본(154,843.4)은 무시된다
        "_profit_loss_raw": 15_487_100_000_000.0,
        "_owner_net_income_raw": 14_473_401_000_000.0,
    }])[0]
    assert result["net_income"] == pytest.approx(154_871.0)
    assert result["owner_net_income"] == pytest.approx(144_734.0)


def test_owner_net_income_may_exceed_net_income_when_minority_loses_money():
    """비지배지분이 적자면 지배주주순이익 > 당기순이익이다(삼천리 2016 실측 형태)."""
    result = _compute_derived_annual_metrics([{
        "year_end": "2016-12-31",
        "_profit_loss_raw": 20_057_055_252.0,        # 전체 200.6억
        "_owner_net_income_raw": 34_542_944_249.0,   # 지배 345.4억 (비지배 -144.9억)
    }])[0]
    assert result["net_income"] == pytest.approx(200.6)
    assert result["owner_net_income"] == pytest.approx(345.4)
    assert result["owner_net_income"] > result["net_income"]
    assert "_profit_loss_raw" not in result


def test_drop_kis_interim_records_preserves_fiscal_year_change_history():
    """결산기를 바꾼 회사는 연간 레코드가 두 무리로 갈린다 — 작은 무리를 날리면 안 된다.

    최신 한 행만 후보로 보는 규칙이라 12월 무리가 통째로 사라지지 않는다.
    """
    from engine.fundamental_fetcher import drop_kis_interim_records

    records = [
        {"year_end": f"{y}-12-31", "eps": 100.0} for y in (2016, 2017, 2018)
    ] + [
        {"year_end": f"{y}-03-31", "eps": 200.0} for y in (2020, 2021, 2022)
    ]
    kept = drop_kis_interim_records(records)
    assert len(kept) == 6  # 어느 무리도 잘려나가지 않는다


def test_drop_kis_interim_records_only_removes_the_newest_row():
    """누적 오염이 아니라 KIS가 매번 하나 끼워 보내는 구조 — 최신 한 행만 걷어낸다."""
    from engine.fundamental_fetcher import drop_kis_interim_records

    records = [
        {"year_end": "2024-12-31"}, {"year_end": "2025-12-31"},
        {"year_end": "2026-03-31"},
    ]
    kept = drop_kis_interim_records(records)
    assert [r["year_end"] for r in kept] == ["2024-12-31", "2025-12-31"]


# ── DART 레코드의 결산일 라벨 (2026-08-07) ──

def test_dart_year_end_uses_fiscal_month_not_december():
    """bsns_year는 '그 결산기가 끝나는 달력 연도'다 — 결산월과 조합해 실제 결산일을 만든다.

    실측: 효성오앤비(acc_mt=06) bsns_year 2023의 당기순이익 12.3억 = KIS 2023-06 레코드,
    금비(acc_mt=09) bsns_year 2024 = KIS 2024-09 레코드.
    """
    from engine.fundamental_fetcher import dart_year_end

    assert dart_year_end(2023, "06") == "2023-06-30"
    assert dart_year_end(2024, "09") == "2024-09-30"
    assert dart_year_end(2024, "02") == "2024-02-29"   # 윤년 말일
    assert dart_year_end(2025, "12") == "2025-12-31"


def test_dart_fiscal_month_falls_back_to_december_on_lookup_failure(monkeypatch):
    """기업개황 조회가 실패해도 현행 동작(12월)으로 떨어질 뿐 멈추지 않는다."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setattr(ff, "_DART_FISCAL_MONTHS", {})
    monkeypatch.setattr(ff, "_fetch_dart_json", lambda path, params: {"status": "013"})
    assert ff.dart_fiscal_month("999999", "00000000") == "12"


def test_dart_fiscal_month_caches_successful_lookup(monkeypatch, tmp_path):
    """acc_mt는 거의 바뀌지 않으므로 파일로 눌러 두고 재조회하지 않는다."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setattr(ff, "_DART_FISCAL_MONTHS", {})
    monkeypatch.setattr(ff, "_DART_FISCAL_MONTH_PATH", tmp_path / "fiscal.json")
    calls = []

    def fake(path, params):
        calls.append(path)
        return {"status": "000", "acc_mt": "6"}

    monkeypatch.setattr(ff, "_fetch_dart_json", fake)
    assert ff.dart_fiscal_month("097870", "00123456") == "06"
    assert ff.dart_fiscal_month("097870", "00123456") == "06"
    assert len(calls) == 1


def test_fetch_cash_flow_from_dart_labels_record_with_fiscal_year_end(monkeypatch):
    """비12월 결산 회사의 DART 레코드가 실제 결산일에 붙어야 한다."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00126380")
    monkeypatch.setattr(ff, "dart_fiscal_month", lambda symbol, corp_code: "06")

    rows = [{**row, "rcept_no": "20240930000001"} for row in _DART_CF_BS_FIXTURE]

    def fake_fetch(path, params):
        if path == "list.json":
            return {"status": "013"}
        return {"status": "000", "list": rows}

    monkeypatch.setattr(ff, "_fetch_dart_json", fake_fetch)

    record = _fetch_cash_flow_from_dart("097870", 2024, 2024)[0]
    assert record["year_end"] == "2024-06-30"


def test_dart_annual_report_name_captures_year_and_fiscal_month():
    """사업보고서 이름의 괄호 월은 **그 사업연도의** 결산월이다 — 함께 뽑는다."""
    from engine.fundamental_fetcher import _DART_ANNUAL_REPORT_NAME as pattern

    assert pattern.search("사업보고서 (2025.06)").groups() == ("2025", "06")
    assert pattern.search("[기재정정]사업보고서 (2023.06)").groups() == ("2023", "06")
    assert pattern.search("사업보고서 (2024.12)").groups() == ("2024", "12")
    assert pattern.search("반기보고서 (2024.06)") is None


def test_fetch_dart_annual_report_periods_reads_month_and_original_date(monkeypatch):
    """6월 결산 회사도 매핑되고, 정정본이 아니라 원공시가 이겨야 한다."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setattr(ff, "_fetch_dart_json", lambda path, params: {
        "status": "000",
        "total_count": 3,
        "list": [
            {"report_nm": "사업보고서 (2025.06)", "rcept_dt": "20250919"},
            {"report_nm": "[기재정정]사업보고서 (2024.06)", "rcept_dt": "20240926"},
            {"report_nm": "사업보고서 (2024.06)", "rcept_dt": "20240919"},
        ],
    })
    assert ff._fetch_dart_annual_report_periods("00123456") == {
        2025: ("06", "2025-09-19"),
        2024: ("06", "2024-09-19"),   # 정정본 09-26이 아니다
    }


def test_fetch_dart_annual_report_periods_tracks_fiscal_year_change(monkeypatch):
    """결산기를 바꾼 회사는 연도마다 결산월이 다르다 — acc_mt 하나로는 표현되지 않는다."""
    import engine.fundamental_fetcher as ff

    monkeypatch.setattr(ff, "_fetch_dart_json", lambda path, params: {
        "status": "000",
        "total_count": 3,
        "list": [
            {"report_nm": "사업보고서 (2018.12)", "rcept_dt": "20190315"},
            {"report_nm": "사업보고서 (2017.12)", "rcept_dt": "20180316"},
            {"report_nm": "사업보고서 (2016.03)", "rcept_dt": "20160629"},
        ],
    })
    periods = ff._fetch_dart_annual_report_periods("00123456")
    assert periods[2016][0] == "03"   # 전환 이전
    assert periods[2017][0] == "12"   # 전환 이후


def test_fetch_dart_original_filing_dates_projects_dates_only(monkeypatch):
    import engine.fundamental_fetcher as ff

    monkeypatch.setattr(ff, "_fetch_dart_json", lambda path, params: {
        "status": "000", "total_count": 1,
        "list": [{"report_nm": "사업보고서 (2024.12)", "rcept_dt": "20250311"}],
    })
    assert ff._fetch_dart_original_filing_dates("00126380") == {2024: "2025-03-11"}


# ── KIS 0 자리표시자 연도 제거 + Naver 보충 (실측 2026-08-17, 삼진제약 005500 22개 연도 전부 0) ──

def _placeholder(year_end: str) -> dict:
    """KIS가 재무를 싣지 않은 연도의 실제 응답 모양 — 당좌비율만 값이 있고 나머지는 0."""
    return {"year_end": year_end, "eps": 0.0, "bps": 0.0, "sps": 0.0, "roe_or_gpa": 0.0,
            "debt_ratio": 0.0, "net_margin": 0.0, "quick_ratio": 46.06}


def test_drop_kis_placeholder_records_removes_eps_bps_sps_all_zero_rows():
    from engine.fundamental_fetcher import drop_kis_placeholder_records, is_kis_placeholder_record

    valid = {"year_end": "2025-12-31", "eps": 1746.0, "bps": 22942.0, "sps": 51000.0}
    spac = {"year_end": "2025-12-31", "eps": -12.0, "bps": 2050.0, "sps": 0.0}       # 매출 0이지만 순자산 있음
    impaired = {"year_end": "2025-12-31", "eps": -900.0, "bps": -1200.0, "sps": 800.0}  # 자본잠식
    naver_shaped = {"year_end": "2025-12-31", "eps": 0.0, "bps": 0.0}                # sps 없음 = KIS 아님
    records = [_placeholder("2024-12-31"), valid, spac, impaired, naver_shaped, _placeholder("2023-12-31")]

    kept = drop_kis_placeholder_records(records)
    assert kept == [valid, spac, impaired, naver_shaped]
    assert is_kis_placeholder_record(_placeholder("2024-12-31")) is True
    assert is_kis_placeholder_record(spac) is False


def test_fetch_fundamentals_supplements_naver_when_kis_is_all_placeholder(tmp_path, monkeypatch):
    """KIS가 전 연도 0이면 예전엔 '결과 있음'으로 보고 Naver를 건너뛰어 PER·PBR·ROE가 통째로
    비고 부채비율 0이 '≤ N' 필터를 거짓 통과했다 — 이제 자리표시자를 걷어내고 Naver로 채운다."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ff, "_fetch_fundamentals_from_kis",
                        lambda symbol: [_placeholder("2025-12-31"), _placeholder("2024-12-31")])
    naver_calls = {"n": 0}

    def _naver(symbol, retry=2):
        naver_calls["n"] += 1
        return [{"year_end": "2025-12-31", "eps": 1746.0, "bps": 22942.0, "roe_or_gpa": 8.76, "debt_ratio": 62.03}]

    monkeypatch.setattr(ff, "_fetch_fundamentals_from_naver", _naver)
    monkeypatch.setattr(ff, "_fetch_cash_flow_from_dart", lambda symbol: [
        {"year_end": "2024-12-31", "available_from": "2025-03-13", "operating_cash_flow": 3.8e10},
    ])

    result = fetch_fundamentals("005500", retry=0)
    by_year = {r["year_end"]: r for r in result}
    assert naver_calls["n"] == 1
    assert by_year["2025-12-31"]["eps"] == 1746.0 and by_year["2025-12-31"]["debt_ratio"] == 62.03
    assert "eps" not in by_year["2024-12-31"]                      # 자리표시자 0은 값으로 남지 않는다
    assert by_year["2024-12-31"]["operating_cash_flow"] == 3.8e10  # DART 병합은 그대로
    assert not any(ff.is_kis_placeholder_record(r) for r in result)


def test_fetch_fundamentals_partial_placeholder_keeps_kis_and_fills_gaps_from_naver(tmp_path, monkeypatch):
    """일부 연도만 자리표시자면 KIS 정상 연도는 KIS 값이 이기고, Naver는 KIS가 비운 연도만 채운다."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)
    kis_valid_2024 = {"year_end": "2024-12-31", "eps": 900.0, "bps": 12000.0, "sps": 30000.0, "debt_ratio": 40.0}
    monkeypatch.setattr(ff, "_fetch_fundamentals_from_kis",
                        lambda symbol: [_placeholder("2025-12-31"), kis_valid_2024])
    monkeypatch.setattr(ff, "_fetch_fundamentals_from_naver", lambda symbol, retry=2: [
        {"year_end": "2025-12-31", "eps": 1050.0, "bps": 12500.0, "debt_ratio": 45.0},
        {"year_end": "2024-12-31", "eps": 850.0, "bps": 11900.0, "debt_ratio": 41.0},  # KIS와 겹침 → KIS 우선
    ])
    monkeypatch.setattr(ff, "_fetch_cash_flow_from_dart", lambda symbol: None)

    result = fetch_fundamentals("001080", retry=0)
    by_year = {r["year_end"]: r for r in result}
    assert by_year["2025-12-31"]["eps"] == 1050.0            # 자리표시자 자리를 Naver가 채움
    assert by_year["2024-12-31"]["eps"] == 900.0             # KIS 정상 연도는 KIS 값 유지
    assert by_year["2024-12-31"]["sps"] == 30000.0


def test_fetch_fundamentals_skips_naver_when_kis_has_no_placeholder(tmp_path, monkeypatch):
    import engine.fundamental_fetcher as ff
    monkeypatch.setattr(ff, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ff, "_fetch_fundamentals_from_kis", lambda symbol: [
        {"year_end": "2025-12-31", "eps": 6564.0, "bps": 63997.0, "sps": 49471.0},
    ])

    def _naver(symbol, retry=2):
        raise AssertionError("온전한 KIS 결과엔 Naver를 부르지 않는다")

    monkeypatch.setattr(ff, "_fetch_fundamentals_from_naver", _naver)
    monkeypatch.setattr(ff, "_fetch_cash_flow_from_dart", lambda symbol: None)
    assert fetch_fundamentals("005930", retry=0)[0]["eps"] == 6564.0


# ── PSR 폴백: DART 매출액 파싱 + enrich (FR-BT-052k) ──

def test_dart_revenue_parsed_from_income_statement_into_revenue_eok(monkeypatch):
    """같은 fnlttSinglAcntAll 응답의 ifrs-full_Revenue → _revenue_raw → revenue(억원). 추가 호출 0."""
    import engine.fundamental_fetcher as ff
    monkeypatch.setenv("DART_API_KEY", "test-key")
    monkeypatch.setattr(ff, "_get_dart_corp_code", lambda symbol: "00863533")
    monkeypatch.setattr(ff, "_fetch_dart_annual_report_periods", lambda corp_code: {2024: ("12", "2025-03-13")})
    rows = [
        {"sj_div": "CF", "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
         "account_nm": "영업활동현금흐름", "thstrm_amount": "38152787881", "rcept_no": "20250313000123"},
        {"sj_div": "CIS", "account_id": "ifrs-full_Revenue", "account_nm": "수익(매출액)",
         "thstrm_amount": "308349934442", "rcept_no": "20250313000123"},
    ]
    monkeypatch.setattr(ff, "_fetch_dart_json", lambda path, params: {"status": "000", "list": rows})

    records = _fetch_cash_flow_from_dart("005500", 2024, 2024)
    assert records[0]["_revenue_raw"] == 308349934442.0
    derived = _compute_derived_annual_metrics([dict(records[0])])
    assert derived[0]["revenue"] == pytest.approx(3083.5)
    assert "_revenue_raw" not in derived[0]


def test_enrich_psr_falls_back_to_market_cap_over_revenue_only_when_sps_missing():
    df = _make_ohlcv_df(["2025-03-11", "2025-03-12"], [50_000.0, 50_000.0])
    df["market_cap"] = [6000.0, 6000.0]
    # 2024: SPS 없음(자리표시자 제거) + 매출 3000억 → 폴백 2.0 / SPS 있으면 종가÷SPS가 이긴다
    fundamentals = [{"year_end": "2024-12-31", "available_from": "2025-03-11", "revenue": 3000.0}]
    out = enrich_ohlcv_with_fundamentals(df, fundamentals)
    assert out["psr"].iloc[0] == pytest.approx(2.0)

    with_sps = [{"year_end": "2024-12-31", "available_from": "2025-03-11", "sps": 25_000.0, "revenue": 3000.0}]
    out2 = enrich_ohlcv_with_fundamentals(df, with_sps)
    assert out2["psr"].iloc[0] == pytest.approx(2.0)   # 50000/25000 — 우연히 같으니 SPS 바꿔 재확인
    with_sps[0]["sps"] = 10_000.0
    out3 = enrich_ohlcv_with_fundamentals(df, with_sps)
    assert out3["psr"].iloc[0] == pytest.approx(5.0)   # 종가÷SPS, 폴백(2.0)이 덮지 않는다
