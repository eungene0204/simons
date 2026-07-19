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
    assert u.normalize_sector("로봇") == "로봇"  # 독립 정본 섹터(2026-07-13 신설)
    assert u.normalize_sector("로보틱스") == "로봇"  # 산업어 동기화(sector_mapper 파생)
    assert u.normalize_sector("메타버스") is None  # 목록 밖
    assert u.normalize_sector(None) is None


def test_filter_by_sector_uses_korea_stocks_sot():
    # 실데이터(korea-stocks.json) 기준: 삼성전자/하이닉스=반도체, NAVER=소프트웨어/플랫폼.
    filtered = u.filter_by_sector(["005930", "000660", "035420"], "반도체")
    assert filtered == ["005930", "000660"]
    # 동의어 입력도 정규화되어 동작한다.
    assert u.filter_by_sector(["005930", "035420"], "인터넷") == ["035420"]
    # 미지원 섹터명은 빈 목록(엔진이 명시적 에러로 fail-fast).
    assert u.filter_by_sector(["005930"], "메타버스") == []
    # 복수 섹터는 합집합 필터(FR-STR-066 ⑦). 미지원 항목만 있으면 빈 목록.
    assert u.filter_by_sector(
        ["005930", "000660", "035420"], ["반도체", "소프트웨어/플랫폼"]
    ) == ["005930", "000660", "035420"]
    assert u.filter_by_sector(["005930"], ["메타버스"]) == []
    # 로봇 독립 섹터(2026-07-13): 두산로보틱스=로봇, 삼성전자≠로봇.
    assert u.filter_by_sector(["454910", "005930"], "로봇") == ["454910"]
    assert u.filter_by_sector(["454910", "005930"], ["반도체", "로봇"]) == ["454910", "005930"]


def test_normalize_sector_value_normal_form():
    # 정규형: 없음=None, 단일=str(하위 호환), 복수=list. 항목 정본화·미지원 드롭·순서보존 dedup.
    assert u.normalize_sector_value(None) is None
    assert u.normalize_sector_value("배터리") == "이차전지"
    assert u.normalize_sector_value(["배터리"]) == "이차전지"
    assert u.normalize_sector_value(["배터리", "2차전지", "로봇"]) == ["이차전지", "로봇"]
    assert u.normalize_sector_value(["메타버스"]) is None
    assert u.sector_value_as_list(None) == []
    assert u.sector_value_as_list("반도체") == ["반도체"]
    assert u.sector_value_as_list(["반도체", "화학"]) == ["반도체", "화학"]


# ── 상폐 종목 섹터 백필(생존 편향 제거) ──────────────────────────────────────────
# 2026-07-12: 섹터 분류가 현재 상장(korea-stocks.json)만 커버해 섹터 백테스트에서
# 기간 중 상폐된 종목이 통째로 빠졌다 — 마스터(stock-master.json)의 sector 백필을
# 병합해 상폐 종목도 섹터 유니버스에 포함시키고, 업종 미상만 경고 대상으로 남긴다.

