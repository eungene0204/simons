"""KOSDAQ150 백테스트 유니버스 배선 — 명부로 해석하고, 못 얻으면 시장 전체로 넓히지 않는다."""
import json
import time

import pytest

from engine import strategy_converter as sc


ROSTER_SYMBOLS = [f"{i:06d}" for i in range(100000, 100150)]


@pytest.fixture
def roster(tmp_path, monkeypatch):
    """신선한 150종목 명부. 네트워크로 새지 않도록 KIS 조회는 막아둔다."""
    path = tmp_path / "kosdaq150-cache.json"
    path.write_text(
        json.dumps({"fetched_at": time.time(), "symbols": ROSTER_SYMBOLS}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sc, "_KOSDAQ150_CACHE_PATH", path)
    monkeypatch.setattr(
        sc, "_fetch_index_from_kis",
        lambda _index_id: pytest.fail("신선한 캐시가 있으면 KIS 를 다시 부르지 않는다"),
    )
    return path


def test_load_universe_reads_kosdaq150_roster(roster):
    assert sc._load_universe(["KOSDAQ150"]) == ROSTER_SYMBOLS


def test_kosdaq150_roster_is_not_widened_to_full_kosdaq(tmp_path, monkeypatch):
    """명부를 못 얻어도 KOSDAQ 전체(1,700여 종목)로 대체해서는 안 된다."""
    monkeypatch.setattr(sc, "_KOSDAQ150_CACHE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(sc, "_fetch_index_from_kis", lambda _index_id: None)

    assert sc._load_universe(["KOSDAQ150"]) == []


def test_kosdaq150_combines_with_other_markets_without_swallowing_them(roster, tmp_path, monkeypatch):
    """KOSDAQ150 + KOSPI 조합에서 KOSPI 종목이 사라지지 않아야 한다."""
    stocks = tmp_path / "korea-stocks.json"
    stocks.write_text(json.dumps([
        {"symbol": "005930", "market": "KOSPI", "name": "삼성전자"},
        {"symbol": "999999", "market": "KOSDAQ", "name": "코스닥종목"},
    ]), encoding="utf-8")
    monkeypatch.setattr(sc, "_STOCKS_PATH", stocks)

    symbols = sc._load_universe(["KOSDAQ150", "KOSPI"])

    assert "005930" in symbols, "KOSPI 종목이 지수 명부에 삼켜지면 안 된다"
    assert set(ROSTER_SYMBOLS) <= set(symbols)
    assert "999999" not in symbols, "KOSDAQ 전체가 딸려 들어오면 안 된다"


def test_stale_cache_refetches_from_kis_master(tmp_path, monkeypatch):
    path = tmp_path / "kosdaq150-cache.json"
    path.write_text(
        json.dumps({"fetched_at": 0, "symbols": ["OLD"]}), encoding="utf-8"
    )
    monkeypatch.setattr(sc, "_KOSDAQ150_CACHE_PATH", path)
    monkeypatch.setattr(sc, "_fetch_index_from_kis", lambda _index_id: ["NEW1", "NEW2"])

    assert sc._load_kosdaq150() == ["NEW1", "NEW2"]
    assert json.loads(path.read_text())["symbols"] == ["NEW1", "NEW2"]


def test_kospi200_prefers_kis_master_over_naver(tmp_path, monkeypatch):
    """KOSPI200 명부 출처를 KIS 마스터로 통일 — 네이버는 폴백으로만 쓴다."""
    path = tmp_path / "kospi200-cache.json"
    path.write_text(json.dumps({"fetched_at": 0, "symbols": ["OLD"]}), encoding="utf-8")
    monkeypatch.setattr(sc, "_KOSPI200_CACHE_PATH", path)
    monkeypatch.setattr(sc, "_fetch_index_from_kis", lambda _index_id: ["005930", "000660"])

    called = []
    monkeypatch.setattr(
        sc, "_fetch_kospi200_from_naver", lambda: called.append(True) or ["999999"]
    )

    symbols = sc._load_kospi200()

    assert called == [], "KIS 마스터가 성공하면 네이버를 호출하지 않는다"
    assert "005930" in symbols and "000660" in symbols


def test_parsed_strategy_keeps_kosdaq150_instead_of_silently_defaulting():
    """공용 DSL이 KOSDAQ150을 모르면 universe 키를 버리고 기본값 KOSPI200으로 둔갑했다."""
    from engine.nl_parser import ParsedStrategy

    assert ParsedStrategy(description="t", universe=["KOSDAQ150"]).universe == ["KOSDAQ150"]
    assert ParsedStrategy(description="t", universe=["코스닥150"]).universe == ["KOSDAQ150"]
    assert ParsedStrategy(
        description="t", universe=["KOSDAQ150", "KOSPI"]
    ).universe == ["KOSDAQ150", "KOSPI"]


def test_interpreter_and_planner_vocabulary_accept_kosdaq150():
    from strategy_conversation.interpreter.models import UniverseSpec
    from strategy_conversation.registry.capability_registry import SUPPORTED_MARKETS
    from strategy_conversation.tools.catalog import ClassifyUniverseIn, _classify_universe

    assert UniverseSpec(markets=["코스닥150"]).markets == ["KOSDAQ150"]
    assert "KOSDAQ150" in SUPPORTED_MARKETS

    hit = _classify_universe(ClassifyUniverseIn(text="코스닥 150"))
    assert (hit.universe_type, hit.canonical) == ("MARKET", "KOSDAQ150")

    # 지수명을 짚지 않은 표현을 150종목으로 좁히지 않는다.
    vague = _classify_universe(ClassifyUniverseIn(text="코스닥 대형주"))
    assert vague.canonical != "KOSDAQ150"
    assert _classify_universe(ClassifyUniverseIn(text="코스닥")).canonical == "KOSDAQ"


def test_kospi200_falls_back_to_naver_when_kis_master_fails(tmp_path, monkeypatch):
    path = tmp_path / "kospi200-cache.json"
    monkeypatch.setattr(sc, "_KOSPI200_CACHE_PATH", path)
    monkeypatch.setattr(sc, "_fetch_index_from_kis", lambda _index_id: None)
    monkeypatch.setattr(sc, "_fetch_kospi200_from_naver", lambda: ["005930"])

    assert "005930" in sc._load_kospi200()
