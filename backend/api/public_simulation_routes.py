"""공개 전략 시뮬레이션 내부 엔드포인트(docs/development/strategy-simulation.md §4.1).

Next 서버(공개 조건·캐시·요청 제한을 이미 처리한 뒤)만 부르는 경로라 `/internal/` 접두사로 내부 토큰 잠금
(internal_auth)을 그대로 받는다. 스냅샷은 Next가 DB에서 읽어 넣은 값이며 브라우저 입력이 아니다.
실행은 기존 `backtest_executor.run` + 워치독을 재사용하고, 이 모듈은 창 계산·검증·축약만 맡는다.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from engine.watchdog import BacktestTimeoutError
from public_simulation.params import OverrideError, apply_overrides, build_editable_params
from public_simulation.summary import SimulationResultError, build_public_result, check_executable
from public_simulation.window import SimulationWindow, WindowError, compute_window

logger = logging.getLogger("public_simulation")
router = APIRouter(prefix="/internal/public-simulation")

_slots = threading.BoundedSemaphore(max(1, int(os.environ.get("PUBLIC_SIMULATION_MAX_CONCURRENCY", "1"))))


def _timeout_s() -> float:
    return float(os.environ.get("PUBLIC_SIMULATION_TIMEOUT_S", "180"))


class DescribeRequest(BaseModel):
    snapshot: Dict[str, Any]


class RunRequest(BaseModel):
    snapshot: Dict[str, Any]
    overrides: Optional[List[Dict[str, Any]]] = None


def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"code": code, "message": message, **extra}, status_code=status)


# ── 테스트에서 교체하는 경계(데이터·엔진·이름 조회) ─────────────────────────────

def _data_as_of() -> date:
    import main as _main
    from engine.market_index import load_index_frame

    frame = load_index_frame("KOSPI", _main.engine.loader.data_dir)
    if frame is None or frame.height == 0:
        raise WindowError("NO_INDEX_DATA", "데이터 기준일을 확인할 수 없습니다.")
    return frame["date"].max().date()


class SimulationBusy(Exception):
    """공개 실행 동시 한도에 닿음 — 대기열 없이 바로 돌려보낸다."""


def _execute(req: Dict[str, Any]) -> Dict[str, Any]:
    """박스 칸이 차면 기존 실행기가 정한 곳(설정에 따라 Modal)으로 넘긴다 — 이 모듈은 그 정책을 바꾸지 않는다.
    슬롯은 워치독이 실행을 버린 뒤에도 실제 계산이 끝날 때(또는 시작하지 못했을 때) 한 번만 풀린다."""
    import main as _main
    import backtest_executor
    from engine.watchdog import run_with_timeout

    if not _slots.acquire(blocking=False):
        raise SimulationBusy()
    release_lock, released = threading.Lock(), []

    def release_once() -> None:
        with release_lock:
            if not released:
                released.append(True)
                _slots.release()

    def work() -> Dict[str, Any]:
        try:
            return backtest_executor.run(_main.engine, req)
        finally:
            release_once()

    try:
        return run_with_timeout(work, _timeout_s())
    except BaseException:
        from engine.watchdog import BacktestTimeoutError

        # 타임아웃이면 버려진 워커가 끝날 때 스스로 풀린다. 그 밖의 실패는 워커가 이미 풀었거나 시작도 못 한 경우다.
        if not isinstance(sys.exc_info()[1], BacktestTimeoutError):
            release_once()
        raise


def _name_lookup(symbol: str) -> Optional[str]:
    try:
        from stock_analysis.symbol_resolver import resolve_by_symbol

        ref = resolve_by_symbol(symbol)
        return ref.name if ref else None
    except Exception:  # noqa: BLE001 — 이름은 표시용, 실패하면 종목코드로 대체한다
        return None


# ── 공통 준비 ───────────────────────────────────────────────────────────────

def _validated_request(snapshot: Dict[str, Any]) -> tuple:
    """(엔진 요청 dict, None) 또는 (None, 실행 불가 사유 dict)."""
    problem = check_executable(snapshot)
    if problem:
        return None, problem
    from schemas import BacktestRequest

    try:
        return BacktestRequest(**snapshot).model_dump(), None
    except (ValidationError, TypeError) as exc:
        return None, {"reason": "INVALID_SNAPSHOT", "detail": [str(exc)[:200]]}


def _window() -> SimulationWindow:
    return compute_window(datetime.now(timezone.utc), _data_as_of())


@router.get("/baseline")
def baseline() -> Any:
    from engine.version import ENGINE_VERSION

    try:
        return {**_window().to_dict(), "engineVersion": ENGINE_VERSION}
    except WindowError as exc:
        return _error(503, exc.code, str(exc))


@router.post("/describe")
def describe(body: DescribeRequest) -> Any:
    _, problem = _validated_request(body.snapshot)
    if problem:
        return {"status": "unavailable", **problem, "editableParams": []}
    return {"status": "executable", "editableParams": build_editable_params(body.snapshot)}


@router.post("/run")
def run(body: RunRequest) -> Any:
    req, problem = _validated_request(body.snapshot)
    if problem:
        return {"status": "unavailable", **problem}
    try:
        modified, changed = apply_overrides(body.snapshot, body.overrides or [])
    except OverrideError as exc:
        return _error(400, "INVALID_PARAMETER", "입력값을 확인해 주세요.", errors=exc.errors)
    try:
        window = _window()
    except WindowError as exc:
        return _error(503, exc.code, str(exc))

    if changed:
        req, problem = _validated_request(modified)
        if problem:  # 덮어쓴 값이 스키마를 깨는 경우는 범위 검증이 막지만, 방어로 한 번 더 확인한다
            return _error(400, "INVALID_PARAMETER", "입력값을 확인해 주세요.")
    req = {**req, "startDate": window.requested_start, "endDate": window.end_date}

    try:
        result = _execute(req)
    except SimulationBusy:
        return _error(429, "BUSY", "다른 시뮬레이션을 계산 중입니다. 잠시 뒤 다시 시도해 주세요.", retryAfterSeconds=30)
    except BacktestTimeoutError:
        return _error(504, "TIMEOUT", "계산 시간이 제한을 넘었습니다. 잠시 뒤 다시 시도해 주세요.")
    except Exception:  # noqa: BLE001
        logger.exception("public simulation engine failure")
        return _error(500, "ENGINE_ERROR", "계산에 실패했습니다. 잠시 뒤 다시 시도해 주세요.")

    try:
        public = build_public_result(result, modified, window, name_lookup=_name_lookup)
    except (SimulationResultError, WindowError) as exc:
        logger.error("public simulation result rejected: %s %s", exc.code, exc)
        return _error(500, exc.code, "계산 결과를 확인하지 못해 표시하지 않습니다.")
    return {
        **public,
        "dataAsOf": window.data_as_of,
        "appliedOverrides": changed,
        "editableParams": build_editable_params(body.snapshot),
    }
