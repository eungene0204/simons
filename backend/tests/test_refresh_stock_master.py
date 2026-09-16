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
