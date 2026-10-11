"""관찰 계층 조회 — 운영 콘솔 실패 분류 탭(관리자 전용 읽기 뷰).

백엔드는 외부에 노출되지 않는다(Caddy는 web만 프록시) — 관리자 확인은 이 엔드포인트를
부르는 Next 라우트(app/api/admin/trace-triage, requireAdmin)가 한다. 응답에는 Trace
원문 표본이 들어가므로 보관 정책(원문 3일)이 지난 데이터는 애초에 남아 있지 않다.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from observability.retention import RETENTION_DAYS

router = APIRouter(tags=["observability"])


@router.get("/admin/trace-triage")
async def trace_triage(days: int = Query(RETENTION_DAYS, ge=1, le=RETENTION_DAYS)) -> dict:
    """최근 N일(오늘 포함) Trace의 실패 후보 묶음 — 판정은 구조 신호만(observability/triage.py)."""
    from observability import triage

    result = await asyncio.to_thread(triage.load, None, days)
    return {**result, "tiers": list(triage.TIERS), "retention_days": RETENTION_DAYS}
