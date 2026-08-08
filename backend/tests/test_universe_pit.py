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
        # active KOSPI, large (common stock — symbol ends in "0")
        {"symbol": "AAAAA0", "market": "KOSPI", "delistingDate": None,
         "shares": 1000, "dataStart": "2015-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
        # KOSPI delisted mid-2019 — must appear only while alive
        {"symbol": "BBBBB0", "market": "KOSPI", "delistingDate": "2019-06-30",
         "shares": 500, "dataStart": "2015-01-01", "dataEnd": "2019-06-28", "hasOhlcv": True},
        # KOSDAQ active
        {"symbol": "CCCCC0", "market": "KOSDAQ", "delistingDate": None,
         "shares": 200, "dataStart": "2016-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
        # no local OHLCV — never tradeable
        {"symbol": "DDDDD0", "market": "KOSPI", "delistingDate": None,
         "shares": 300, "dataStart": None, "dataEnd": None, "hasOhlcv": False},
        # active KOSPI SPAC — must never enter the universe (rebalancing safety)
        {"symbol": "EEEEE0", "market": "KOSPI", "delistingDate": None, "name": "한국제10호스팩",
         "shares": 100, "dataStart": "2015-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
        # active KOSPI preferred share (symbol ends in non-"0") — must never enter the universe
        {"symbol": "FFFFF5", "market": "KOSPI", "delistingDate": None, "name": "테스트홀딩스우",
         "shares": 50, "dataStart": "2015-01-01", "dataEnd": "2026-06-01", "hasOhlcv": True},
    ]
    path = tmp_path / "stock-master.json"
    path.write_text(json.dumps({"stocks": stocks}), encoding="utf-8")
    monkeypatch.setattr(u, "_MASTER_PATH", path)
    u.reload_master()
    yield
    u.reload_master()


def test_parse_universe_markets():
    assert u.parse_universe_markets("kospi") == (["KOSPI"], None)
    assert u.parse_universe_markets("kospi200") == (["KOSPI"], 200)
    assert u.parse_universe_markets("kosdaq_kospi") == (["KOSPI", "KOSDAQ"], None)
    # custom symbol sets must be left untouched (no market universe)
    assert u.parse_universe_markets(None) == ([], None)
    assert u.parse_universe_markets("my_custom_list") == ([], None)


def test_parse_universe_markets_kosdaq150():
    """KOSDAQ150 은 KOSDAQ 시장의 시점 기준 시총 상위 150으로 근사한다."""
    assert u.parse_universe_markets("kosdaq150") == (["KOSDAQ"], 150)
    # 지수 토큰이 둘이면 시장별로 순위를 나눠 매길 수 없어 미인식 처리한다.
    assert u.parse_universe_markets("kosdaq150_kospi200") == ([], None)
    # 지수 + 다른 시장이 섞이면 순위 게이트가 그 시장까지 잘라내므로 게이트를 끈다.
    assert u.parse_universe_markets("kosdaq150_kospi") == (["KOSPI", "KOSDAQ"], None)


def test_delisted_name_included_while_alive(synthetic_master):
    # The whole point: a stock that has since delisted is in the universe for the
    # window it was actually trading — this is what removes survivorship bias.
    syms = u.resolve_symbols("kospi", "2016-01-01", "2018-12-31")
    assert "BBBBB0" in syms
    assert "AAAAA0" in syms


def test_delisted_name_excluded_after_delisting(synthetic_master):
    syms = u.resolve_symbols("kospi", "2024-01-01", "2026-01-01")
    assert "BBBBB0" not in syms
    assert "AAAAA0" in syms


def test_delisted_name_excluded_before_listing_coverage(synthetic_master):
    # Window entirely after the stock stopped trading → excluded.
    syms = u.resolve_symbols("kospi", "2020-01-01", "2021-01-01")
    assert "BBBBB0" not in syms


def test_symbol_without_ohlcv_is_excluded(synthetic_master):
    syms = u.resolve_symbols("kospi", "2015-01-01", "2026-01-01")
    assert "DDDDD0" not in syms


def test_market_filter(synthetic_master):
    assert "CCCCC0" not in u.resolve_symbols("kospi", "2016-01-01", "2026-01-01")
    assert "CCCCC0" in u.resolve_symbols("kosdaq", "2016-01-01", "2026-01-01")
    both = u.resolve_symbols("kosdaq_kospi", "2016-01-01", "2026-01-01")
    assert "AAAAA0" in both and "CCCCC0" in both


def test_custom_universe_returns_none(synthetic_master):
    # None signals the engine to keep the caller-provided symbol list as-is.
    assert u.resolve_symbols(None, "2016-01-01", "2026-01-01") is None


def test_full_period_uses_start_floor(synthetic_master):
    # start=None (period=FULL) must still resolve via the default floor, not crash.
    syms = u.resolve_symbols("kospi", None, "2026-01-01")
    assert "AAAAA0" in syms


def test_get_shares(synthetic_master):
    assert u.get_shares(["AAAAA0", "BBBBB0"]) == {"AAAAA0": 1000.0, "BBBBB0": 500.0}


def test_spac_excluded_from_universe(synthetic_master):
    # SPAC(기업인수목적회사)은 리밸런싱/랭킹 유니버스에 절대 섞이면 안 된다.
    assert "EEEEE0" not in u.resolve_symbols("kospi", "2016-01-01", "2026-01-01")


def test_preferred_share_excluded_from_universe(synthetic_master):
    # 우선주(끝자리≠0)는 백테스트/리밸런싱 유니버스에 절대 섞이면 안 된다.
    assert "FFFFF5" not in u.resolve_symbols("kospi", "2016-01-01", "2026-01-01")


def test_is_preferred_detects_symbol_suffix():
    assert u._is_preferred("005935")   # 삼성전자우
    assert u._is_preferred("00088K")   # 신형 영문 종목코드 우선주
    assert not u._is_preferred("005930")  # 삼성전자(보통주)
    assert not u._is_preferred("")


def test_is_spac_detects_name_variants():
    assert u._is_spac("한국제10호스팩")
    assert u._is_spac("DB금융스팩10호")
    assert not u._is_spac("동화약품")
    assert not u._is_spac("")


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
    # 섹터 소속의 정본은 KG다(2026-07-30). 이 픽스처는 **파일 병합 규칙**
    # (마스터→korea-stocks 우선순위·우선주 상속)을 검증하므로 KG 경로를 비워
    # sector_map_from_files 폴백이 합성 데이터를 읽게 한다.
    monkeypatch.setattr(u, "_sector_map_from_graph", lambda: {})
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


def test_resolve_single_etf_product(synthetic_etf_master):
    # 정확한 상품명이면 그 마스터 항목을 반환한다(단일 종목 판정 근거).
    single = u.resolve_single_etf_product("KODEX 반도체")
    assert single is not None and single["symbol"] == "091160"
    # 여러 ETF에 걸치는 테마 키워드는 단일 상품이 아니다.
    assert u.resolve_single_etf_product("반도체") is None
    assert u.resolve_single_etf_product(None) is None
    assert u.resolve_single_etf_product("") is None


def test_extract_etf_theme_self_validating(synthetic_etf_master):
    # 토큰 접미사가 마스터 이름과 매칭될 때만 테마로 인정한다.
    assert u.extract_etf_theme("미국 ETF 사서 장기 보유") == "미국"
    assert u.extract_etf_theme("반도체ETF 모멘텀") == "반도체"
    assert u.extract_etf_theme("KODEX 200을 골든크로스로 매매") == "KODEX 200"
    # 매칭 안 되는 선행어("사는")는 테마가 아니다.
    assert u.extract_etf_theme("etf를 사는 전략") is None


# ── 신규 상장 유니버스 (FR-STR-073) ──────────────────────────────────────────

@pytest.fixture
def listing_master(tmp_path, monkeypatch):
    stocks = [
        # 오래된 종목 — 상장일이 백필 하한(dataStart)보다 훨씬 앞선다.
        {"symbol": "OLD000", "market": "KOSPI", "delistingDate": None,
         "listingDate": "1975-06-11", "dataStart": "2013-12-18",
         "dataEnd": "2026-06-01", "hasOhlcv": True},
        # 2025년 IPO — 상장일과 데이터 시작이 같다.
        {"symbol": "IPO250", "market": "KOSDAQ", "delistingDate": None,
         "listingDate": "2025-06-02", "dataStart": "2025-06-02",
         "dataEnd": "2026-06-01", "hasOhlcv": True},
        # 이전상장/재상장 — KIND 상장일은 최근이지만 그 전부터 거래됐다.
        {"symbol": "MOVE00", "market": "KOSDAQ", "delistingDate": None,
         "listingDate": "2025-06-30", "dataStart": "2022-12-23",
         "dataEnd": "2026-06-01", "hasOhlcv": True},
        # 상장일 미상(KIND 미커버) — dataStart가 하한 역할을 한다.
        {"symbol": "NODATE", "market": "KOSDAQ", "delistingDate": None,
         "listingDate": None, "dataStart": "2016-08-08",
         "dataEnd": "2026-06-01", "hasOhlcv": True},
        # 근거가 전혀 없는 종목 — 신규 상장 판정에서 제외되고 보고된다.
        {"symbol": "UNKNWN", "market": "KOSDAQ", "delistingDate": None,
         "listingDate": None, "dataStart": None, "dataEnd": None, "hasOhlcv": False},
        # 기간 중 상장했다가 상폐 — 생존 편향 없이 당시 신규 상장으로 잡혀야 한다.
        {"symbol": "GONE00", "market": "KOSDAQ", "delistingDate": "2019-06-30",
         "listingDate": "2018-03-02", "dataStart": "2018-03-02",
         "dataEnd": "2019-06-28", "hasOhlcv": True},
    ]
    path = tmp_path / "stock-master.json"
    path.write_text(json.dumps({"stocks": stocks}), encoding="utf-8")
    monkeypatch.setattr(u, "_MASTER_PATH", path)
    u.reload_master()
    yield
    u.reload_master()


def test_first_listed_date_prefers_earlier_evidence(listing_master):
    # 이전상장은 KIND 상장일(2025-06-30)이 아니라 실제 거래 시작일이 최초 상장일이다 —
    # 그러지 않으면 2022년부터 거래된 종목이 2025년 신규 상장으로 둔갑한다.
    dates = u.first_listed_dates(["OLD000", "IPO250", "MOVE00", "NODATE", "UNKNWN"])
    assert dates["OLD000"] == "1975-06-11"
    assert dates["IPO250"] == "2025-06-02"
    assert dates["MOVE00"] == "2022-12-23"
    assert dates["NODATE"] == "2016-08-08"   # 상장일 미상 → dataStart가 하한
    assert "UNKNWN" not in dates              # 근거 없음 → 키 자체가 없다


def test_filter_by_listing_window_year_cohort(listing_master):
    symbols = ["OLD000", "IPO250", "MOVE00", "NODATE", "UNKNWN"]
    # "2025년 신규 상장" = 상장일이 2025년인 종목. 이전상장(실제 2022년 거래 시작)은 빠진다.
    kept, unknown = u.filter_by_listing_window(symbols, "2025-01-01", "2025-12-31")
    assert kept == ["IPO250"]
    assert unknown == ["UNKNWN"]


def test_filter_by_listing_window_open_upper_bound(listing_master):
    # "2016년 이후 상장" — 상한이 없으면 그 뒤 상장분을 모두 포함한다.
    kept, _ = u.filter_by_listing_window(
        ["OLD000", "IPO250", "MOVE00", "NODATE"], "2016-01-01", None
    )
    assert kept == ["IPO250", "MOVE00", "NODATE"]


def test_filter_by_listing_window_includes_delisted_names(listing_master):
    # 상장 후 상폐된 종목도 그 해엔 신규 상장이었다(생존 편향 제거).
    kept, _ = u.filter_by_listing_window(["OLD000", "GONE00"], "2018-01-01", "2018-12-31")
    assert kept == ["GONE00"]


def test_filter_by_listing_window_reports_unknown_listing_dates(listing_master):
    # 상장일 근거가 없는 종목은 조용히 통과시키지 않고 제외 후 보고한다.
    kept, unknown = u.filter_by_listing_window(["IPO250", "UNKNWN"], "2025-01-01", None)
    assert kept == ["IPO250"]
    assert unknown == ["UNKNWN"]
