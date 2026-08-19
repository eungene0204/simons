"""워크포워드 창(window) 단위 프로세스 병렬 — 워커 프로세스 코드 + 부모 쪽 풀 헬퍼.

창은 서로 독립이다(각 창 = IS 최적화 + OOS 검증, 자기 날짜 범위만 사용). 파이썬 GIL
때문에 스레드로는 CPU 병렬이 안 되므로 **프로세스 풀**로 창을 흩뿌린다. 워커마다
BacktestEngine을 따로 만들므로 엔진의 공유 가변 상태(warnings 등) 경합도 없다.

- 시작 방식은 spawn 고정: fork는 부모의 스레드(uvicorn·스레드풀)와 Polars/OpenMP 런타임
  상태를 물려받아 데드락 위험이 있다(docs/deployment.md §7 가드와 같은 이유).
- 워커 기동(spawn + vectorbt·pandas import ≈ 5~9s)은 부모의 '기간 확인' 백테스트와
  겹치도록 창 분할 전에 미리 띄운다(WindowPool.start → 워커 수만큼 warm 작업 제출).
- 진행률은 mp.Queue로 부모에 올린다(워커→부모 단방향). 취소는 mp.Event(부모→워커).
- 워커의 Phase1 스레드 수는 작게(코어÷워커, 최대 4) 잡는다 — Phase1은 GIL에 묶여 스레드가
  속도를 내지 못하고(2026-08-19 실측: 1스레드≈14스레드), 프로세스가 여럿이면 오히려
  서로 방해한다(3워커: 14스레드 53s → 2스레드 34s).
- 워커의 Phase1 캐시 예산은 워커 수로 나눈다 — 기본값 그대로면 워커 수만큼 곱해진다.

이 모듈은 spawn된 자식이 import 하므로 워커 함수는 최상위에 둔다(클로저·람다 금지).
"""

from __future__ import annotations

import concurrent.futures as cf
import multiprocessing as mp
import os
import queue as _queue
import time
from typing import Any, Callable, Dict, Optional

# ── 워커 프로세스 전역 ───────────────────────────────────────────────
_engine = None
_progress_queue = None
_cancel_event = None
_engine_spec: Dict[str, Any] = {}


def worker_init(progress_queue, cancel_event, engine_spec: Dict[str, Any],
                prep_cache_mb: Optional[float], phase1_threads: Optional[int],
                phase1_workers: Optional[int] = None) -> None:
    """ProcessPoolExecutor initializer — 워커 전역 상태 설정 + 엔진을 미리 만든다(warm).

    engine_spec: 부모 엔진의 ``worker_spec()`` — 워커에서 같은 엔진을 다시 만들 kwargs.
    phase1_workers: 이 창 워커가 안에서 띄울 Phase1 프로세스 풀 크기(코어÷창 워커, 1 이하=스레드 경로).
        창 병렬 × Phase1 병렬이 코어 수를 넘지 않게 부모가 나눠 준다.
    """
    global _progress_queue, _cancel_event, _engine_spec
    _progress_queue = progress_queue
    _cancel_event = cancel_event
    _engine_spec = dict(engine_spec or {})
    if prep_cache_mb is not None and "BACKTEST_PREP_CACHE_MB" not in os.environ:
        os.environ["BACKTEST_PREP_CACHE_MB"] = str(prep_cache_mb)
    if phase1_threads is not None and "BACKTEST_PHASE1_THREADS" not in os.environ:
        os.environ["BACKTEST_PHASE1_THREADS"] = str(int(phase1_threads))
    if phase1_workers is not None and "BACKTEST_PHASE1_WORKERS" not in os.environ:
        os.environ["BACKTEST_PHASE1_WORKERS"] = str(int(phase1_workers))
    _get_engine()


def _get_engine():
    global _engine
    if _engine is None:
        from backtest_engine import BacktestEngine
        _engine = BacktestEngine(**_engine_spec)
    return _engine


def _should_cancel() -> bool:
    return bool(_cancel_event is not None and _cancel_event.is_set())


