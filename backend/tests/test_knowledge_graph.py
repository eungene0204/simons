"""지식그래프(engine/knowledge_graph) — 시드 무결성·개념 인식·섹터 해석·확장 검증(FR-STR-070).

핵심 계약:
  - 시드의 모든 엣지 끝점은 정본(CANONICAL_SECTORS·korea-stocks·etf-master)에서 검증된다
    (오타 심볼·미지원 엣지 타입 = 무결성 테스트 실패).
  - 문장 스캔은 normalize_sector가 이미 해석하는 용어를 취급하지 않는다(이중 매칭 방지).
  - 섹터 해석은 소속 엣지(is_a/part_of/belongs_to)만 따르며, 다업종 테마·복수 개념
    충돌은 None(기존 되묻기/LLM 폴백 유지).
  - term_grounding 체인에서 시드 개념은 LLM·검색 없이 ①b에서 해석된다.
"""

from __future__ import annotations

import json

import pytest

import engine.knowledge_graph as kg
from engine.knowledge_graph import get_graph, related_universe, resolve_sector_from_text


def test_seed_integrity_no_issues():
    graph = get_graph()
    assert graph.issues == []


def test_scan_terms_unique_and_exclude_sector_vocabulary():
    from engine.universe_pit import normalize_sector

    graph = get_graph()
    index = graph._scan_index
    # 같은 용어가 서로 다른 노드를 가리키면 인식이 비결정적이 된다
    seen: dict[str, str] = {}
    for key, node_id in index:
        assert seen.setdefault(key, node_id) == node_id, f"중복 스캔 용어: {key}"
    # normalize_sector가 이미 해석하는 용어(AI·인공지능·원자력 등)는 스캔에서 제외된다
    for key, _ in index:
        assert normalize_sector(key) is None, f"섹터 어휘와 충돌하는 스캔 용어: {key}"


def test_find_concepts_latin_boundary():
    graph = get_graph()
    # 라틴 문자 연속 내부의 부분 일치는 히트가 아니다('progress'의 'ess' 등)
    assert graph.find_concepts("progress 개선 전략") == []
    assert any(n["id"] == "hbm" for n in graph.find_concepts("HBM 관련주 전략"))
    assert any(n["id"] == "hbm" for n in graph.find_concepts("hbm3e 물량 확대"))  # 별칭
    assert any(n["id"] == "smr" for n in graph.find_concepts("소형모듈원자로 테마"))


def test_resolve_sector_from_text():
    assert resolve_sector_from_text("HBM 관련주로 전략 만들어줘") == "반도체"
    assert resolve_sector_from_text("SMR 관련 투자") == "에너지/원자력"  # is_a 원자력 경유 2단계
    assert resolve_sector_from_text("휴머노이드 로봇 기업에 투자") == "로봇"
    assert resolve_sector_from_text("변압기 만드는 회사들") == "에너지/원자력"
    assert resolve_sector_from_text("생성형 AI 전략") == "소프트웨어/플랫폼"
    # 다업종 테마(데이터센터)는 의도적으로 소속 엣지가 없다 → None(되묻기/LLM 폴백)
    assert resolve_sector_from_text("데이터센터 관련주") is None
    # 서로 다른 섹터의 개념이 함께 오면 모호 → None
    assert resolve_sector_from_text("HBM이랑 SMR 둘 다") is None
    # 개념 없음 → None
    assert resolve_sector_from_text("PER 10 이하 저평가 종목") is None


def test_related_universe_expands_hbm():
    result = related_universe("HBM 관련주")
    assert result is not None
    assert result["concept"]["id"] == "hbm"
    symbols = {c["symbol"] for c in result["companies"]}
    assert {"000660", "005930", "042700"} <= symbols          # 생산·공급 기업
    assert "반도체" in {s["name"] for s in result["sectors"]}
    assert "091160" in {e["symbol"] for e in result["etfs"]}  # KODEX 반도체
    assert any(n["id"] == "gpu" for n in result["concepts"])  # 2단계 관계 탐색
    # 각 항목은 관계 근거(via) 경로를 가진다 — 객관적 관계 표시용
    assert all("→" in c["via"] or "–" in c["via"] for c in result["companies"])


