"""전략 그래프용 공개 지표 메타데이터 라우트 — 읽기 전용, 사용자 데이터 없음."""
import asyncio

from fastapi import APIRouter

router = APIRouter()


@router.get("/strategy/graph-meta")
async def strategy_graph_meta() -> dict:
    """지표 이름·단위·지원 상태·파라미터 범위·분류·개념 관계의 공개 부분만 돌려준다.

    관리자 덤프(`/ontology/graph`)와 달리 issues·내부 메모·기본값은 싣지 않는다.
    """
    from strategy_conversation.registry.public_metadata import build_public_metadata

    return await asyncio.to_thread(build_public_metadata)
