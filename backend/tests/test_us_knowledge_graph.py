"""미국 지식그래프(engine/us_knowledge_graph.py) — 시드 무결성·합성·테마 해석."""

import json
from pathlib import Path

import pytest

import engine.us_knowledge_graph as uskg
from engine.universe_pit import resolve_us_theme

_ROOT = Path(__file__).resolve().parents[2]
_SEED = _ROOT / "data" / "us-knowledge-graph.json"
_CATALOG = _ROOT / "data" / "us-theme-catalog.json"
_OHLCV = _ROOT / "data" / "ohlcv-us"

needs_data = pytest.mark.skipif(not _OHLCV.exists(), reason="미국 파케이 미러 없음")


def _fresh_graph():
    uskg._CACHED = None
    uskg._CACHED_MTIMES = None
    uskg._registry_names.cache_clear()
    return uskg.get_graph()


# ── 시드 무결성 ────────────────────────────────────────────────────────────────

def test_graph_integrity_zero_issues():
    # 오타 티커·미정의 노드·미지원 엣지 타입은 로드 시 issues로 잡힌다 — 항상 0.
    assert _fresh_graph().issues == []


def test_seed_alias_no_conflict_within_and_across_layers():
    """별칭은 그래프 전체에서 단일 노드만 가리켜야 한다(비결정적 해석 방지).

    시드 안 충돌은 물론, 시드-카탈로그 교차 충돌도 금지 — 같은 표기를 두 레이어가
    다르게 정의하면 어느 쪽 구성이 답인지가 삽입 순서에 숨는다(정본은 한 곳)."""
    seed = json.loads(_SEED.read_text())
    catalog = json.loads(_CATALOG.read_text())
    seen: dict[str, str] = {}
    for node in seed["nodes"]:
        for term in [node.get("name", ""), node.get("name_en") or "", *node.get("synonyms", [])]:
            key = uskg._norm_key(term)
            if len(key) < 2:
                continue
            assert seen.setdefault(key, node["id"]) == node["id"], f"별칭 충돌: {term}"
    for theme in catalog["themes"]:
        for term in [theme.get("name", ""), theme.get("name_en") or "", *theme.get("aliases", [])]:
            key = uskg._norm_key(term)
            if len(key) < 2:
                continue
            owner = seen.setdefault(key, theme["id"])
            assert owner == theme["id"], f"시드-카탈로그 별칭 충돌: {term} ({owner})"


@needs_data
def test_seed_company_symbols_all_have_parquet():
    # 데이터 없는 티커를 조용히 제외하지 않는다 — 시드 편집 시 여기서 Fail Fast.
    seed = json.loads(_SEED.read_text())
    missing = [
        e["target"] for e in seed["edges"]
        if e["target"].startswith("company:")
        and not (_OHLCV / f"{e['target'].split(':', 1)[1]}.parquet").exists()
    ]
    assert missing == []


# ── 합성·해석 ──────────────────────────────────────────────────────────────────

def test_resolve_seed_theme_direct_company_edges():
    name, symbols = uskg.resolve_theme("스트리밍")
    assert name == "스트리밍" and "NFLX" in symbols
    # 영문 별칭도 같은 노드
    assert uskg.resolve_theme("streaming")[1] == symbols


def test_resolve_catalog_theme_via_graph():
    # 카탈로그 레이어가 그래프에 합성돼 기존 카탈로그 테마도 같은 경로로 해석된다.
    name, symbols = uskg.resolve_theme("AI 반도체")
    assert name == "AI 반도체" and "NVDA" in symbols


def test_resolve_us_prefix_and_exact_only():
    # '미국' 접두는 시장 한정어 — 벗겨서 조회한다
    assert uskg.resolve_theme("미국 금광주")[0] == "금광"
    # 정확 일치만 — 부분 문자열 매칭 금지(오폭 방지)
    assert uskg.resolve_theme("금") is None
    assert uskg.resolve_theme("없는테마") is None
    assert uskg.resolve_theme(None) is None


def test_concept_anchor_expands_to_member_theme_union():
    # ai·semiconductor·datacenter 앵커는 직접 종목 엣지 없이 소속(part_of/is_a)
    # 하위 테마 상장사의 합집합으로 전개한다(2026-08-26 사용자 결정 — 종전 '앵커=None'
    # 비확정 설계 대체: /us "AI 관련주"가 유니버스로 서야 한다).
    graph = uskg.get_graph()
    assert graph.theme_node("AI") is not None
    name, symbols = uskg.resolve_theme("AI")
    assert name == "AI"
    # AI 반도체(NVDA)·AI 소프트웨어(MSFT)·AI 서버(SMCI)가 모두 합류하고 중복은 없다
    assert {"NVDA", "MSFT", "SMCI"} <= set(symbols)
    assert len(symbols) == len(set(symbols))
    # 공급망 주변부(benefits_from·demanded_by)는 구성원이 아니다 — datacenter의
    # HVAC(CARR)는 합류하지 않는다(구리 테마는 분류 중복이라 시드에서 제거됐다,
    # 2026-08-27 축 정리 — FCX는 이제 분류 'Copper'가 담당한다)
    _, dc_symbols = uskg.resolve_theme("데이터센터")
    assert {"SMCI"} <= set(dc_symbols)
    assert not {"CARR"} & set(dc_symbols)


