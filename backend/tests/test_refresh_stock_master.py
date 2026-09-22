"""종목 마스터 제자리 갱신(scripts/refresh_stock_master.py) 회귀.

사고(2026-09-16): 마스터가 2026-06-13 생성본에서 멈춰 있어 ① 그 뒤 상장폐지된 24종목이
백테스트 유니버스에서 통째로 빠졌고, ② 창 시작이 마스터의 가격 커버리지 끝보다 뒤인
백테스트는 as-of 해석이 0종목이 돼 '현재 상장 종목' 목록으로 조용히 폴백했다(생존 편향).

갱신은 전체 재빌드가 아니라 제자리 병합이어야 한다 — 재빌드는 마스터에 누적된 섹터
후처리(묶음 분류 분할·외과 패치)를 되돌린다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.refresh_stock_master import refresh  # noqa: E402


def _master() -> dict:
    return {
        "generatedAt": "2026-06-13T04:49:16+09:00",
        "delistingFloor": "2015-01-01",
        "counts": {"total": 2},
        "stocks": [
            {
                "symbol": "005930", "name": "삼성전자", "market": "KOSPI", "secuGroup": "주권",
                "listingDate": "1975-06-11", "delistingDate": None, "shares": 100,
                "reason": None, "toSymbol": None,
                "dataStart": "2015-01-02", "dataEnd": "2026-06-12", "hasOhlcv": True,
            },
            {
                "symbol": "900110", "name": "옛종목", "market": "KOSDAQ", "secuGroup": "주권",
                "listingDate": "2011-05-20", "delistingDate": None, "shares": 10,
                "reason": None, "toSymbol": None,
                "industry": "기타", "sector": "소재",   # 후처리로 손질된 값
                "dataStart": "2015-01-02", "dataEnd": "2026-06-12", "hasOhlcv": True,
            },
        ],
    }


def test_refresh_updates_coverage_and_new_delistings_without_losing_curation():
    coverage = {"005930": ("2015-01-02", "2026-09-15"), "900110": ("2015-01-02", "2026-08-01")}
    active = {"005930": {"symbol": "005930", "name": "삼성전자", "market": "KOSPI",
                         "secuGroup": "주권", "listingDate": "1975-06-11", "delistingDate": None,
                         "shares": 120, "reason": None, "toSymbol": None}}
    delisted = {"900110": {"symbol": "900110", "name": "옛종목", "market": "KOSDAQ",
                           "secuGroup": "주권", "listingDate": "2011-05-20",
                           "delistingDate": "2026-08-04", "shares": 10, "reason": "감사의견 거절",
                           "toSymbol": None, "industry": "다른업종", "sector": "다른섹터"}}

    out = refresh(_master(), coverage, active, delisted)
    rows = {s["symbol"]: s for s in out["stocks"]}

    # ① 가격 커버리지는 로컬 parquet이 정본
    assert rows["005930"]["dataEnd"] == "2026-09-15"
    # ② 신규 상장폐지 반영
    assert rows["900110"]["delistingDate"] == "2026-08-04"
    assert rows["900110"]["reason"] == "감사의견 거절"
    # ③ 후처리로 손질된 분류는 보존(재빌드였다면 '다른업종/다른섹터'로 덮였다)
    assert rows["900110"]["industry"] == "기타"
    assert rows["900110"]["sector"] == "소재"
    # ④ 활성 행의 상장주식수는 갱신(시점 시총 랭킹의 입력)
    assert rows["005930"]["shares"] == 120
    assert out["counts"]["delisted"] == 1


def test_refresh_adds_new_symbols_and_drops_nothing():
    coverage = {"005930": ("2015-01-02", "2026-09-15"), "999999": ("2026-07-01", "2026-09-15")}
    active = {"999999": {"symbol": "999999", "name": "신규상장", "market": "KOSDAQ",
                         "secuGroup": "주권", "listingDate": "2026-07-01", "delistingDate": None,
                         "shares": 5, "reason": None, "toSymbol": None}}

    out = refresh(_master(), coverage, active, {})
    rows = {s["symbol"]: s for s in out["stocks"]}

    assert set(rows) == {"005930", "900110", "999999"}   # 기존 행은 하나도 사라지지 않는다
    assert rows["999999"]["dataStart"] == "2026-07-01"
    # 로컬 가격이 없는 행은 hasOhlcv=False로 내려가 as-of 유니버스에서 빠진다
    assert rows["900110"]["hasOhlcv"] is False


def test_refresh_is_idempotent():
    coverage = {"005930": ("2015-01-02", "2026-09-15"), "900110": ("2015-01-02", "2026-08-01")}
    once = refresh(_master(), coverage, {}, {})
    twice = refresh(once, coverage, {}, {})
    assert once["stocks"] == twice["stocks"]


# ── 상류 출처가 죽었을 때(2026-09-22 실측) ──────────────────────────────────────
# 야간 갱신이 FDR의 두 목록에 기대고 있었는데 같은 날 둘 다 고장났다:
#   · KRX-DESC(상장일) → HTTP 404
#   · KRX-DELISTING(상폐 명부) → 빈 표(행 0·컬럼 0)
# 첫째는 KIND 직접 호출로 옮겼고, 둘째는 '조용한 0건'이 되지 않도록 전용 예외로 올린 뒤
# 호출부가 나머지 갱신을 진행한다 — 이 단계에서 죽으면 신규 상장·가격 커버리지까지 멈춰
# 마스터가 통째로 낡고, 그게 생존편향이 되살아나는 경로다.

def test_empty_delisting_response_is_an_error_not_zero_delistings():
    import pandas as pd
    import pytest

    from scripts.build_stock_master import DelistingSourceUnavailable, _load_delisted

    class _Dead:
        @staticmethod
        def StockListing(_key):
            return pd.DataFrame()

    with pytest.raises(DelistingSourceUnavailable):
        _load_delisted(_Dead())

    class _Partial:
        @staticmethod
        def StockListing(_key):
            return pd.DataFrame({"Symbol": ["000000"], "Name": ["x"]})   # 컬럼이 모자란다

    with pytest.raises(DelistingSourceUnavailable):
        _load_delisted(_Partial())


def test_listing_dates_come_from_kind_and_fall_back_to_fdr(monkeypatch):
    """상장일 출처는 KIND 직접 호출이고, 막히면 FDR로 폴백한다(2026-09-22 KRX-DESC 404)."""
    import pandas as pd

    from scripts import build_stock_master as bsm

    monkeypatch.setattr(bsm, "_fetch_kind_listing_table", lambda: pd.DataFrame(
        {"종목코드": ["5930", "0220W0"], "상장일": ["1975-06-11", "2026-08-25"]}))
    dates = bsm.load_kind_listing_dates()
    assert dates == {"005930": "1975-06-11", "0220W0": "2026-08-25"}   # 6자리로 채운다

    def _dead():
        raise RuntimeError("KIND 404")

    monkeypatch.setattr(bsm, "_fetch_kind_listing_table", _dead)
    monkeypatch.setitem(sys.modules, "FinanceDataReader", type("F", (), {
        "StockListing": staticmethod(lambda key: pd.DataFrame(
            {"Code": ["005930"], "ListingDate": ["1975-06-11"]})),
    }))
    assert bsm.load_kind_listing_dates() == {"005930": "1975-06-11"}


def test_refresh_keeps_existing_delistings_when_the_source_is_down():
    """상폐 출처가 죽은 날에도 기존 상폐 행은 남는다 — 잃는 것은 새 상폐분뿐이다."""
    master = _master()
    master["stocks"][1]["delistingDate"] = "2026-06-20"

    payload = refresh(master, {"005930": ("2015-01-02", "2026-09-18")}, {}, {})

    delisted = [s for s in payload["stocks"] if s.get("delistingDate")]
    assert [s["symbol"] for s in delisted] == [master["stocks"][1]["symbol"]]
    assert payload["counts"]["delisted"] == 1


# ── 상폐 추론: 현행 목록 이탈 + 가격 중단 (2026-09-22, 상류 명부 대체) ──────────────

def _absence_master() -> dict:
    return {"stocks": [
        {"symbol": "111110", "name": "폐지된회사", "market": "KOSPI", "delistingDate": None},
        {"symbol": "222220", "name": "목록누락후거래중", "market": "KOSPI", "delistingDate": None},
        {"symbol": "333330", "name": "상장중", "market": "KOSPI", "delistingDate": None},
        {"symbol": "444440", "name": "이미상폐", "market": "KOSPI", "delistingDate": "2020-01-02"},
    ]}


_COVERAGE = {
    "111110": ("2015-01-02", "2026-09-04"),   # 2주 전 멈춤
    "222220": ("2015-01-02", "2026-09-18"),   # 가격은 계속 붙는다
    "333330": ("2015-01-02", "2026-09-18"),
    "444440": ("2015-01-02", "2019-12-30"),
}


def test_absence_plus_stalled_prices_infers_a_delisting():
    from scripts.build_stock_master import infer_delistings_from_absence

    found, hold = infer_delistings_from_absence(
        _absence_master(), _COVERAGE, {"333330": {}})   # 현행 목록엔 333330만 있다

    assert hold is None
    assert set(found) == {"111110"}                      # 222220은 가격이 살아 있어 제외
    assert found["111110"]["delistingDate"] == "2026-09-04"   # 상폐일 = 마지막 거래일
    assert "추론" in found["111110"]["reason"]


def test_mass_absence_is_treated_as_a_listing_fetch_failure():
    """목록이 통째로 덜 왔을 때 수백 종목을 상폐로 찍으면 유니버스가 무너진다 — 전부 보류."""
    from scripts.build_stock_master import infer_delistings_from_absence

    master = {"stocks": [
        {"symbol": f"{i:06d}", "name": f"종목{i}", "market": "KOSPI", "delistingDate": None}
        for i in range(100)
    ]}
    coverage = {f"{i:06d}": ("2015-01-02", "2026-08-01") for i in range(100)}
    coverage["999990"] = ("2015-01-02", "2026-09-18")      # 시장 최신 거래일을 세우는 종목

    found, hold = infer_delistings_from_absence(master, coverage, {"999990": {}})

    assert found == {} and hold and "상한" in hold


def test_upstream_delisting_row_wins_over_inference():
    """상류가 살아 있으면 그쪽 값(사유·이전 종목코드)을 쓴다 — 추론은 빈 칸만 메운다."""
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from scripts.build_stock_master import infer_delistings_from_absence

    delisted = {"111110": {"symbol": "111110", "name": "폐지된회사", "market": "KOSPI",
                           "delistingDate": "2026-09-05", "reason": "상장폐지(합병)",
                           "toSymbol": "005930"}}
    inferred, _ = infer_delistings_from_absence(_absence_master(), _COVERAGE, {"333330": {}})
    for symbol, row in inferred.items():
        if symbol not in delisted:
            delisted[symbol] = row

    assert delisted["111110"]["reason"] == "상장폐지(합병)"
    assert delisted["111110"]["toSymbol"] == "005930"
