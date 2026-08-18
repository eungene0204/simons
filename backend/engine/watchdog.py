"""백테스트 무한루프/행(hang) 방어 워치독.

엔진이 어떤 이유로든(예: AI 추론 데드락, 비정상 입력) 끝나지 않으면 요청이 영원히
매달리고 SSE 스트림은 상태 메시지만 무한히 내보낸다. 워커를 데몬 스레드로 돌리고
벽시계 제한 시간(BACKTEST_TIMEOUT_S, 기본 600초)을 넘기면 사용자에게 명확한 에러를
돌려준다. 스레드는 강제 종료할 수 없으므로 진짜 데드락이면 워커가 남지만(로그로 경고),
사용자 요청은 반드시 끝난다는 것이 이 모듈의 계약이다.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Callable


def backtest_timeout_s() -> float:
    return float(os.environ.get("BACKTEST_TIMEOUT_S", "600"))


def walk_forward_timeout_s() -> float:
    # 워크포워드는 창(window)마다 IS 최적화(수십 회 백테스트)를 반복하므로
    # 단일 백테스트 제한(600초)으로는 정상 실행도 대부분 잘린다.
    return float(os.environ.get("WALK_FORWARD_TIMEOUT_S", "3600"))


def walk_forward_timeout_message(timeout_s: float) -> str:
    return (
        f"워크포워드 분석이 제한 시간({int(timeout_s)}초)을 초과해 중단되었습니다. "
        "구간 수·시도 횟수를 줄이거나 기간을 짧게 해서 다시 실행해 주세요."
    )


def rebalance_comparison_timeout_s() -> float:
    # 리밸런싱 기간별 비교는 같은 전략을 6주기로 재실행(백테스트 6회) + LLM 서술 1회다.
    return float(os.environ.get("REBALANCE_COMPARISON_TIMEOUT_S", "3600"))


def rebalance_comparison_timeout_message(timeout_s: float) -> str:
    return (
        f"리밸런싱 기간별 비교가 제한 시간({int(timeout_s)}초)을 초과해 중단되었습니다. "
        "종목 범위나 기간을 줄여서 다시 실행해 주세요."
    )


class BacktestTimeoutError(Exception):
    pass


def timeout_message(timeout_s: float) -> str:
    return (
        f"백테스트가 제한 시간({int(timeout_s)}초)을 초과해 중단되었습니다. "
        "조건을 줄이거나 기간을 짧게 해서 다시 실행해 주세요."
    )


def run_with_timeout(fn: Callable[[], Any], timeout_s: float | None = None) -> Any:
    """fn()을 데몬 스레드에서 실행하고 timeout_s 안에 못 끝내면 BacktestTimeoutError.

    fn이 던진 예외는 그대로 재전파한다. 타임아웃 시 워커 스레드는 버려진다(데몬이라
    프로세스 종료를 막지 않음).
    """
    budget = backtest_timeout_s() if timeout_s is None else timeout_s
    holder: dict[str, Any] = {}

    def _target():
        try:
            holder["result"] = fn()
        except BaseException as exc:  # noqa: BLE001 — 워커 예외를 호출 스레드로 그대로 전달
            holder["error"] = exc

    worker = threading.Thread(target=_target, daemon=True, name="backtest-worker")
    worker.start()
    worker.join(budget)
    if worker.is_alive():
        print(f"[WATCHDOG] 백테스트가 {budget:.0f}s를 초과 — 워커 스레드 유기", flush=True)
        raise BacktestTimeoutError(timeout_message(budget))
    if "error" in holder:
        raise holder["error"]
    return holder["result"]
