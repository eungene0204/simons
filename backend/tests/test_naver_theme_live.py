"""네이버 금융 라이브 조회→카탈로그 편입(engine/naver_theme_live) — KG 미스 1순위 검색.

핵심 계약(2026-07-27 사용자 지시: KG에 없으면 네이버를 항상 우선 검색해 KG에 넣는다):
  - 표기 정합은 정규화 정확 일치만(원명·괄호 제거 본체·슬래시 변형) — 부분·접두 금지.
  - 정합 시 카탈로그 파일에 병합 저장되고 그래프가 즉시 합성한다(테마→종목 조회).
  - 정본에 없는 심볼 드롭·수집 실패 = False(기존 체인 폴백). 이름 키워드 스코프
    가드(인물·정치·재해·질병)는 2026-08-29 폐지 — 되살리지 말 것.
  - term_grounding 검색 레인은 뉴스 검색 학습 전에 이 조회를 먼저 시도한다
    (search_fn 주입 시엔 건너뛴다 — 테스트·대체 검색 경로의 실네트워크 차단).
"""

from __future__ import annotations

import json

import engine.knowledge_graph as kg
import engine.naver_theme_live as ntl
import engine.term_grounding as tg


def _fake_fetch(pages: dict[str, str]):
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        return pages[url]

    fetch.calls = calls
    return fetch


def _pages(theme_name: str, no: int = 901, stocks: list[dict] | None = None) -> dict[str, str]:
    """네이버 금융 JSON API 응답(2026-10-01 개편 이후 형태)."""
    stocks = stocks if stocks is not None else [
        {"itemCode": "005930", "stockName": "삼성전자"},
        {"itemCode": "000660", "stockName": "SK하이닉스"},
        {"itemCode": "999999", "stockName": "정본없는종목"},
    ]
    return {
        ntl.LIST_URL.format(api_kind="theme", page=1): json.dumps(
            {"groups": [{"no": no, "name": theme_name}], "totalCount": 1}, ensure_ascii=False),
        ntl.LIST_URL.format(api_kind="industry", page=1): json.dumps(
            {"groups": [], "totalCount": 0}),
        ntl.GROUP_API_URL.format(api_kind="theme", no=no, page=1): json.dumps(
            {"stocks": stocks, "totalCount": len(stocks)}, ensure_ascii=False),
    }


def test_lookup_exact_match_ingests_and_graph_serves(tmp_path, monkeypatch):
    catalog = tmp_path / "kg-naver-theme-catalog.json"
    fetch = _fake_fetch(_pages("가상수집테마"))
    assert ntl.lookup_and_ingest("가상수집테마", catalog_path=catalog, fetch=fetch) is True

    data = json.loads(catalog.read_text(encoding="utf-8"))
    (theme,) = data["themes"]
    assert theme["id"] == "naver-theme-901"
    # 정본 가드 — korea-stocks.json에 없는 심볼은 드롭
    assert [s["symbol"] for s in theme["stocks"]] == ["005930", "000660"]
    assert theme["synonyms"] == []  # 원명 정확 일치 — 동의어 불필요

    # 편입 즉시 그래프가 합성해 테마→종목 조회가 결정적으로 동작한다
    monkeypatch.setattr(kg, "_NAVER_CATALOG_PATH", catalog)
    monkeypatch.setattr(kg, "_CACHED", None)
    result = kg.theme_listed_companies("가상수집테마 관련주")
    assert {c["symbol"] for c in result["companies"]} == {"005930", "000660"}
    assert result["first_known_date"] is None  # 카탈로그 분류 — 시점 편향 경고 없음
    monkeypatch.setattr(kg, "_CACHED", None)


def test_lookup_paren_variant_match_records_term_synonym(tmp_path, monkeypatch):
    """괄호 병기 원명("가상수집테마(부속)")도 본체 표기로 정합하고, 재수집 후에도
    용어가 도달 가능하도록 질의 용어를 동의어로 남긴다."""
    catalog = tmp_path / "kg-naver-theme-catalog.json"
    fetch = _fake_fetch(_pages("가상수집테마(부속)"))
    assert ntl.lookup_and_ingest("가상수집테마", catalog_path=catalog, fetch=fetch) is True
    (theme,) = json.loads(catalog.read_text(encoding="utf-8"))["themes"]
    assert theme["name"] == "가상수집테마(부속)"
    assert theme["synonyms"] == ["가상수집테마"]


