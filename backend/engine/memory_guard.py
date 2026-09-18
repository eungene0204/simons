"""컨테이너 메모리 한계에 **부딪히기 전에** 백테스트를 멈춘다.

한계를 넘으면 무엇을 죽일지는 커널이 고른다. Phase1 워커가 걸리면 phase1_pool이 그것을
사용자 문구(RESOURCE_EXHAUSTED_MESSAGE)로 바꿔 주지만, 본체(FastAPI 프로세스)가 걸리면
백엔드 컨테이너가 통째로 죽는다 — 사용자는 문구 없이 연결이 끊긴 것만 보고, 같은 프로세스에
있는 자동매매(VirtualTrader)까지 재시작된다. 어느 쪽이 걸릴지는 그때그때 다르다.

그래서 한계의 일정 비율(BACKTEST_MEMORY_GUARD_PCT, 기본 0.9)에 닿으면 **우리가 먼저** 실행을
끊고 같은 문구로 실패시킨다. 판단 근거는 cgroup의 익명 메모리(anon)다 — memory.current는
페이지 캐시를 포함해 한계 근처까지 차 있어도 정상이므로 신호로 쓸 수 없다.

한계가 없으면(로컬 dev·테스트) 가드는 아무 일도 하지 않는다.
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from typing import Any, Callable, Optional

from engine.phase1_pool import RESOURCE_EXHAUSTED_MESSAGE, BacktestResourceError

_CGROUP_V2_MAX = "/sys/fs/cgroup/memory.max"
_CGROUP_V2_STAT = "/sys/fs/cgroup/memory.stat"
_CGROUP_V1_MAX = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
_CGROUP_V1_STAT = "/sys/fs/cgroup/memory/memory.stat"

# v1의 limit_in_bytes는 '무제한'을 이 근처의 큰 수로 적는다(커널 버전마다 값이 다르다).
_V1_UNLIMITED_FLOOR = 1 << 62

_DEFAULT_THRESHOLD = 0.9
_DEFAULT_INTERVAL_S = 0.25   # 할당 속도가 빠를수록 늦게 보면 놓친다 — 감시는 촘촘하게


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as fh:
            return fh.read()
    except OSError:
        return None


def limit_bytes() -> Optional[int]:
    """컨테이너 메모리 한계(바이트). 한계가 없거나 읽을 수 없으면 None."""
    raw = _read(_CGROUP_V2_MAX)
    if raw is not None:
        raw = raw.strip()
        if raw == "max":
            return None
        try:
            return int(raw)
        except ValueError:
            return None
    raw = _read(_CGROUP_V1_MAX)
    if raw is None:
        return None
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    return None if value >= _V1_UNLIMITED_FLOOR else value


def anon_bytes() -> Optional[int]:
    """익명 메모리(파일 캐시 제외) 사용량. 읽을 수 없으면 None.

    컨테이너 안의 모든 프로세스(본체 + Phase1 워커)가 같은 cgroup이라 합계가 잡힌다.
    """
    for path, key in ((_CGROUP_V2_STAT, "anon"), (_CGROUP_V1_STAT, "rss")):
        raw = _read(path)
        if raw is None:
            continue
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == key:
                try:
                    return int(parts[1])
                except ValueError:
                    return None
    return None


def threshold() -> float:
    try:
        value = float(os.environ.get("BACKTEST_MEMORY_GUARD_PCT", _DEFAULT_THRESHOLD))
    except ValueError:
        return _DEFAULT_THRESHOLD
    return value if 0.0 < value <= 1.0 else _DEFAULT_THRESHOLD


def trip_bytes() -> Optional[int]:
    """이 사용량에 닿으면 중단한다. 한계가 없으면 None."""
    limit = limit_bytes()
    return None if limit is None else int(limit * threshold())


def _async_raise(thread_id: int, exc_type: Optional[type]) -> None:
    """다른 스레드에 예외를 심는다(None이면 심어 둔 예외를 거둔다).

    파이썬 바이트코드 경계에서 발동하므로 긴 C 호출(numpy 연산) 중에는 그 호출이 끝난 뒤
    올라온다 — 즉시는 아니지만 종목 루프가 파이썬이라 한 종목 안에서 끊긴다.
    """
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),
        ctypes.py_object(exc_type) if exc_type is not None else ctypes.c_void_p(0),
    )


def guarded(fn: Callable[[], Any], *, interval_s: float = _DEFAULT_INTERVAL_S) -> Any:
    """fn()을 메모리 감시 아래에서 실행한다. 한계 직전이면 BacktestResourceError.

    감시 스레드는 ① Phase1 워커를 먼저 정리해 메모리를 돌려받고 ② 호출 스레드에 예외를 심는다.
    한계를 모르거나(로컬 dev) 사용량을 못 읽으면 fn()을 그대로 부른다.
    """
    trip = trip_bytes()
    if trip is None or anon_bytes() is None:
        return fn()

    target_tid = threading.get_ident()
    done = threading.Event()
    tripped = threading.Event()

    def _watch() -> None:
        while not done.wait(interval_s):
            used = anon_bytes()
            if used is None or used < trip:
                continue
            tripped.set()
            print(f"[BT-MEM] 메모리 한계 접근 — 사용 {used / 1024**3:.1f}GB / 중단선 "
                  f"{trip / 1024**3:.1f}GB (한계의 {threshold():.0%}) — 백테스트 중단", flush=True)
            try:
                from engine import phase1_pool
                phase1_pool.shutdown_all()      # 워커가 쥔 메모리를 먼저 돌려받는다
            except Exception as exc:            # noqa: BLE001 — 정리 실패가 중단을 막지 않는다
                print(f"[BT-MEM] 워커 정리 실패(무시): {exc}", flush=True)
            _async_raise(target_tid, BacktestResourceError)
            return

    watcher = threading.Thread(target=_watch, daemon=True, name="backtest-memory-guard")
    watcher.start()
    try:
        result = fn()
    except BacktestResourceError:
        raise BacktestResourceError(RESOURCE_EXHAUSTED_MESSAGE)
    finally:
        done.set()
        watcher.join(timeout=interval_s * 4)
        if tripped.is_set():
            _async_raise(target_tid, None)      # fn이 먼저 끝났으면 심어 둔 예외를 거둔다
    if tripped.is_set():
        raise BacktestResourceError(RESOURCE_EXHAUSTED_MESSAGE)
    return result
