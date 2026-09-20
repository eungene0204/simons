"""분기 EPS·실적 발표일 수집(engine/quarterly_earnings.py)의 계약 테스트.

DART에 붙지 않는다 — `_fetch_dart_json`을 대역으로 갈아 끼워 응답 모양만 고정한다.
지키려는 계약 셋:
  ① 분기보고서의 3개월 값(thstrm_amount)을 쓰고 누적(thstrm_add_amount)을 쓰지 않는다
  ② 4분기는 연간 − 3분기 누적이다(4분기 보고서가 없으므로)
  ③ 연결/별도 기준은 종목 단위로 하나만 쓴다(섞이면 분기 차분이 기준 변경을 잰다)
"""
from __future__ import annotations

import pytest

from engine import quarterly_earnings as qe


def _eps_payload(amount, cumulative, rcept_no, account_id="ifrs-full_BasicEarningsLossPerShare"):
    return {
        "status": "000",
        "list": [
            {"account_id": "ifrs-full_Revenue", "thstrm_amount": "1000"},
            {
                "account_id": account_id,
                "account_nm": "기본주당이익",
                "thstrm_amount": amount,
                "thstrm_add_amount": cumulative,
                "rcept_no": rcept_no,
            },
        ],
    }


# 삼성전자 2024 실측값(1Q 975 · 2Q 1419 · 3Q 1440 · 연간 4950, 3Q 누적 3834).
_SAMSUNG_2024 = {
    ("11013", "CFS"): _eps_payload("975", "975", "20240516001421"),
    ("11012", "CFS"): _eps_payload("1419", "2394", "20240814003284"),
    ("11014", "CFS"): _eps_payload("1440", "3834", "20241114002642"),
    ("11011", "CFS"): _eps_payload("4950", "", "20250311001085"),
}


@pytest.fixture
def stub_dart(monkeypatch):
    """(reprt_code, fs_div) → 응답 표를 받아 DART 호출을 대역으로 바꾼다."""

    def install(table, fiscal_month="12"):
        def fake_fetch(path, params):
            if path == "company.json":
                return {"status": "000", "acc_mt": fiscal_month}
            key = (params.get("reprt_code"), params.get("fs_div"))
            return table.get(key, {"status": "013"})

        monkeypatch.setattr(qe, "_fetch_dart_json", fake_fetch)
        monkeypatch.setattr(qe, "_get_dart_corp_code", lambda symbol: "00126380")
        monkeypatch.setattr(qe, "dart_fiscal_month", lambda symbol, corp: fiscal_month)

    return install


def test_quarterly_eps_uses_three_month_amount_not_cumulative(stub_dart):
    stub_dart(_SAMSUNG_2024)

    records = qe.fetch_quarterly_earnings("005930", start_year=2024, end_year=2024)

    assert [r["eps"] for r in records[:3]] == [975.0, 1419.0, 1440.0]


def test_fourth_quarter_is_annual_minus_third_quarter_cumulative(stub_dart):
    stub_dart(_SAMSUNG_2024)

    records = qe.fetch_quarterly_earnings("005930", start_year=2024, end_year=2024)

    fourth = records[3]
    assert fourth["period_end"] == "2024-12-31"
    assert fourth["eps"] == pytest.approx(4950.0 - 3834.0)
    # 4분기 발표일은 사업보고서 접수일이다(분기보고서가 없다).
    assert fourth["announce_date"] == "2025-03-11"


def test_announce_date_comes_from_receipt_number(stub_dart):
    stub_dart(_SAMSUNG_2024)

    records = qe.fetch_quarterly_earnings("005930", start_year=2024, end_year=2024)

    assert [r["announce_date"] for r in records[:3]] == [
        "2024-05-16", "2024-08-14", "2024-11-14",
    ]


def test_fourth_quarter_dropped_when_third_quarter_cumulative_missing(stub_dart):
    table = dict(_SAMSUNG_2024)
    table[("11014", "CFS")] = _eps_payload("1440", "", "20241114002642")
    stub_dart(table)

    records = qe.fetch_quarterly_earnings("005930", start_year=2024, end_year=2024)

    # 역산 재료가 없으면 지어내지 않고 비운다(fail-closed).
    assert [r["period_end"] for r in records] == [
        "2024-03-31", "2024-06-30", "2024-09-30",
    ]


def test_separate_statements_used_only_when_consolidated_absent(stub_dart):
    stub_dart({
        ("11013", "OFS"): _eps_payload("1488", "1488", "20240516001111"),
        ("11012", "OFS"): _eps_payload("2224", "3712", "20240814002222"),
    })

    records = qe.fetch_quarterly_earnings("035420", start_year=2024, end_year=2024)

    assert {r["fs_div"] for r in records} == {"OFS"}


def test_mixed_basis_is_not_produced_when_consolidated_exists(stub_dart):
    """연결이 잡힌 종목은 별도 응답이 있어도 별도를 섞지 않는다(NAVER 2024 1Q 사고 형태)."""
    stub_dart({
        ("11013", "OFS"): _eps_payload("1488", "1488", "20240516001111"),
        ("11012", "CFS"): _eps_payload("2224", "3712", "20240814002222"),
        ("11014", "CFS"): _eps_payload("3423", "9016", "20241114003333"),
    })

    records = qe.fetch_quarterly_earnings("035420", start_year=2024, end_year=2024)

    assert {r["fs_div"] for r in records} == {"CFS"}
    # 1분기는 연결 응답이 없으므로 별도 값(1488)으로 채우지 않고 비운다.
    assert [r["period_end"] for r in records] == ["2024-06-30", "2024-09-30"]


def test_legacy_taxonomy_account_id_is_accepted(stub_dart):
    """2018년 이전 보고서는 ifrs_ 접두(구 택소노미)다."""
    stub_dart({
        ("11013", "CFS"): _eps_payload(
            "36356", "36356", "20160516000001", account_id="ifrs_BasicEarningsLossPerShare"
        ),
    })

    records = qe.fetch_quarterly_earnings("005930", start_year=2016, end_year=2016)

    assert records[0]["eps"] == 36356.0


def test_non_december_fiscal_year_quarters_count_back_from_settlement(stub_dart):
    """6월 결산 회사의 1분기는 9월 말이다(결산일에서 3개월씩 역산)."""
    stub_dart(_SAMSUNG_2024, fiscal_month="06")

    records = qe.fetch_quarterly_earnings("004890", start_year=2024, end_year=2024)

    assert [r["period_end"] for r in records] == [
        "2023-09-30", "2023-12-31", "2024-03-31", "2024-06-30",
    ]


def test_quota_exhaustion_raises_instead_of_returning_partial(stub_dart):
    """한도 소진은 '분기 실적 없음'이 아니다 — 부분 결과를 완성본으로 저장하면 안 된다."""
    from engine.fundamental_fetcher import DartQuotaExhausted

    stub_dart({("11013", "CFS"): {"status": "020"}})

    with pytest.raises(DartQuotaExhausted):
        qe.fetch_quarterly_earnings("005930", start_year=2024, end_year=2024)


def test_dart_call_counter_tracks_budget(stub_dart):
    stub_dart(_SAMSUNG_2024)
    qe.reset_dart_calls()

    qe.fetch_quarterly_earnings("005930", start_year=2024, end_year=2024)

    # 분기 3 + 연간 1 = 4회(기준이 첫 연도 연결에서 바로 잡혔다).
    assert qe.dart_calls_used() == 4
