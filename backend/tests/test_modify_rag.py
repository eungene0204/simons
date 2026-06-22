import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine import modify_rag
from engine.modify_rag import (
    ModifyRAG,
    build_dynamic_modify_prompt,
    record_example,
    _load_corpus,
    _category_for,
    _fallback_examples,
    _MODIFY_EXAMPLES,
)


def test_modify_rag_initialization():
    """RAG 초기화 및 코퍼스 로드 — 합성 JSON(또는 폴백 시드) 전체가 적재돼야 함"""
    rag = ModifyRAG()
    rag._init_collection()
    assert rag._collection is not None
    assert rag._collection.count() == len(_load_corpus())
    # 합성 코퍼스가 폴백 시드보다 충분히 커야 함
    assert rag._collection.count() >= len(_MODIFY_EXAMPLES)


def test_modify_rag_retrieve_take_profit():
    """익절 관련 예시 검색"""
    rag = ModifyRAG()
    examples = rag.retrieve_examples("30% 익절 설정", k=2)
    assert len(examples) > 0
    assert any(ex["category"] == "take_profit" for ex in examples)


def test_modify_rag_retrieve_stop_loss():
    """손절 관련 예시 검색"""
    rag = ModifyRAG()
    examples = rag.retrieve_examples("손절 -12%", k=2)
    assert len(examples) > 0
    assert any(ex["category"] == "stop_loss" for ex in examples)


def test_modify_rag_retrieve_universe():
    """유니버스 변경 예시 검색"""
    rag = ModifyRAG()
    examples = rag.retrieve_examples("코스닥으로 바꿔줘", k=2)
    assert len(examples) > 0
    assert any("universe" in ex["category"] for ex in examples)


def test_build_dynamic_modify_prompt_size():
    """동적 프롬프트 크기가 원본보다 작아야 함"""
    dynamic_prompt = build_dynamic_modify_prompt("30% 익절 설정", k=2)
    assert len(dynamic_prompt) < 2000
    assert "현재 전략 JSON" in dynamic_prompt
    assert "예시" in dynamic_prompt


def test_build_dynamic_modify_prompt_includes_relevant_examples():
    """동적 프롬프트가 관련 예시를 포함해야 함"""
    dynamic_prompt = build_dynamic_modify_prompt("익절 20%", k=2)
    assert "익절" in dynamic_prompt or "take_profit" in dynamic_prompt


def test_category_for_derives_from_output():
    assert _category_for({"stop_loss_pct": 10.0}) == "stop_loss"
    assert _category_for({"take_profit_pct": 30.0}) == "take_profit"
    assert _category_for({"universe": ["KOSDAQ"]}) == "universe"
    assert _category_for({"stop_loss_pct": 10.0, "max_positions": 5}) == "mixed"
    assert _category_for({}) == "misc"


class _FakeCollection:
    """bge-m3/chroma 없이 record 영속 경로만 검증하기 위한 더미."""

    def __init__(self):
        self.added = []

    def add(self, **kwargs):
        self.added.append(kwargs)

    def count(self):
        return 0


def _make_offline_rag(corpus=None):
    rag = ModifyRAG()
    rag._init_collection = lambda: None  # type: ignore
    rag._init_embedder = lambda: None  # type: ignore
    rag._collection = _FakeCollection()
    rag._corpus = list(corpus or [])
    return rag


def test_record_example_persists_simple_fields(tmp_path, monkeypatch):
    """성공한 수정 요청이 learned.jsonl에 단순 필드만 기록돼야 함"""
    learned = tmp_path / "learned.jsonl"
    monkeypatch.setenv("MODIFY_CORPUS_PATH", str(learned))

    rag = _make_offline_rag()
    # null 필드와 구조화 필드는 제외, stop_loss_pct만 기록
    ok = rag.record_example("손절 9%로 바꿔줘", {
        "stop_loss_pct": 9.0,
        "take_profit_pct": None,
        "entry_signals": [{"type": "rsi"}],
    })
    assert ok is True
    assert learned.exists()

    rows = [json.loads(line) for line in learned.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    rec = rows[0]
    assert rec["request"] == "손절 9%로 바꿔줘"
    assert rec["category"] == "stop_loss"
    assert rec["output"] == {"stop_loss_pct": 9.0}  # null/구조화 필드 제외


def test_record_example_dedup_and_empty(tmp_path, monkeypatch):
    """동일 요청 중복 기록 방지 + 단순 필드 없으면 기록 안 함"""
    learned = tmp_path / "learned.jsonl"
    monkeypatch.setenv("MODIFY_CORPUS_PATH", str(learned))

    rag = _make_offline_rag()
    assert rag.record_example("익절 25%", {"take_profit_pct": 25.0}) is True
    # 같은 요청 재기록 → dedup
    assert rag.record_example("익절 25%", {"take_profit_pct": 25.0}) is False
    # 단순 필드가 전혀 없으면 기록 안 함
    assert rag.record_example("설명만 바꿔줘", {"description": "x", "entry_signals": [1]}) is False

    rows = [l for l in learned.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1


def test_record_example_adds_to_live_collection(tmp_path, monkeypatch):
    """컬렉션이 살아있으면 라이브로 추가돼 즉시 검색 가능해야 함"""
    learned = tmp_path / "learned.jsonl"
    monkeypatch.setenv("MODIFY_CORPUS_PATH", str(learned))

    rag = _make_offline_rag()

    # 임베더가 있는 것처럼 흉내 (encode가 호출되면 라이브 add 수행)
    class _Emb:
        def encode(self, texts, normalize_embeddings=True):
            class _Arr(list):
                def tolist(self_inner):
                    return [[0.0]]
            return _Arr()

    rag._init_embedder = lambda: setattr(rag, "_embedder", _Emb())  # type: ignore
    rag._embedder = _Emb()

    assert rag.record_example("트레일링 12%", {"trailing_stop_pct": 12.0}) is True
    assert len(rag._collection.added) == 1
    assert rag._collection.added[0]["documents"] == ["트레일링 12%"]


def test_build_dynamic_modify_prompt_falls_back_without_embedder(monkeypatch):
    """RAG(bge-m3/chromadb)가 없으면 정적 예시로 폴백하고 절대 raise하지 않아야 함.

    회귀: sentence_transformers 미설치 시 _init_embedder가 RuntimeError를 던져
    수정 파싱 전체가 죽던 버그(로컬 'pip install sentence-transformers 필요').
    """
    def _boom(self, user_request, k=2):
        raise RuntimeError("pip install sentence-transformers 필요")

    monkeypatch.setattr(ModifyRAG, "retrieve_examples", _boom)

    prompt = build_dynamic_modify_prompt("30% 익절 설정", k=2)
    assert "현재 전략 JSON" in prompt
    assert "수정 요청:" in prompt  # 폴백 예시가 실제로 포함됨
    assert len(prompt) < 4000


def test_fallback_examples_cover_categories():
    """폴백 예시는 임베딩 없이 여러 카테고리를 대표해야 함"""
    examples = _fallback_examples()
    assert len(examples) >= 3
    cats = {ex.get("category") for ex in examples}
    assert "take_profit" in cats or "stop_loss" in cats


def test_module_record_example_never_raises(monkeypatch):
    """모듈 레벨 record_example은 내부 예외를 삼켜야 함(사용자 플로우 보호)"""
    def _boom():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(modify_rag, "get_modify_rag", _boom)
    assert record_example("아무거나", {"stop_loss_pct": 5.0}) is False