def test_learned_lexicon_overlay(tmp_path, monkeypatch):
    lexicon = tmp_path / "term_lexicon.json"
    lexicon.write_text(json.dumps({
        "폐배터리": {"term": "폐배터리", "definition": "배터리 재활용", "sector": "이차전지"},
        "매핑불가어": {"term": "매핑불가어", "definition": None, "sector": None},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    graph = get_graph()
    node = graph.nodes.get("learned:폐배터리")
    assert node is not None and node["category"] == "learned"
    assert graph.resolve_sector("learned:폐배터리") == "이차전지"
    # 섹터 없는 학습 항목(매핑 불가)은 노드로 편입하지 않는다
    assert "learned:매핑불가어" not in graph.nodes

    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_graph_step_short_circuits_llm_and_search(tmp_path):
    """term_grounding 체인 ①b — 시드 개념은 LLM·검색 없이 그래프가 해석한다."""
    from engine.term_grounding import resolve_sector

    base_calls: list[str] = []

    def base_resolver(text: str):
        base_calls.append(text)
        return None

    def failing_chat(*args, **kwargs):
        raise AssertionError("시드 개념은 LLM에 도달하면 안 된다")

    search_calls: list[str] = []

    def search(term: str):
        search_calls.append(term)
        return []

    got = resolve_sector("SMR 관련 종목으로 전략 짜줘", failing_chat,
                         base_resolver=base_resolver, search_fn=search,
                         lexicon_path=tmp_path / "lex.json")
    assert got == "에너지/원자력"
    assert base_calls == [] and search_calls == []


def test_learned_edges_only_verified_composed(tmp_path, monkeypatch):
    """학습 관계 엣지(FR-STR-070b) — verified만 그래프에 합성되고 pending/rejected는
    제외된다. 섹터 매핑 없이 verified 엣지만 있는 용어도 노드로 편입된다."""
    lexicon = tmp_path / "term_lexicon.json"
    lexicon.write_text(json.dumps({
        "폐배터리": {"term": "폐배터리", "definition": "배터리 재활용", "sector": "이차전지",
                  "edges": [
                      {"type": "related_to", "target": "battery-cathode",
                       "status": "verified", "support": 2},
                      {"type": "uses", "target": "lithium", "status": "pending", "support": 1},
                      {"type": "related_to", "target": "hbm", "status": "rejected", "support": 2},
                  ]},
        "무섹터어": {"term": "무섹터어", "definition": "정의", "sector": None,
                  "edges": [{"type": "related_to", "target": "hbm",
                             "status": "verified", "support": 2}]},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    graph = get_graph()
    out = {(e["type"], e["target"]) for e in graph._out.get("learned:폐배터리", [])}
    assert ("related_to", "battery-cathode") in out
    assert ("uses", "lithium") not in out          # pending 미합성
    assert ("related_to", "hbm") not in out        # rejected 미합성
    assert "learned:무섹터어" in graph.nodes        # 섹터 없어도 verified 엣지로 편입

    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_learned_company_edges_create_canonical_nodes(tmp_path, monkeypatch):
    """학습된 related_company 엣지(FR-STR-071)의 company: 타깃은 정본 노드로 자동 생성된다.

    verified만 합성(pending 제외), 정본에 없는 심볼은 issues 없이 조용히 건너뛴다."""
    import engine.knowledge_graph as kg

    lexicon = tmp_path / "lex.json"
    lexicon.write_text(json.dumps({
        "위고비": {"term": "위고비", "sector": "바이오/제약", "edges": [
            {"type": "related_company", "target": "company:005930",
             "target_name": "삼성전자", "support": 2, "status": "verified"},
            {"type": "related_company", "target": "company:035720",
             "target_name": "카카오", "support": 1, "status": "pending"},
            {"type": "related_company", "target": "company:999999",
             "target_name": "없는회사", "support": 2, "status": "verified"},
        ]}
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    graph = kg.get_graph()
    assert "company:005930" in graph.nodes
    assert graph.nodes["company:005930"]["name"] == "삼성전자"
    assert any(
        e["source"] == "learned:위고비" and e["target"] == "company:005930"
        for e in graph.edges
    )
    # pending은 미합성, 정본에 없는 심볼은 엣지·issue 모두 없이 스킵
    assert not any(e["source"] == "learned:위고비" and e["target"] == "company:035720"
                   for e in graph.edges)
    assert not any(e["source"] == "learned:위고비" and e["target"] == "company:999999"
                   for e in graph.edges)
    assert not any("999999" in issue for issue in graph.issues)
    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_scan_index_includes_learned_terms_seed_wins_on_collision(tmp_path, monkeypatch):
    """읽기 경로 통합(2026-07-25) — 학습 용어도 그래프 스캔 인덱스에 포함돼 find_concepts·
    resolve_sector_from_text가 어휘집 별도 스캔 없이 해석한다. 같은 용어가 시드에도 있으면
    시드가 이긴다(큐레이션 우선 — 비결정적 인식 방지)."""
    lexicon = tmp_path / "term_lexicon.json"
    lexicon.write_text(json.dumps({
        "마운자로": {"term": "마운자로", "definition": "당뇨·비만 치료제",
                  "sector": "바이오/제약", "searched_at": "2026-07-25T00:00:00+00:00"},
        "hbm": {"term": "HBM", "definition": "학습이 시드와 겹친 경우",
                "sector": "이차전지"},  # 시드 hbm(반도체)과 충돌 — 시드가 이겨야 한다
        "매핑불가어": {"term": "매핑불가어", "definition": None, "sector": None},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(kg, "_LEXICON_PATH", lexicon)
    monkeypatch.setattr(kg, "_CACHED", None)

    graph = get_graph()
    # 학습 용어가 스캔으로 인식되고 belongs_to로 섹터 해석까지 단일 경로로 통한다
    assert any(n["id"] == "learned:마운자로" for n in graph.find_concepts("마운자로 관련주 전략"))
    assert resolve_sector_from_text("마운자로 관련주 전략") == "바이오/제약"
    # 시드와 겹치는 용어는 시드 노드가 인식된다(학습 노드로 갈라지지 않음)
    hits = graph.find_concepts("HBM 관련주")
    assert any(n["id"] == "hbm" for n in hits)
    assert not any(n["id"] == "learned:hbm" for n in hits)
    # 매핑 불가 항목은 노드가 아니므로 스캔에도 없다(부정 캐시는 어휘집 원장 담당)
    assert graph.find_concepts("매핑불가어 관련") == []

    monkeypatch.setattr(kg, "_CACHED", None)  # 다음 테스트가 원본 경로로 재로드하도록


def test_graph_dump_route_returns_full_graph():
    """GET /knowledge/graph(FR-STR-070c) — 관리자 콘솔 KG 시각화가 쓰는 합성 그래프
    전체 덤프. nodes/edges/issues 구조와 정본 자동 생성 노드 포함 여부를 검증한다."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import intent_routes

    app = FastAPI()
    app.include_router(intent_routes.router)
    res = TestClient(app).get("/knowledge/graph")
    assert res.status_code == 200
    data = res.json()
    assert set(data.keys()) == {"nodes", "edges", "issues"}

    graph = get_graph()
    assert len(data["nodes"]) == len(graph.nodes)
    assert len(data["edges"]) == len(graph.edges)
    node_ids = {n["id"] for n in data["nodes"]}
    # 시드 개념 + 정본 자동 생성(섹터·기업) 노드가 모두 포함된다
    assert "hbm" in node_ids
    assert any(i.startswith("sector:") for i in node_ids)
    assert any(i.startswith("company:") for i in node_ids)
