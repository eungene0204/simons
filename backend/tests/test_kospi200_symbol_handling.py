import os
import sys
from unittest.mock import patch

sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine.strategy_converter import _extract_naver_symbol, _normalize_kospi200_symbols, to_backtest_request
from engine.nl_parser import ParsedStrategy


def test_extract_naver_symbol_accepts_numeric_and_alphanumeric_codes():
    assert _extract_naver_symbol("/item/main.naver?code=005930") == "005930"
    assert _extract_naver_symbol("/item/main.naver?code=0126Z0") == "0126Z0"


def test_extract_naver_symbol_rejects_non_six_char_codes():
    assert _extract_naver_symbol("/item/main.naver?code=ABC") is None
    assert _extract_naver_symbol("/item/main.naver?code=1234567") is None


def test_normalize_kospi200_symbols_adds_missing_alphanumeric_constituent():
    symbols = _normalize_kospi200_symbols(["005930", "000660", "005930"])

    assert symbols == ["000660", "005930", "0126Z0"]


@patch("engine.strategy_converter._load_universe", return_value=["005930", "000660"])
def test_to_backtest_request_includes_universe_id_for_kosdaq(_mock):
    strategy = ParsedStrategy(
        description="테스트",
        universe=["KOSDAQ"],
        entry_signals=[],
        exit_signals=[],
        fundamental_filters=[],
    )
    req = to_backtest_request(strategy)
    assert req["universe_id"] == "kosdaq"


@patch("engine.strategy_converter._load_universe", return_value=["005930"])
def test_to_backtest_request_includes_universe_id_for_mixed(_mock):
    strategy = ParsedStrategy(
        description="테스트",
        universe=["KOSPI", "KOSDAQ"],
        entry_signals=[],
        exit_signals=[],
        fundamental_filters=[],
    )
    req = to_backtest_request(strategy)
    assert "kospi" in req["universe_id"] and "kosdaq" in req["universe_id"]
