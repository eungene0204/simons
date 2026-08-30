"""네이버 금융 업종·테마 카탈로그 수집(scripts/ingest_naver_themes) — 파서·가드 검증.

핵심 계약:
  - 목록 파서는 상세 링크(no)와 이름만 취하고 중복 no는 1회만.
  - 종목 파서는 텍스트 있는 종목 링크만(차트 링크 자연 제외), 중복 코드 1회만.
  - 스코프 제외는 명시 목록(EXCLUDE_PERSON·EXCLUDE_EVENT·EXCLUDE_MARKET)만 쓴다 —
    이름 키워드 가드(인물·정치·재해·질병)는 2026-08-29 폐지.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ingest_naver_themes.py"
spec = importlib.util.spec_from_file_location("ingest_naver_themes", _SCRIPT)
ing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ing)

_THEME_LIST_HTML = """
<td class="col_type1"><a href="/sise/sise_group_detail.naver?type=theme&no=442">2차전지</a></td>
<td class="col_type1"><a href="/sise/sise_group_detail.naver?type=theme&no=589">LCD 부품/소재</a></td>
<td class="col_type1"><a href="/sise/sise_group_detail.naver?type=theme&no=442">2차전지</a></td>
<a href="/sise/theme.naver?&amp;page=6">6</a>
<a href="/sise/theme.naver?&amp;page=7">7</a>
"""

_DETAIL_HTML = """
<td class="name"><div class="name_area"><a href="/item/main.naver?code=035420">NAVER</a></div></td>
<td><a href="/item/main.naver?code=035420"><img src="chart.png"></a></td>
<td class="name"><div class="name_area"><a href="/item/main.naver?code=035720">카카오</a></div></td>
"""


def test_parse_group_list_dedupes_and_extracts():
    groups = ing.parse_group_list(_THEME_LIST_HTML, "theme")
    assert {(g["no"], g["name"]) for g in groups} == {(442, "2차전지"), (589, "LCD 부품/소재")}


def test_parse_theme_page_count():
    assert ing.parse_theme_page_count(_THEME_LIST_HTML) == 7
    assert ing.parse_theme_page_count("<html></html>") == 1


def test_parse_group_stocks_skips_chart_links():
    assert ing.parse_group_stocks(_DETAIL_HTML) == [("035420", "NAVER"), ("035720", "카카오")]


def test_scope_keyword_guard_is_abolished():
    """인물·이벤트 스코프 키워드 가드 폐지(2026-08-29 사용자 결정) — 되살리지 말 것.

    이 가드는 네이버 346개 분류 중 8개(코로나19 4종·황사/미세먼지·재난/안전·태풍 및 장마·
    스포츠행사 수혜)만 막았고 그중 일곱은 실제 사업 실체가 있는 테마였다(마스크·공기청정기·
    소방·진단기기). 도입 커밋(ff8e1114)에 근거가 기록돼 있지 않았다. 편입 여부는 분류 이름의
    키워드가 아니라 근거로 판단한다.

    이름 기반 스코프 제외는 명시 목록(EXCLUDE_PERSON·EXCLUDE_EVENT·EXCLUDE_MARKET)만 남는다."""
    assert not hasattr(ing, "EXCLUDE_NAME_PATTERNS")
    import engine.naver_theme_live as live
    assert not hasattr(live, "EXCLUDE_NAME_PATTERNS")
