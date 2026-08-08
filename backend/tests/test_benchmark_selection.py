"""벤치마크 선택 회귀 테스트 (엔진 v11.0).

두 가지 오배정을 고정한다:

  - 코스피+코스닥 혼합 유니버스가 코스닥150과 비교되던 검사 순서 문제
  - universe_id가 없는 백테스트(지정 종목·테마 유니버스)가 보유 종목의 시장과
    무관하게 항상 KODEX 200과 비교되던 문제

벤치마크는 "이 전략을 쓰지 않았다면 대신 들고 있었을 것"의 대체재여야 하므로,
비교 대상이 틀리면 buyAndHoldReturn 전체가 무의미해진다.
"""
import pytest

from backtest_engine import BacktestEngine
from engine import universe_pit


KODEX_200 = ("069500", "KODEX 200 (069500)")
KODEX_KOSPI = ("226490", "KODEX 코스피 (226490)")
KODEX_KOSDAQ150 = ("229200", "KODEX KOSDAQ 150 (229200)")


@pytest.mark.parametrize(
    "universe_id,expected",
    [
        ("kospi200", KODEX_200),
        ("kospi", KODEX_KOSPI),
        ("kosdaq", KODEX_KOSDAQ150),
        # kosdaq150 유니버스의 벤치마크는 코스닥 전체와 같은 상품이다(코스피200과
        # 달리 별도 지수 ETF를 쓰지 않는다). 회귀 전에는 토큰을 몰라 KODEX 200으로
        # 떨어졌다 — 이번에 고친 오배정과 같은 종류.
        ("kosdaq150", KODEX_KOSDAQ150),
        # 회귀: 혼합 유니버스가 코스닥을 먼저 검사하는 순서 탓에 코스닥150과
        # 비교되던 문제. 코스피 전 종목 지수가 대형주 200종목 지수보다 가깝다.
        ("kospi_kosdaq", KODEX_KOSPI),
        ("kosdaq_kospi", KODEX_KOSPI),
        # ETF 유니버스는 시장 토큰이 없어 기본값으로 남는다.
        ("etf", KODEX_200),
    ],
)
def test_benchmark_follows_universe_markets(universe_id, expected):
    assert BacktestEngine.benchmark_for_universe(universe_id) == expected


def test_benchmark_infers_market_from_symbols_when_universe_id_is_empty(monkeypatch):
    """지정 종목·테마 유니버스는 universe_id가 None이라 시장 정보가 사라진다.

    회귀 전에는 코스닥 종목만 담긴 백테스트도 KODEX 200과 비교됐다.
    """
    monkeypatch.setattr(universe_pit, "dominant_market", lambda symbols: "KOSDAQ")
    assert BacktestEngine.benchmark_for_universe("", ["035720"]) == KODEX_KOSDAQ150

    monkeypatch.setattr(universe_pit, "dominant_market", lambda symbols: "KOSPI")
    assert BacktestEngine.benchmark_for_universe("", ["005930"]) == KODEX_KOSPI


def test_explicit_universe_id_wins_over_symbol_inference(monkeypatch):
    """universe_id가 시장을 명시하면 심볼 추론은 하지 않는다."""
    called = []
    monkeypatch.setattr(
        universe_pit, "dominant_market", lambda symbols: called.append(symbols) or "KOSDAQ"
    )
    assert BacktestEngine.benchmark_for_universe("kospi200", ["035720"]) == KODEX_200
    assert called == []


def test_benchmark_falls_back_when_market_unknown(monkeypatch):
    """ETF처럼 주식 마스터에 없는 심볼만 있으면 기본값(KODEX 200)."""
    monkeypatch.setattr(universe_pit, "dominant_market", lambda symbols: None)
    assert BacktestEngine.benchmark_for_universe("", ["069500"]) == KODEX_200
    assert BacktestEngine.benchmark_for_universe("", []) == KODEX_200


# ── dominant_market ──────────────────────────────────────────────────────────

def _master(rows):
    return lambda: rows


def test_dominant_market_majority_vote(monkeypatch):
    monkeypatch.setattr(
        universe_pit,
        "_load_master",
        _master(
            [
                {"symbol": "A", "market": "KOSDAQ"},
                {"symbol": "B", "market": "KOSDAQ"},
                {"symbol": "C", "market": "KOSPI"},
            ]
        ),
    )
    assert universe_pit.dominant_market(["A", "B", "C"]) == "KOSDAQ"
    assert universe_pit.dominant_market(["C"]) == "KOSPI"


def test_dominant_market_ties_go_to_kospi(monkeypatch):
    monkeypatch.setattr(
        universe_pit,
        "_load_master",
        _master([{"symbol": "A", "market": "KOSDAQ"}, {"symbol": "B", "market": "KOSPI"}]),
    )
    assert universe_pit.dominant_market(["A", "B"]) == "KOSPI"


def test_dominant_market_returns_none_when_unresolvable(monkeypatch):
    monkeypatch.setattr(universe_pit, "_load_master", _master([{"symbol": "A", "market": "KOSPI"}]))
    assert universe_pit.dominant_market([]) is None
    assert universe_pit.dominant_market(["069500"]) is None
