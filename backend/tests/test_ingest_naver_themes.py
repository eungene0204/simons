"""네이버 금융 업종·테마 카탈로그 수집(scripts/ingest_naver_themes) — 파서·가드 검증.

핵심 계약:
  - 수집은 네이버 금융 JSON API(2026-10-01 개편 이후) — 목록·상세 모두 페이지를 넘겨 전부 모은다.
  - 목록 파서는 no·이름만 취하고 중복 no는 1회만. 종목 파서는 6자리 코드만, 중복 1회만.
  - 목록 0개는 수집 고장으로 예외(조용한 0개 = 라이브 편입 전체가 죽은 채 잠복).
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

import json

import pytest

import engine.naver_theme_live as live


def _api(pages: dict[str, dict]):
    def fetch(url: str) -> str:
        return json.dumps(pages[url], ensure_ascii=False)
    return fetch


def _list_url(api_kind: str, page: int) -> str:
    return live.LIST_URL.format(api_kind=api_kind, page=page)


def test_fetch_group_index_pages_through_api(monkeypatch):
    monkeypatch.setattr(live, "FETCH_DELAY_S", 0)
    fetch = _api({
        _list_url("theme", 1): {"groups": [{"no": 121, "name": "남북경협"},
                                          {"no": 442, "name": "2차전지"}], "totalCount": 3},
        _list_url("theme", 2): {"groups": [{"no": 442, "name": "2차전지"},
                                          {"no": 589, "name": "LCD 부품/소재"}], "totalCount": 3},
        _list_url("industry", 1): {"groups": [{"no": 261, "name": "제약"}], "totalCount": 1},
    })
    groups = live.fetch_group_index(fetch)
    assert {(g["no"], g["name"], g["kind"]) for g in groups} == {
        (121, "남북경협", "theme"), (442, "2차전지", "theme"),
        (589, "LCD 부품/소재", "theme"), (261, "제약", "upjong"),
    }


def test_fetch_group_index_empty_is_failure(monkeypatch):
    """개편 사고(2026-10-01) 회귀 — 옛 HTML 파서가 0개를 돌려줘도 '정합 없음'으로 지나갔다."""
    monkeypatch.setattr(live, "FETCH_DELAY_S", 0)
    fetch = _api({_list_url(k, 1): {"groups": [], "totalCount": 0} for k in ("theme", "industry")})
    with pytest.raises(RuntimeError):
        live.fetch_group_index(fetch)


def test_fetch_group_pairs_pages_and_dedupes(monkeypatch):
    monkeypatch.setattr(live, "FETCH_DELAY_S", 0)
    url = live.GROUP_API_URL
    fetch = _api({
        url.format(api_kind="industry", no=261, page=1): {"stocks": [
            {"itemCode": "035420", "stockName": "NAVER"},
            {"itemCode": "035420", "stockName": "NAVER"},
        ], "totalCount": 3},
        url.format(api_kind="industry", no=261, page=2): {"stocks": [
            {"itemCode": "035720", "stockName": "카카오"},
        ], "totalCount": 3},
    })
    pairs = live.fetch_group_pairs({"no": 261, "name": "제약", "kind": "upjong"}, fetch)
    assert pairs == [("035420", "NAVER"), ("035720", "카카오")]


def test_inter_korean_themes_not_excluded():
    """'남북경협'·'대북주'·'개성공단' 제외 해제(2026-10-01 사용자 결정) — 재추가 금지."""
    assert not {"남북경협", "대북주", "개성공단"} & set(ing.EXCLUDE_EVENT)


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
