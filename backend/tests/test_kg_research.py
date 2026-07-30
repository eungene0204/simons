"""개념↔종목 관계의 근거·관련도(설계 스펙 § 8.5).

여기서 고정하는 계약:
  ① 원장이 정본이다 — 이 코드가 관계를 새로 판정하지 않는다
  ② 원장에 없는 관계에는 근거를 붙이지 않는다(지어내지 않는다)
  ③ 직접 사업 관계(Producer·Supplier)와 그 밖의 연관을 구분한다
  ④ [규제 안전] 관계 유형은 과거·현재의 사실만 — 전망성 유형은 도입하지 않는다
"""

from __future__ import annotations

import json

import pytest

from engine import kg_research


@pytest.fixture(autouse=True)
def _fresh_cache():
    kg_research._reset_for_tests()
    yield
    kg_research._reset_for_tests()


def _ledger(tmp_path, concept_id: str, stocks: list[dict]) -> None:
    (tmp_path / f"{concept_id}.json").write_text(
        json.dumps({"concept": {"id": concept_id}, "stocks": stocks}, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(kg_research, "_RESEARCH_DIR", tmp_path)
    return tmp_path


# ── 원장 읽기 ────────────────────────────────────────────────────────────────

def test_relation_is_read_from_ledger(ledger_dir):
    _ledger(ledger_dir, "solid-state-battery", [{
        "company_name": "삼성SDI", "ticker": "006400",
        "relation_type": "Producer", "relevance": "Core", "relevance_score": 90,
        "reason": "직접 개발·시제품 생산", "business_evidence": "S라인 착공",
        "verified": True, "sources": [{"url": "x"}, {"url": "y"}],
    }])
    meta = kg_research.lookup("solid-state-battery", "006400")
    assert meta["relation_type"] == "Producer"
    assert meta["relevance"] == "Core"
    assert meta["relevance_score"] == 90
    assert meta["business_evidence"] == "S라인 착공"
    assert meta["verified"] is True
    assert meta["source_count"] == 2


def test_missing_relation_returns_none_not_a_guess(ledger_dir):
    """원장에 없는 관계에는 근거를 붙이지 않는다."""
    _ledger(ledger_dir, "hbm", [])
    assert kg_research.lookup("hbm", "000660") is None
    assert kg_research.lookup("없는개념", "005930") is None


def test_broken_ledger_file_does_not_kill_the_rest(ledger_dir):
    """원장 한 건이 깨져도 나머지 관계는 살린다 — 근거 표기는 부가 정보다."""
    (ledger_dir / "broken.json").write_text("{망가진", encoding="utf-8")
    _ledger(ledger_dir, "good", [{"ticker": "000660", "relation_type": "Producer"}])
    assert kg_research.lookup("good", "000660") is not None


def test_stock_without_ticker_is_skipped(ledger_dir):
    _ledger(ledger_dir, "c", [{"company_name": "비상장사", "relation_type": "Producer"}])
    assert kg_research.relation_index() == {}


# ── 직접 관계 구분 (§ 8.5 핵심) ───────────────────────────────────────────────

@pytest.mark.parametrize("relation_type, direct", [
    ("Producer", True),        # 직접 생산
    ("Supplier", True),        # 핵심 부품·소재·장비 공급
    ("Investor", False),       # 지분 관계 — 사실이지만 직접 사업 관계는 아니다
    ("Infrastructure", False),  # 산업 인프라 — 간접
    ("Related", False),        # 그 밖의 연관
])
def test_direct_business_relation_is_separated_from_other_links(
    ledger_dir, relation_type, direct
):
    _ledger(ledger_dir, "c", [{"ticker": "000660", "relation_type": relation_type}])
    assert kg_research.lookup("c", "000660")["direct"] is direct


def test_unknown_relation_type_is_passed_through_not_dropped(ledger_dir):
    """원장이 정본이다 — 목록 밖 유형도 버리지 않고 '미지'로 표시만 한다.
    걸러내면 새 유형을 추가할 때 관계가 조용히 사라진다."""
    _ledger(ledger_dir, "c", [{"ticker": "000660", "relation_type": "NewKind"}])
    meta = kg_research.lookup("c", "000660")
    assert meta["relation_type"] == "NewKind"
    assert meta["relation_known"] is False
    assert meta["direct"] is False


def test_no_forward_looking_relation_type_is_declared():
    """[규제 안전] 설계 스펙 § 8.5의 '정책 수혜 가능성'은 미래 전망이라 도입하지 않는다 —
    근거로 표기하는 순간 객관적 데이터 표시가 아니라 전망 제공이 된다."""
    for banned in ("Policy", "Beneficiary", "Expected", "Outlook", "Forecast"):
        assert banned not in kg_research._KNOWN_RELATION_TYPES


def test_relevance_rank_orders_by_directness():
    assert kg_research.relevance_rank("Core") < kg_research.relevance_rank("Strong")
    assert kg_research.relevance_rank("Strong") < kg_research.relevance_rank("Moderate")
    # 목록 밖·없음은 가장 뒤
    assert kg_research.relevance_rank(None) > kg_research.relevance_rank("Unverified")


# ── 실제 원장 (정본 데이터 계약) ──────────────────────────────────────────────

def test_shipped_ledger_relation_types_are_all_factual():
    """정본 원장에 전망성 관계 유형이 섞여 들어오지 않았는지 상시 확인한다."""
    types = {m["relation_type"] for m in kg_research.relation_index().values()}
    assert types  # 원장이 실제로 로드됐다
    assert types <= kg_research._KNOWN_RELATION_TYPES, f"미등록 관계 유형: {types}"


# ── 그래프·유니버스까지의 배선 ────────────────────────────────────────────────

def test_relation_meta_reaches_listed_companies():
    """원장 → 시드 엣지 → listed_companies. 이 배선이 끊기면 런타임이 '직접 생산'과
    '테마 목록에 함께 있을 뿐'을 구분할 수 없다(§ 8.5가 요구하는 바로 그 구분)."""
    from engine import knowledge_graph

    companies = {
        c["symbol"]: c
        for c in knowledge_graph.get_graph().listed_companies("solid-state-battery")
    }
    samsung = companies["006400"]
    assert samsung["evidence_source"] == "research"
    assert samsung["direct"] is True
    assert samsung["relation"]["relevance"] == "Core"


def test_concept_without_ledger_degrades_without_fabricating_evidence():
    """원장이 없는 개념은 근거 없이 남는다 — 없는 근거를 만들어내지 않는다."""
    from engine import knowledge_graph

    companies = knowledge_graph.get_graph().listed_companies("hbm")
    assert companies
    for c in companies:
        assert c["relation"] is None
        assert c["direct"] is False
        # 시드 큐레이션 엣지이지 카탈로그·학습이 아니다(출처를 읽는 시점에 추론하면
        # 근거 없는 시드 엣지가 카탈로그로 잘못 표기된다).
        assert c["evidence_source"] == "seed"


def test_concept_universe_uses_structured_score_not_note_parsing():
    """원장이 있으면 note 문자열 되파싱 대신 구조화된 점수·근거를 쓴다."""
    from engine import concept_universe, knowledge_graph

    graph = knowledge_graph.get_graph()
    candidates = {
        c["symbol"]: c
        for c in concept_universe._company_candidates_of(
            graph, "solid-state-battery", "전고체 배터리"
        )
    }
    samsung = candidates["006400"]
    assert samsung["score"] == pytest.approx(0.90)
    assert samsung["relation_type"] == "Producer"
    assert samsung["direct"] is True
    assert samsung["business_evidence"]
    # 이유는 원장 문장이지 note에서 괄호를 떼어낸 것이 아니다.
    assert "Core" not in samsung["reason"]
