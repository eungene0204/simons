import os
import sys
import time
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import nl_cache


def test_nl_cache_key_changes_when_universe_file_changes(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    stocks = data_dir / "korea-stocks.json"
    kospi200 = data_dir / "kospi200-cache.json"
    stocks.write_text("[]", encoding="utf-8")
    kospi200.write_text('{"symbols":[]}', encoding="utf-8")

    monkeypatch.setattr(nl_cache, "_BASE_DIR", tmp_path)
    monkeypatch.setattr(
        nl_cache,
        "_UNIVERSE_FILES",
        (stocks, kospi200),
    )

    key_before = nl_cache.nl_cache_key("prompt", "mlx", None, None)
    time.sleep(0.001)
    stocks.write_text('[{"symbol":"005930"}]', encoding="utf-8")
    key_after = nl_cache.nl_cache_key("prompt", "mlx", None, None)

    assert key_before != key_after


def test_nl_cache_key_rotates_daily(monkeypatch):
    """[회귀] '백테스트 2년' 같은 상대 기간은 파싱 시점의 오늘 기준 날짜로 변환돼 캐시되므로,
    자정을 넘기면 키가 달라져 스테일 날짜가 반환되지 않아야 한다."""
    from datetime import date as _date

    class _Day1(_date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 1)

    class _Day2(_date):
        @classmethod
        def today(cls):
            return cls(2026, 7, 2)

    monkeypatch.setattr(nl_cache, "date", _Day1)
    key_day1 = nl_cache.nl_cache_key("최근 2년 백테스트", "ollama", None, None)
    monkeypatch.setattr(nl_cache, "date", _Day2)
    key_day2 = nl_cache.nl_cache_key("최근 2년 백테스트", "ollama", None, None)

    assert key_day1 != key_day2