def test_universe_pit_delegates_to_graph():
    # 기존 진입점(resolve_us_theme)은 그래프 위임 후에도 계약이 같다
    assert resolve_us_theme("스트리밍") == uskg.resolve_theme("스트리밍")
    # 광의어 '반도체'는 앵커 소속 합집합으로 전개된다(설계 전환 2026-08-26)
    name, symbols = resolve_us_theme("반도체")
    assert name == "반도체 산업" and "NVDA" in symbols


def test_seed_wins_over_catalog_and_unknown_catalog_symbol_skipped(tmp_path, monkeypatch):
    """레이어 계약: 별칭이 겹치면 시드(큐레이션) 승, 카탈로그의 정본 밖 티커는 스킵."""
    seed = {
        "nodes": [{"id": "t1", "name": "겹침테마", "category": "theme", "synonyms": []}],
        "edges": [{"source": "t1", "type": "related_company", "target": "company:AAPL"}],
    }
    catalog = {"themes": [
        {"id": "dup", "name": "겹침테마", "aliases": [], "symbols": ["MSFT"]},
        {"id": "ghost", "name": "유령테마", "aliases": [], "symbols": ["MSFT", "ZZZZZZ"]},
    ]}
    seed_p, cat_p = tmp_path / "seed.json", tmp_path / "catalog.json"
    seed_p.write_text(json.dumps(seed, ensure_ascii=False))
    cat_p.write_text(json.dumps(catalog, ensure_ascii=False))
    monkeypatch.setattr(uskg, "_SEED_PATH", seed_p)
    monkeypatch.setattr(uskg, "_CATALOG_PATH", cat_p)
    uskg._CACHED = None
    uskg._CACHED_MTIMES = None
    try:
        graph = uskg.get_graph()
        assert graph.issues == []
        assert uskg.resolve_theme("겹침테마") == ("겹침테마", ["AAPL"])  # 시드 승
        assert uskg.resolve_theme("유령테마") == ("유령테마", ["MSFT"])  # 정본 밖 스킵
    finally:
        uskg._CACHED = None
        uskg._CACHED_MTIMES = None


