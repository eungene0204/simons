"""Tests for news_v2 symbol mapping."""

from news_v2.symbol_mapping import extract_tickers, map_symbols_from_text


def test_extract_tickers_finds_kr_codes():
    assert extract_tickers("삼성전자 005930, SK하이닉스 000660") == ["000660", "005930"]


def test_alias_mapping_links_preferred_share():
    rows = map_symbols_from_text(
        text="삼성전자우와 삼성전자 우선주가 동반 강세",
        target_symbol="005930",
        target_name="삼성전자",
    )

    symbols = {row["symbol"] for row in rows}
    assert "005930" in symbols
    assert "005935" in symbols


def test_sector_keyword_maps_multiple_semiconductor_names():
    rows = map_symbols_from_text(
        text="반도체 HBM 수요 확대로 메모리 업황 회복",
        target_symbol="005930",
        target_name="삼성전자",
    )

    symbols = {row["symbol"] for row in rows}
    assert "005930" in symbols
    assert "000660" in symbols
