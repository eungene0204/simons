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


def test_nl_cache_key_includes_pending_question():
    """같은 답('3억원')이라도 어떤 되묻기에 대한 답이냐에 따라 귀속 필드가 달라진다 —
    질문을 키에서 빼면 앞선 질문의 해석 결과가 그대로 재사용된다(pending_ask와 같은 계약)."""
    capital_q = "초기자금을 얼마로 변경할까요?"
    period_q = "백테스트 기간을 어떻게 변경할까요?"
    prev = {"universe": ["KOSPI"]}
    assert (
        nl_cache.nl_cache_key("3억원", "ollama", None, prev, None, capital_q)
        != nl_cache.nl_cache_key("3억원", "ollama", None, prev, None, period_q)
    )
    # 질문이 없는 턴(기존 호출부)은 키가 달라지지 않아야 한다 — 하위 호환.
    assert (
        nl_cache.nl_cache_key("3억원", "ollama", None, prev)
        == nl_cache.nl_cache_key("3억원", "ollama", None, prev, None, None)
    )


def test_cache_key_separates_region_and_prompt_version(monkeypatch):
    """[회귀] 2026-08-27 — 지역·프롬프트 버전이 키에 없어 캐시가 결과를 섞었다.

    표시 언어가 곧 지역이다(/us=en, KR=ko — lib/geo/region). 지역은 유니버스 기본값
    (SP500 vs KOSPI200)·지역 격리 가드·되묻기 언어를 좌우하는데 키에 없어서 **먼저 온
    지역의 결과를 다른 지역이 받았다**(실측: /us 게이트가 KR 문맥 캐시를 그대로 받음).
    프롬프트 버전도 같은 이유다 — 해석 프롬프트를 고쳐도 캐시가 옛 결과를 돌려줘
    QA 게이트가 수정 전을 재측정했다(4.9 적용 후 100건 중 1건만 새 프롬프트로 파싱).
    """
    import ui_language
    from nl_cache import nl_cache_key

    ko = nl_cache_key("Buy SPY", "ollama", None, None)
    with ui_language.bind("en"):
        en = nl_cache_key("Buy SPY", "ollama", None, None)
    assert ko != en, "지역이 다른데 캐시 키가 같다 — 응답이 섞인다"

    import nl_cache

    monkeypatch.setattr(nl_cache, "_interpreter_prompt_version", lambda: "9.9")
    bumped = nl_cache_key("Buy SPY", "ollama", None, None)
    assert bumped != ko, "프롬프트 버전이 바뀌었는데 캐시 키가 같다 — 옛 결과가 남는다"
