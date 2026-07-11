"""Point-in-time (survivorship-bias-free) universe resolution tests."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine import universe_pit as u


@pytest.fixture
def synthetic_master(tmp_path, monkeypatch):
    stocks = [
        # active KOSPI, large
        {"symbol": "AAAAAA", "market": "KOSPI", "delistingDate": None,
         "shares": 1000, "dataStart": "2015-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
        # KOSPI delisted mid-2019 — must appear only while alive
        {"symbol": "BBBBBB", "market": "KOSPI", "delistingDate": "2019-06-30",
         "shares": 500, "dataStart": "2015-01-01", "dataEnd": "2019-06-28", "hasOhlcv": True},
        # KOSDAQ active
        {"symbol": "CCCCCC", "market": "KOSDAQ", "delistingDate": None,
         "shares": 200, "dataStart": "2016-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
        # no local OHLCV — never tradeable
        {"symbol": "DDDDDD", "market": "KOSPI", "delistingDate": None,
         "shares": 300, "dataStart": None, "dataEnd": None, "hasOhlcv": False},
    ]
    path = tmp_path / "stock-master.json"
    path.write_text(json.dumps({"stocks": stocks}), encoding="utf-8")
    monkeypatch.setattr(u, "_MASTER_PATH", path)
    u.reload_master()
    yield
    u.reload_master()


def test_parse_universe_markets():
    assert u.parse_universe_markets("kospi") == (["KOSPI"], False)
    assert u.parse_universe_markets("kospi200") == (["KOSPI"], True)
    assert u.parse_universe_markets("kosdaq_kospi") == (["KOSPI", "KOSDAQ"], False)
    # custom symbol sets must be left untouched (no market universe)
    assert u.parse_universe_markets(None) == ([], False)
    assert u.parse_universe_markets("my_custom_list") == ([], False)


def test_delisted_name_included_while_alive(synthetic_master):
    # The whole point: a stock that has since delisted is in the universe for the
    # window it was actually trading — this is what removes survivorship bias.
    syms = u.resolve_symbols("kospi", "2016-01-01", "2018-12-31")
    assert "BBBBBB" in syms
    assert "AAAAAA" in syms


def test_delisted_name_excluded_after_delisting(synthetic_master):
    syms = u.resolve_symbols("kospi", "2024-01-01", "2026-01-01")
    assert "BBBBBB" not in syms
    assert "AAAAAA" in syms


def test_delisted_name_excluded_before_listing_coverage(synthetic_master):
    # Window entirely after the stock stopped trading → excluded.
    syms = u.resolve_symbols("kospi", "2020-01-01", "2021-01-01")
    assert "BBBBBB" not in syms


def test_symbol_without_ohlcv_is_excluded(synthetic_master):
    syms = u.resolve_symbols("kospi", "2015-01-01", "2026-01-01")
    assert "DDDDDD" not in syms


def test_market_filter(synthetic_master):
    assert "CCCCCC" not in u.resolve_symbols("kospi", "2016-01-01", "2026-01-01")
    assert "CCCCCC" in u.resolve_symbols("kosdaq", "2016-01-01", "2026-01-01")
    both = u.resolve_symbols("kosdaq_kospi", "2016-01-01", "2026-01-01")
    assert "AAAAAA" in both and "CCCCCC" in both


def test_custom_universe_returns_none(synthetic_master):
    # None signals the engine to keep the caller-provided symbol list as-is.
    assert u.resolve_symbols(None, "2016-01-01", "2026-01-01") is None


def test_full_period_uses_start_floor(synthetic_master):
    # start=None (period=FULL) must still resolve via the default floor, not crash.
    syms = u.resolve_symbols("kospi", None, "2026-01-01")
    assert "AAAAAA" in syms


def test_get_shares(synthetic_master):
    assert u.get_shares(["AAAAAA", "BBBBBB"]) == {"AAAAAA": 1000.0, "BBBBBB": 500.0}


# ── 섹터 유니버스 ────────────────────────────────────────────────────────────

def test_normalize_sector_canonical_and_synonyms():
    assert u.normalize_sector("반도체") == "반도체"
    assert u.normalize_sector("2차전지") == "이차전지"
    assert u.normalize_sector("배터리") == "이차전지"
    assert u.normalize_sector("제약") == "바이오/제약"
    assert u.normalize_sector("바이오/제약") == "바이오/제약"
    assert u.normalize_sector("반도체 소재") == "반도체 소재"  # 공백 무시
    assert u.normalize_sector("로봇") is None  # 목록 밖
    assert u.normalize_sector(None) is None


def test_filter_by_sector_uses_korea_stocks_sot():
    # 실데이터(korea-stocks.json) 기준: 삼성전자/하이닉스=반도체, NAVER=소프트웨어/플랫폼.
    filtered = u.filter_by_sector(["005930", "000660", "035420"], "반도체")
    assert filtered == ["005930", "000660"]
    # 동의어 입력도 정규화되어 동작한다.
    assert u.filter_by_sector(["005930", "035420"], "인터넷") == ["035420"]
    # 미지원 섹터명은 빈 목록(엔진이 명시적 에러로 fail-fast).
    assert u.filter_by_sector(["005930"], "로봇") == []
