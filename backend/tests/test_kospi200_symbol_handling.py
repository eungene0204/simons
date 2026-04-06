import os
import sys

sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine.strategy_converter import _extract_naver_symbol, _normalize_kospi200_symbols


def test_extract_naver_symbol_accepts_numeric_and_alphanumeric_codes():
    assert _extract_naver_symbol("/item/main.naver?code=005930") == "005930"
    assert _extract_naver_symbol("/item/main.naver?code=0126Z0") == "0126Z0"


def test_extract_naver_symbol_rejects_non_six_char_codes():
    assert _extract_naver_symbol("/item/main.naver?code=ABC") is None
    assert _extract_naver_symbol("/item/main.naver?code=1234567") is None


def test_normalize_kospi200_symbols_adds_missing_alphanumeric_constituent():
    symbols = _normalize_kospi200_symbols(["005930", "000660", "005930"])

    assert symbols == ["000660", "005930", "0126Z0"]
