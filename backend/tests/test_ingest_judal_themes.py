"""주달 테마 수집기 파서 — 2026-10 사이트 마크업 변경 회귀(네트워크 불필요).

사고: 테마명이 <span> 밖으로 나오고 종목 링크가 네이버 증권 주소로 바뀌어 옛 파서가
테마 0개를 돌려줬고, 0개가 조용히 통과해 카탈로그 갱신이 죽어 있었다."""

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ingest_judal_themes.py"
_spec = importlib.util.spec_from_file_location("simons_ingest_judal", _PATH)
judal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judal)

_MAIN_HTML = """
<li data-cat="neg" data-score="13" data-order="194" class="hide"><a href="https://www.judal.co.kr/?view=stockList&themeIdx=53">여행<span>(9)</span></a></li>
<li data-cat="mid" data-score="42"><a href="https://www.judal.co.kr/?view=stockList&themeIdx=202">반도체 기술(3D 낸드)<span>(9)</span></a></li>
<li><a href="https://www.judal.co.kr/?view=stockList&themeIdx=53">여행<span>(9)</span></a></li>
"""

_THEME_HTML = """
<th scope="row" class="table-success text-start">
    <a href="https://stock.naver.com/domestic/stock/039130/price" target="_blank" role="button" class="btn p-0 m-0 text-start noBoxLine">
        <b style='font-size:.95em'>하나투어</b><br/>
<th scope="row" class="table-success text-start">
    <a href="https://stock.naver.com/domestic/stock/048550/price" target="_blank" role="button" class="btn">
        <b style='font-size:.95em'>SM C&amp;C</b><br/>
"""


def test_parse_theme_list_reads_name_outside_span():
    themes = judal.parse_theme_list(_MAIN_HTML)
    assert sorted((t["idx"], t["name"], t["count"]) for t in themes) == [
        (53, "여행", 9), (202, "반도체 기술(3D 낸드)", 9),
    ]


def test_parse_theme_list_empty_is_failure_not_silence():
    with pytest.raises(RuntimeError):
        judal.parse_theme_list("<html>개편된 페이지</html>")


def test_parse_theme_stocks_reads_naver_stock_links():
    assert judal.parse_theme_stocks(_THEME_HTML) == [("039130", "하나투어"), ("048550", "SM C&C")]
