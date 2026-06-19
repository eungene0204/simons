"""코퍼스 검색 스모크 테스트 — bge-m3 적재→의미 쿼리→상위 매칭 일관성.

엔진 백테스트는 제외하고(합성 메트릭) 벡터 계층만 검증한다.
모델 로딩 필요 — RUN_BGE_M3_TESTS=1 로 실행.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from vector_memory import (
    ChromaVectorMemoryRepository,
    VectorMemoryService,
    normalize_backtest_result,
)
from vector_memory.embedding import BgeM3EmbeddingClient

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BGE_M3_TESTS") != "1",
    reason="bge-m3 모델 로딩 필요 — RUN_BGE_M3_TESTS=1 로 실행",
)


_DUMMY_METRICS = {"cagr": 0.1, "mdd": -0.15, "sharpe": 0.8, "win_rate": 0.5, "trade_count": 40}


def _record(dsl, summary):
    return normalize_backtest_result(strategy_dsl=dsl, metrics=_DUMMY_METRICS, strategy_summary=summary)


@pytest.mark.asyncio
async def test_semantic_query_retrieves_related_strategy():
    """'저평가 가치주' 쿼리가 RSI/모멘텀 전략보다 PBR 전략을 상위로 검색해야 한다."""
    pbr_dsl = {
        "universe": ["KOSPI200"],
        "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.0}],
        "entry_signals": [],
        "max_positions": 10,
        "rebalancing_period": "monthly",
    }
    rsi_dsl = {
        "universe": ["KOSDAQ"],
        "fundamental_filters": [],
        "entry_signals": [{"indicator": "rsi", "signal_type": "buy", "period": 14, "operator": "<", "value": 30}],
        "max_positions": 5,
    }

    with tempfile.TemporaryDirectory() as tmp:
        service = VectorMemoryService(
            repository=ChromaVectorMemoryRepository(persist_path=Path(tmp)),
            embedding_client=BgeM3EmbeddingClient(),
        )
        await service.upsert_backtest_memories([
            _record(pbr_dsl, "코스피200에서 PBR 1배 이하 저평가 가치주를 월간 리밸런싱"),
            _record(rsi_dsl, "코스닥에서 RSI 과매도 반등 단기 매수"),
        ])

        query = _record(
            {"universe": ["KOSPI200"], "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1.2}]},
            "저평가된 PBR 낮은 종목에 분산 투자하고 싶어",
        )
        matches = await service.query_similar(record=query, top_k=2)

    assert matches, "검색 결과가 비어있음"
    top = matches[0]
    assert "pbr" in top.metadata.get("indicators", ""), f"상위 매칭이 PBR 전략이 아님: {top.metadata.get('indicators')}"
    assert top.similarity_score > 0.5
