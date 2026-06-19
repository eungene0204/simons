"""bge-m3 임베딩 클라이언트 테스트.

모델(~2.3GB) 로딩이 필요하므로 기본 CI 서브셋에서는 건너뛴다.
로컬 검증: RUN_BGE_M3_TESTS=1 pytest tests/test_bge_m3_embedding.py
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from vector_memory.embedding import BGE_M3_DIMENSION, BgeM3EmbeddingClient

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BGE_M3_TESTS") != "1",
    reason="bge-m3 모델 로딩 필요 — RUN_BGE_M3_TESTS=1 로 실행",
)


@pytest.fixture(scope="module")
def client():
    return BgeM3EmbeddingClient()


@pytest.mark.asyncio
async def test_embedding_dimension_and_normalized(client):
    vector = await client.embed_text("코스피200에서 PBR 1배 이하 저평가 종목 매수")
    assert len(vector) == BGE_M3_DIMENSION
    norm = sum(value * value for value in vector) ** 0.5
    assert abs(norm - 1.0) < 1e-3  # L2 정규화(코사인 검색용)


@pytest.mark.asyncio
async def test_semantic_similarity_orders_correctly(client):
    texts = [
        "PBR이 낮은 저평가 가치주",
        "저PBR 종목에 투자",
        "RSI 과매도 반등 매수",
        "오늘 날씨 어때",
    ]
    embeddings = await client.embed_batch(texts)

    def cos(i: int, j: int) -> float:
        return sum(a * b for a, b in zip(embeddings[i], embeddings[j]))

    # 의미 동의 쌍이 무관 쌍보다 분명히 가까워야 한다.
    assert cos(0, 1) > cos(0, 2)
    assert cos(0, 2) > cos(0, 3)
    assert cos(0, 1) > 0.7


@pytest.mark.asyncio
async def test_empty_batch_returns_empty(client):
    assert await client.embed_batch([]) == []