@pytest.fixture
def synthetic_sector_sources(tmp_path, monkeypatch):
    master = [
        # 현재 상장 — 섹터는 korea-stocks.json이 정본. 마스터에 다른 값이 있어도 덮여야 한다.
        {"symbol": "AAAAAA", "market": "KOSPI", "delistingDate": None, "sector": "화학",
         "shares": 1000, "dataStart": "2015-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
        # 상폐 + sector 백필 — 섹터 필터에 포함되어야 한다(생존 편향 제거의 핵심).
        {"symbol": "BBBBBB", "market": "KOSPI", "delistingDate": "2019-06-30", "sector": "반도체",
         "shares": 500, "dataStart": "2015-01-01", "dataEnd": "2019-06-28", "hasOhlcv": True},
        # 상폐 + 업종 미상 — 필터에서 빠지고 경고 대상(sector_unknown_delisted)으로 잡힌다.
        {"symbol": "EEEEEE", "market": "KOSPI", "delistingDate": "2018-01-05", "sector": None,
         "shares": 300, "dataStart": "2015-01-01", "dataEnd": "2018-01-04", "hasOhlcv": True},
        # 현재 상장 + 업종 미상(신규 상장 등) — 필터에선 빠지지만 생존 편향 경고 대상은 아니다.
        {"symbol": "FFFFFF", "market": "KOSPI", "delistingDate": None, "sector": None,
         "shares": 300, "dataStart": "2024-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
        # 111110(보통주)의 우선주 111117 — korea-stocks(보통주만)에 없어도 모주 섹터를 물려받는다.
        {"symbol": "111117", "market": "KOSPI", "delistingDate": None, "sector": None,
         "shares": 100, "dataStart": "2015-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
    ]
    korea = [
        {"symbol": "AAAAAA", "name": "액티브", "market": "KOSPI",
         "sector": "반도체", "industry": "반도체 제조업"},
        {"symbol": "111110", "name": "모주", "market": "KOSPI",
         "sector": "반도체", "industry": "반도체 제조업"},
    ]
    master_path = tmp_path / "stock-master.json"
    master_path.write_text(json.dumps({"stocks": master}), encoding="utf-8")
    korea_path = tmp_path / "korea-stocks.json"
    korea_path.write_text(json.dumps(korea), encoding="utf-8")
    monkeypatch.setattr(u, "_MASTER_PATH", master_path)
    monkeypatch.setattr(u, "_KOREA_STOCKS_PATH", korea_path)
    u.reload_master()
    yield
    u.reload_master()


def test_filter_by_sector_includes_backfilled_delisted(synthetic_sector_sources):
    syms = ["AAAAAA", "BBBBBB", "EEEEEE"]
    assert u.filter_by_sector(syms, "반도체") == ["AAAAAA", "BBBBBB"]


def test_korea_stocks_sector_wins_over_master(synthetic_sector_sources):
    # AAAAAA는 마스터에 '화학', korea-stocks에 '반도체' — 현재 상장 SOT(korea-stocks)가 이긴다.
    assert u.filter_by_sector(["AAAAAA"], "화학") == []
    assert u.filter_by_sector(["AAAAAA"], "반도체") == ["AAAAAA"]


def test_sector_unknown_delisted_reports_only_unclassified_delisted(synthetic_sector_sources):
    # 상폐+미상(EEEEEE)만 경고 대상 — 현재 상장 미상(FFFFFF)은 생존 편향이 아니다.
    assert u.sector_unknown_delisted(["AAAAAA", "BBBBBB", "EEEEEE", "FFFFFF"]) == ["EEEEEE"]
    assert u.sector_unknown_delisted(["AAAAAA", "BBBBBB", "FFFFFF"]) == []


def test_preferred_share_inherits_common_stock_sector(synthetic_sector_sources):
    # 우선주(111117)는 모주(111110=반도체, korea-stocks 정본)의 섹터를 물려받는다.
    assert u.filter_by_sector(["111117"], "반도체") == ["111117"]
    assert u.sector_unknown_delisted(["111117"]) == []


def test_reload_master_refreshes_sector_map(synthetic_sector_sources, tmp_path):
    # 백필 스크립트 실행 후 reload_master()만으로 섹터맵 캐시도 함께 갱신되어야 한다.
    assert u.filter_by_sector(["EEEEEE"], "건설") == []
    master_path = tmp_path / "stock-master.json"
    data = json.loads(master_path.read_text(encoding="utf-8"))
    data["stocks"][2]["sector"] = "건설"
    master_path.write_text(json.dumps(data), encoding="utf-8")
    u.reload_master()
    assert u.filter_by_sector(["EEEEEE"], "건설") == ["EEEEEE"]


# ─── ETF 유니버스 ────────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_etf_master(tmp_path, monkeypatch):
    etfs = [
        {"symbol": "069500", "name": "KODEX 200",
         "dataStart": "2014-01-29", "dataEnd": "2026-07-10", "hasOhlcv": True},
        {"symbol": "091160", "name": "KODEX 반도체",
         "dataStart": "2015-01-01", "dataEnd": "2026-07-10", "hasOhlcv": True},
        {"symbol": "360750", "name": "TIGER 미국S&P500",
         "dataStart": "2020-08-07", "dataEnd": "2026-07-10", "hasOhlcv": True},
        {"symbol": "999999", "name": "가짜 미국나스닥", "dataStart": None,
         "dataEnd": None, "hasOhlcv": False},
        # 상폐 ETF(backfill_delisted_etf.py 백필분) — 살아 있던 창에만 포함돼야 한다.
        {"symbol": "152380", "name": "KODEX 구테마", "dataStart": "2015-03-02",
         "dataEnd": "2020-05-29", "hasOhlcv": True, "delistingDate": "2020-05-29"},
    ]
    path = tmp_path / "etf-master.json"
    path.write_text(json.dumps({"etfs": etfs}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(u, "_ETF_MASTER_PATH", path)
    u.reload_master()
    yield
    u.reload_master()


def test_is_etf_universe():
    assert u.is_etf_universe("etf")
    assert u.is_etf_universe("ETF")
    assert not u.is_etf_universe("kospi")
    assert not u.is_etf_universe(None)


def test_resolve_etf_symbols_alive_window(synthetic_etf_master):
    # 2020-08 상장 ETF는 2015~2019 창에는 없어야 한다(as-of).
    early = u.resolve_etf_symbols("2015-01-01", "2019-12-31")
    assert "069500" in early and "360750" not in early
    # 상폐 ETF는 살아 있던 창(~2020-05)에는 포함, 이후 창에서는 제외(생존 편향 제거).
    assert "152380" in early
    late = u.resolve_etf_symbols("2021-01-01", "2026-01-01")
    assert set(late) == {"069500", "091160", "360750"}


def test_etf_delisting_dates_and_backfill_flag(synthetic_etf_master):
    # 엔진의 상폐 강제청산 라벨("상장폐지")은 이 날짜 맵을 근거로 한다 — ETF 마스터 병합.
    dates = u.get_delisting_dates(["152380", "069500"])
    assert dates == {"152380": "2020-05-29"}
    # 상폐분이 백필된 마스터면 생존 편향 경고를 내지 않는다.
    assert u.etf_master_includes_delisted() is True


def test_filter_etf_by_theme_exact_name_wins(synthetic_etf_master):
    syms = ["069500", "091160", "360750"]
    # 정확한 상품명 매칭이면 그 종목만 — "KODEX 200"이 "KODEX 반도체"로 번지지 않는다.
    assert u.filter_etf_by_theme(syms, "KODEX 200") == ["069500"]
    # 키워드는 이름 포함 매칭.
    assert u.filter_etf_by_theme(syms, "반도체") == ["091160"]
    assert u.filter_etf_by_theme(syms, "미국") == ["360750"]
    assert u.filter_etf_by_theme(syms, "채권") == []


def test_extract_etf_theme_self_validating(synthetic_etf_master):
    # 토큰 접미사가 마스터 이름과 매칭될 때만 테마로 인정한다.
    assert u.extract_etf_theme("미국 ETF 사서 장기 보유") == "미국"
    assert u.extract_etf_theme("반도체ETF 모멘텀") == "반도체"
    assert u.extract_etf_theme("KODEX 200을 골든크로스로 매매") == "KODEX 200"
    # 매칭 안 되는 선행어("사는")는 테마가 아니다.
    assert u.extract_etf_theme("etf를 사는 전략") is None