def test_dump_route_market_us():
    """GET /knowledge/graph?market=us — 관리자 콘솔 KG 시각화의 미국 그래프 분기.

    카탈로그 테마가 related_company 엣지로 합성돼(한국과 동일 표현) 콘솔에서
    종목 이웃과 함께 그려질 수 있어야 한다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import intent_routes

    app = FastAPI()
    app.include_router(intent_routes.router)
    res = TestClient(app).get("/knowledge/graph", params={"market": "us"})
    assert res.status_code == 200
    data = res.json()
    assert set(data.keys()) == {"nodes", "edges", "issues"}
    node_ids = {n["id"] for n in data["nodes"]}
    assert "streaming" in node_ids            # 시드 테마
    assert "theme:ai-semiconductor" in node_ids  # 카탈로그 테마
    assert "company:NVDA" in node_ids         # 정본 자동 생성 종목 노드
    assert any(
        e["source"] == "theme:ai-semiconductor" and e["target"] == "company:NVDA"
        for e in data["edges"]
    )
    # 미국 그래프에 한국 종목은 없다 — 6자리 코드 노드가 하나라도 있으면 교차-시장 오염
    # (학습 오버레이 자체는 2026-08-26부터 미국에도 있다 — 소스가 미국 공시라 한국
    # 기계를 부르지 않는다, FR-STR-074. 종전의 'learned: 노드 금지' 단언을 대체)
    assert not any(i.startswith("company:") and i.split(":", 1)[1][:1].isdigit()
                   for i in node_ids)
    # GICS 업종 레이어는 있다(전 종목 등재 — 콘솔 탐색용)
    assert "sector:Health Care" in node_ids


def test_gics_layer_full_membership():
    """GICS 레이어 — 분류가 있는 전 종목이 소속 엣지로 그래프에 들어온다.

    산업이 두 섹터에 걸치면(Consumer Electronics 실측) 소속 엣지를 모두 남기고,
    분류 결측 종목만 테마 참조 시에 등재된다."""
    graph = _fresh_graph()
    sectors = [n for n in graph.nodes if n.startswith("sector:")]
    industries = [n for n in graph.nodes if n.startswith("industry:")]
    companies = [n for n in graph.nodes if n.startswith("company:")]
    assert len(sectors) == 11  # GICS 정본 11종
    assert len(industries) > 200
    # 분류 결측(실측 98)을 빼면 registry 전 종목이 들어온다
    registry_stocks = json.loads((_ROOT / "data" / "us-stocks.json").read_text())
    classified = [s for s in registry_stocks if (s.get("sector") or "").strip()]
    assert len(companies) >= len(classified)
    # 소속 사슬: 회사 -belongs_to-> 산업 -part_of-> 섹터 (Agilent 실측)
    assert any(
        e["source"] == "company:A" and e["type"] == "belongs_to"
        and e["target"] == "industry:Life Sciences Tools & Services"
        for e in graph.edges
    )
    assert any(
        e["source"] == "industry:Life Sciences Tools & Services"
        and e["type"] == "part_of" and e["target"] == "sector:Health Care"
        for e in graph.edges
    )


def test_gics_terms_do_not_resolve_as_themes():
    """GICS 레이어는 테마 해석에 불참 — 업종 필터는 백테스트 미지원이라, 업종명이
    테마어로 조용히 유니버스가 되면 미지원 안내 계약이 깨진다."""
    assert uskg.resolve_theme("헬스케어") is None
    assert uskg.resolve_theme("Health Care") is None
    assert uskg.resolve_theme("Aluminum") is None


def test_seed_typo_ticker_fails_fast(tmp_path, monkeypatch):
    # 시드의 오타 티커는 카탈로그와 달리 조용히 스킵하지 않는다 — issues로 보고
    seed = {
        "nodes": [{"id": "t1", "name": "테마", "category": "theme", "synonyms": []}],
        "edges": [{"source": "t1", "type": "related_company", "target": "company:ZZZZZZ"}],
    }
    seed_p = tmp_path / "seed.json"
    seed_p.write_text(json.dumps(seed, ensure_ascii=False))
    monkeypatch.setattr(uskg, "_SEED_PATH", seed_p)
    uskg._CACHED = None
    uskg._CACHED_MTIMES = None
    try:
        assert any("ZZZZZZ" in i for i in uskg.get_graph().issues)
    finally:
        uskg._CACHED = None
        uskg._CACHED_MTIMES = None


@pytest.mark.parametrize("term,expected", [
    # 영어 시장 접두·범주 접미는 테마 정체성이 아니다 — 벗겨서 정확 일치(2026-08-26,
    # /us 영어 게이트: "US cloud software stocks"·"crypto-related"가 소실되던 실측).
    ("US cloud software stocks", "클라우드 소프트웨어"),
    ("U.S. cloud software", "클라우드 소프트웨어"),
    ("crypto-related stocks", "크립토 관련주"),
    ("US crypto-linked stocks", "크립토 관련주"),
    ("US AI semiconductor names", "AI 반도체"),
    ("American big tech", "빅테크"),
    # 앵커 별칭 — 광의어도 소속 합집합으로 전개(설계 전환 2026-08-26)
    ("semiconductor", "반도체 산업"),
    ("AI-related stocks", "AI"),
    # 벗긴 뒤에도 정확 일치만 — 부분 매칭 금지 계약 유지.
    ("used cars", None),
])
def test_resolve_theme_strips_english_qualifiers(term, expected):
    from engine.us_knowledge_graph import resolve_theme

    got = resolve_theme(term)
    assert (got[0] if got else None) == expected


# ── 회사 앵커 대표 테마(2026-08-29) ──────────────────────────────────────────

@needs_data
def test_representative_theme_prefers_gics_cohesion_not_smallest():
    """대표 테마는 **앵커와 같은 GICS 산업을 공유하는 비율**로 고른다.

    [회귀] 구성 수가 가장 적은 테마를 고르면 NVDA가 '휴머노이드 로봇'(6종)으로
    빠져 AVGO·MRVL을 놓친다 — 'AI 반도체'(8종)가 더 크지만 응집도가 높다.
    """
    graph = _fresh_graph()
    node_id = graph.representative_theme("NVDA")
    assert node_id is not None
    peers = graph.companies(node_id)
    assert {"AVGO", "MRVL", "TSM", "MU"} <= set(peers)
    assert "ISRG" not in peers  # 휴머노이드 로봇 쪽이 아니다


@needs_data
def test_representative_theme_is_none_below_cohesion_floor():
    """동료 테마가 없는 앵커엔 아무것도 얹지 않는다.

    AAPL은 최고 응집도가 0.03('AI 빅데이터' 30종)이다. 하한이 없으면
    '애플 관련주'가 30종으로 번진다.
    """
    graph = _fresh_graph()
    assert graph.representative_theme("AAPL") is None


@needs_data
def test_representative_theme_ignores_gics_and_anchor_layers():
    """후보는 테마 노드뿐 — GICS 산업/섹터·회사 앵커(related:)는 대표 테마가 아니다."""
    graph = _fresh_graph()
    node_id = graph.representative_theme("NVDA")
    assert node_id is not None
    assert not node_id.startswith(("sector:", "industry:", "related:", "company:", "etf:"))