def _emit(payload: Dict[str, Any]) -> None:
    if _progress_queue is None:
        return
    try:
        _progress_queue.put_nowait(payload)
    except Exception:
        pass


def warm_task(delay_s: float = 0.5) -> bool:
    """워커를 미리 띄우기 위한 빈 작업 — 잠깐 점유해 다음 warm 제출이 새 프로세스를 띄우게 한다."""
    time.sleep(delay_s)
    return True


def run_window_task(spec: Dict[str, Any]) -> Dict[str, Any]:
    """창 하나를 이 워커에서 실행한다. spec은 WalkForwardAnalyzer._run_window 인자(피클 가능)."""
    from engine.walk_forward import WalkForwardAnalyzer

    window_idx = int(spec["window_idx"])
    _emit({"window": window_idx, "event": "start"})

    def _on_trial(done: int, total: int, timing: Optional[Dict[str, Any]] = None) -> None:
        event: Dict[str, Any] = {"window": window_idx, "event": "trial", "trial": done, "trial_total": total}
        if timing:
            event["timing"] = timing
        _emit(event)

    engine = _get_engine()
    analyzer = WalkForwardAnalyzer(engine)
    with engine.optimization_session():
        result = analyzer._run_window(
            base_request=spec["base_request"],
            ranges=spec["ranges"],
            is_start=spec["is_start"],
            is_end=spec["is_end"],
            oos_start=spec["oos_start"],
            oos_end=spec["oos_end"],
            target_metric=spec["target_metric"],
            n_trials=spec["n_trials"],
            window_idx=window_idx,
            method=spec["method"],
            on_trial=_on_trial,
            should_cancel=_should_cancel,
        )
    _emit({"window": window_idx, "event": "done"})
    return result


# ── 부모 쪽 풀 헬퍼 ────────────────────────────────────────────────

class WindowPool:
    """spawn 프로세스 풀 + 진행률 큐 + 취소 이벤트 묶음. 부모(WalkForwardAnalyzer)가 쓴다."""

    def __init__(self, n_workers: int, engine_spec: Dict[str, Any]):
        self.n_workers = max(1, int(n_workers))
        self._ctx = mp.get_context("spawn")
        self.progress_q = self._ctx.Queue()
        self.cancel_ev = self._ctx.Event()
        prep_mb = None
        if "BACKTEST_PREP_CACHE_MB" not in os.environ:
            from engine.prep_cache import _DEFAULT_BUDGET_MB
            prep_mb = max(256.0, _DEFAULT_BUDGET_MB / self.n_workers)
        cpu = os.cpu_count() or 1
        phase1_threads = max(1, min(4, cpu // self.n_workers))
        # 창 워커 안의 Phase1 프로세스 풀 크기 — 창 워커 수 × Phase1 워커 수 ≤ 코어 수.
        # 부모가 BACKTEST_PHASE1_WORKERS를 명시했으면 그 값을 그대로 물려받는다(초기화 함수가 setdefault).
        phase1_workers = max(1, cpu // self.n_workers)
        self.executor = cf.ProcessPoolExecutor(
            max_workers=self.n_workers, mp_context=self._ctx,
            initializer=worker_init,
            initargs=(self.progress_q, self.cancel_ev, dict(engine_spec or {}), prep_mb, phase1_threads,
                      phase1_workers),
        )
        self._closed = False

    def start(self) -> None:
        """워커 수만큼 warm 작업을 연달아 제출해 프로세스를 지금 띄운다(기동을 부모 작업과 겹침)."""
        for _ in range(self.n_workers):
            try:
                self.executor.submit(warm_task)
            except Exception:
                break

    def submit_window(self, spec: Dict[str, Any]):
        return self.executor.submit(run_window_task, spec)

    def cancel(self) -> None:
        self.cancel_ev.set()

    def drain(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        while True:
            try:
                handler(self.progress_q.get_nowait())
            except _queue.Empty:
                return
            except Exception:
                return

    def close(self, wait: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.executor.shutdown(wait=wait, cancel_futures=True)
        except Exception:
            pass
        try:
            self.progress_q.close()
        except Exception:
            pass