def test_lookup_rejects_partial_match(tmp_path):
    # 접두·부분 일치 금지 — 복합 테마구 오확정 가드와 동일 원칙
    fetch = _fake_fetch(_pages("가상수집테마"))
    assert ntl.lookup_and_ingest("가상수집", catalog_path=tmp_path / "c.json", fetch=fetch) is False
    assert not any("/theme/" in u for u in fetch.calls)  # 상세 미접근
    # 이름 키워드 스코프 가드는 폐지됐다(2026-08-29) — 종전에 '인맥' 표기만으로 반려되던
    # 분류도 이제 표기가 정합하면 그대로 수록된다. 되살리지 말 것.
    fetch2 = _fake_fetch(_pages("가상정치인맥"))
    assert ntl.lookup_and_ingest("가상정치인맥", catalog_path=tmp_path / "c.json", fetch=fetch2) is True


def test_lookup_fetch_failure_falls_back(tmp_path):
    def broken(url: str) -> str:
        raise OSError("network down")

    assert ntl.lookup_and_ingest("가상수집테마", catalog_path=tmp_path / "c.json", fetch=broken) is False


def test_lookup_merge_replaces_same_id(tmp_path):
    catalog = tmp_path / "kg-naver-theme-catalog.json"
    catalog.write_text(json.dumps({
        "version": 1, "source": "finance.naver.com", "retrieved_at": "2026-07-27",
        "themes": [
            {"id": "naver-theme-1", "name": "기존테마", "kind": "theme", "synonyms": [],
             "stocks": [{"symbol": "005930", "name": "삼성전자"}]},
            {"id": "naver-theme-901", "name": "가상수집테마", "kind": "theme", "synonyms": [],
             "stocks": [{"symbol": "000001", "name": "옛수집분"}]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    fetch = _fake_fetch(_pages("가상수집테마"))
    assert ntl.lookup_and_ingest("가상수집테마", catalog_path=catalog, fetch=fetch) is True
    data = json.loads(catalog.read_text(encoding="utf-8"))
    by_id = {t["id"]: t for t in data["themes"]}
    assert set(by_id) == {"naver-theme-1", "naver-theme-901"}  # 기존 항목 보존
    assert [s["symbol"] for s in by_id["naver-theme-901"]["stocks"]] == ["005930", "000660"]


def test_search_step_prefers_naver_before_news_learning(tmp_path, monkeypatch):
    """검색 레인 순서 계약 — 네이버 분류 정합이 검색 그라운딩 학습보다 먼저다.
    정합 시 학습 없이 종료(None — 테마 유니버스는 그래프가 담당)하고, 정합 없음일 때만
    그라운딩 학습으로 폴백하되 수집한 분류 목록을 학습(관련 기업 엣지)과 공유한다."""
    monkeypatch.setattr(tg, "search_available", lambda: True)
    chat = lambda *a, **k: '{"term": "가상수집테마"}'  # noqa: E731
    groups = [{"no": 901, "name": "가상수집테마", "kind": "theme"}]
    # 실네트워크 가드를 흉내낸 심 — search_fn 주입 시 None(실제 함수와 같은 계약)
    monkeypatch.setattr(
        tg, "_naver_groups_for_learning",
        lambda *, search_injected: None if search_injected else groups,
    )

    calls: list[str] = []
    monkeypatch.setattr(ntl, "lookup_and_ingest", lambda term, **k: calls.append(term) or True)
    monkeypatch.setattr(tg, "_ground_and_learn", lambda *a, **k: calls.append("learn") or None)
    assert tg.resolve_sector("가상수집테마 관련주 전략", chat,
                             lexicon_path=tmp_path / "lex.json") is None
    assert calls == ["가상수집테마"]  # 네이버 정합 → 그라운딩 학습 미진입

    calls.clear()
    monkeypatch.setattr(ntl, "lookup_and_ingest", lambda term, **k: calls.append(term) or False)
    monkeypatch.setattr(
        tg, "_ground_and_learn",
        lambda *a, **k: calls.append(("learn", k.get("naver_groups") is groups))
        or {"sector": "반도체"},
    )
    assert tg.resolve_sector("가상수집테마 관련주 전략", chat,
                             lexicon_path=tmp_path / "lex.json") == "반도체"
    # 정합 없음 → 그라운딩 학습 폴백 + 분류 목록 공유(기업 엣지는 네이버 분류로)
    assert calls == ["가상수집테마", ("learn", True)]

    # search_fn 주입(테스트·대체 검색 경로) 시엔 라이브 조회를 건너뛴다
    calls.clear()
    monkeypatch.setattr(ntl, "lookup_and_ingest",
                        lambda term, **k: calls.append("naver") or True)
    monkeypatch.setattr(tg, "_ground_and_learn", lambda *a, **k: None)
    tg.resolve_sector("가상수집테마 관련주 전략", chat, search_fn=lambda t: None,
                      lexicon_path=tmp_path / "lex.json")
    assert calls == []
