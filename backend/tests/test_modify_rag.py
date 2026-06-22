import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from engine.modify_rag import ModifyRAG, build_dynamic_modify_prompt, _MODIFY_EXAMPLES


def test_modify_rag_initialization():
    """RAG 초기화 및 코퍼스 로드 테스트"""
    rag = ModifyRAG()
    rag._init_collection()
    assert rag._collection is not None
    assert rag._collection.count() == len(_MODIFY_EXAMPLES)


def test_modify_rag_retrieve_take_profit():
    """익절 관련 예시 검색"""
    rag = ModifyRAG()
    examples = rag.retrieve_examples("30% 익절 설정", k=2)
    assert len(examples) > 0
    # 익절 카테고리 예시가 포함되어야 함
    assert any(ex["category"] == "take_profit" for ex in examples)


def test_modify_rag_retrieve_stop_loss():
    """손절 관련 예시 검색"""
    rag = ModifyRAG()
    examples = rag.retrieve_examples("손절 -12%", k=2)
    assert len(examples) > 0
    # 손절 카테고리 예시가 포함되어야 함
    assert any(ex["category"] == "stop_loss" for ex in examples)


def test_modify_rag_retrieve_universe():
    """유니버스 변경 예시 검색"""
    rag = ModifyRAG()
    examples = rag.retrieve_examples("코스닥으로 바꿔줘", k=2)
    assert len(examples) > 0
    assert any("universe" in ex["category"] for ex in examples)


def test_build_dynamic_modify_prompt_size():
    """동적 프롬프트 크기가 원본보다 작아야 함"""
    user_request = "30% 익절 설정"
    dynamic_prompt = build_dynamic_modify_prompt(user_request, k=2)

    # 시스템 지시(공통) + 2개 예시 정도로 구성되어야 함
    assert len(dynamic_prompt) < 2000  # 원본 ~4KB의 50% 이하
    assert "현재 전략 JSON" in dynamic_prompt
    assert "예시" in dynamic_prompt


def test_build_dynamic_modify_prompt_includes_relevant_examples():
    """동적 프롬프트가 관련 예시를 포함해야 함"""
    user_request = "익절 20%"
    dynamic_prompt = build_dynamic_modify_prompt(user_request, k=2)

    # 익절 관련 예시가 포함되어야 함
    assert "익절" in dynamic_prompt or "take_profit" in dynamic_prompt
