"""Phase1 프로세스 풀 — 종목별 준비 계산(engine/phase1.py)을 워커 프로세스에 나눠 돌린다.

왜 프로세스인가: Phase1(pandas 지표·전처리)은 GIL에 묶여 스레드 수와 무관하게 같은 시간이
걸린다(2026-08-19 실측: 1스레드 ≈ 14스레드). 코어를 쓰려면 프로세스뿐이다.

설계
- **상주 풀**(프로세스 기동 5~9s를 매 백테스트마다 내지 않기 위해). 첫 사용 때 lazily 띄우고
  서버 수명 동안 재사용한다. 워커가 죽으면(BrokenPool) 다음 호출에서 다시 띄운다.
- **결정적 샤딩**: 종목 → 워커는 crc32(종목) % n 로 고정. 그래야 워커별 데이터 캐시(parquet)와
  최적화 세션 Phase1 캐시가 서로 겹치지 않고(총 메모리 = 단일 프로세스와 동일), 같은 종목이
  다음 백테스트·다음 시도에서도 같은 워커의 캐시에 적중한다.
- 워커마다 자기 큐(부모→워커) + 공용 결과 큐(워커→부모). 부모의 리더 스레드가 결과를
  job_id별로 배분하므로 여러 요청 스레드가 동시에 써도 된다.
- 최적화 세션(open/close)은 전 워커에 브로드캐스트한다 — 워커는 깊이 카운터로 중첩을 처리.
- 시작 방식 spawn 고정(fork는 부모 스레드·Polars/OpenMP 상태 상속 데드락 위험).

설정
- BACKTEST_PHASE1_WORKERS: 워커 수(1 이하 = 풀 비활성, 엔진 안 스레드 경로). 기본 min(cpu-1, 8).
- BACKTEST_PHASE1_POOL_MIN_SYMBOLS: 이 수 미만의 종목은 풀을 안 쓴다(기본 8, 왕복 비용 회피).
- BACKTEST_PREP_CACHE_MB: 세션 캐시 예산 — 워커에는 워커 수로 나눠 배분한다.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue as _queue
import threading
import time
import uuid
import zlib
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_MAX_WORKERS = 8
_DEFAULT_MIN_SYMBOLS = 8


def resolve_worker_count() -> int:
    raw = os.environ.get("BACKTEST_PHASE1_WORKERS")
    if raw not in (None, ""):
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    cpu = os.cpu_count() or 1
    return max(0, min(cpu - 1, DEFAULT_MAX_WORKERS))


def min_symbols() -> int:
    raw = os.environ.get("BACKTEST_PHASE1_POOL_MIN_SYMBOLS")
    try:
        return max(1, int(raw)) if raw else _DEFAULT_MIN_SYMBOLS
    except ValueError:
        return _DEFAULT_MIN_SYMBOLS


def shard_of(symbol: str, n: int) -> int:
    return zlib.crc32(str(symbol).encode("utf-8")) % n


# ────────────────────────────────────────────────────────────────
# 워커 프로세스
# ────────────────────────────────────────────────────────────────

def _worker_main(idx: int, task_q, result_q, engine_spec: Dict[str, Any], prep_budget_mb: float) -> None:
    os.environ["BACKTEST_PHASE1_WORKERS"] = "0"           # 워커 안에서 또 풀을 만들지 않는다
    os.environ.setdefault("BACKTEST_PREP_CACHE_MB", str(prep_budget_mb))
    from backtest_engine import BacktestEngine
    from engine import phase1
    from engine.prep_cache import SymbolPrepCache

    engine = BacktestEngine(**(engine_spec or {}))
    session_depth = 0
    cache: Optional[SymbolPrepCache] = None
    parent_pid = os.getppid()

    while True:
        try:
            msg = task_q.get(timeout=5.0)
        except _queue.Empty:
            # 부모가 죽었으면(uvicorn --reload 재시작·강제 종료) 고아로 남지 않는다.
            if os.getppid() != parent_pid:
                return
            continue
        except (EOFError, OSError):
            return
        kind = msg[0]
        if kind == "stop":
            return
        if kind == "session":
            _, job_id, action = msg
            if action == "open":
                if session_depth == 0:
                    cache = SymbolPrepCache()
                session_depth += 1
                result_q.put((job_id, idx, "ok", None))
            else:
                session_depth = max(0, session_depth - 1)
                stats = cache.stats() if cache is not None else {}
                if session_depth == 0:
                    cache = None
                result_q.put((job_id, idx, "ok", stats))
            continue
        if kind == "job":
            _, job_id, ctx, symbols = msg
            try:
                out: List[Tuple[str, Any, Dict[str, Any]]] = []
                for sym in symbols:
                    out.append(phase1.process_symbol(
                        sym, ctx, engine.loader, engine.indicator_engine, engine.signal_engine,
                        prep_cache=cache,
                    ))
                result_q.put((job_id, idx, "ok", out))
            except Exception as exc:  # 워커 전체 실패 → 부모가 스레드 경로로 폴백하지 않고 오류를 낸다
                result_q.put((job_id, idx, "error", f"{type(exc).__name__}: {exc}"))
            continue
        if kind == "rebalance_rows":
            # 리밸런싱 기간별 비교(FR-BT-064) — 시뮬레이터 입력 프레임을 받아 주기별 행을 만든다.
            # 부모는 메인 결과 정리(Format)와 겹쳐 돌리려고 시뮬레이션 직후 제출한다.
            _, job_id, payload = msg
            try:
                from engine.rebalance_comparison import simulate_rows_from_frames
                result_q.put((job_id, idx, "ok", simulate_rows_from_frames(payload)))
            except Exception as exc:
                result_q.put((job_id, idx, "error", f"{type(exc).__name__}: {exc}"))
            continue


# ────────────────────────────────────────────────────────────────
# 부모 쪽 풀
# ────────────────────────────────────────────────────────────────

class Phase1Pool:
    def __init__(self, n_workers: int, engine_spec: Dict[str, Any]):
        self.n_workers = max(1, int(n_workers))
        self.engine_spec = dict(engine_spec or {})
        self._ctx = mp.get_context("spawn")
        self._task_qs = [self._ctx.Queue() for _ in range(self.n_workers)]
        self._result_q = self._ctx.Queue()
        budget_mb = float(os.environ.get("BACKTEST_PREP_CACHE_MB", "2048"))
        per_worker_mb = max(128.0, budget_mb / self.n_workers)
        self._procs = [
            self._ctx.Process(
                target=_worker_main, name=f"phase1-worker-{i}", daemon=True,
                args=(i, self._task_qs[i], self._result_q, self.engine_spec, per_worker_mb),
            )
            for i in range(self.n_workers)
        ]
        for p in self._procs:
            p.start()
        self._waiters: Dict[str, "_queue.Queue"] = {}
        self._lock = threading.Lock()
        self._broken = False
        self._reader = threading.Thread(target=self._read_results, name="phase1-pool-reader", daemon=True)
        self._reader.start()
        self.last_session_stats: Dict[str, Any] = {}

    # ── 내부 ─────────────────────────────────────────────────
    def _read_results(self) -> None:
        while True:
            try:
                job_id, idx, status, payload = self._result_q.get(timeout=1.0)
            except _queue.Empty:
                if self._broken:
                    return
                continue
            except (EOFError, OSError):
                return
            with self._lock:
                waiter = self._waiters.get(job_id)
            if waiter is not None:
                waiter.put((idx, status, payload))

    def _register(self, job_id: str) -> "_queue.Queue":
        q: "_queue.Queue" = _queue.Queue()
        with self._lock:
            self._waiters[job_id] = q
        return q

    def _unregister(self, job_id: str) -> None:
        with self._lock:
            self._waiters.pop(job_id, None)

    def _alive(self) -> bool:
        return all(p.is_alive() for p in self._procs)

    def _collect(self, job_id: str, waiter, expected: int, timeout_s: float) -> Dict[int, Tuple[str, Any]]:
        got: Dict[int, Tuple[str, Any]] = {}
        deadline = time.monotonic() + timeout_s
        while len(got) < expected:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Phase1 워커 응답 대기 초과({timeout_s:.0f}s, {len(got)}/{expected})")
            try:
                idx, status, payload = waiter.get(timeout=min(1.0, remaining))
            except _queue.Empty:
                if not self._alive():
                    self._broken = True
                    raise RuntimeError("Phase1 워커 프로세스가 중단되었습니다(메모리 부족 가능). "
                                       "BACKTEST_PHASE1_WORKERS를 줄여 다시 시도해 주세요.")
                continue
            got[idx] = (status, payload)
        return got

    # ── 공개 API ─────────────────────────────────────────────
    @property
    def broken(self) -> bool:
        return self._broken or not self._alive()

    def run(self, ctx: Dict[str, Any], symbols: List[str], timeout_s: float) -> List[Tuple[str, Any, Dict[str, Any]]]:
        """symbols를 샤딩해 워커에 보내고 (status, data, side) 목록을 입력 순서대로 돌려준다."""
        shards: Dict[int, List[str]] = {}
        for sym in symbols:
            shards.setdefault(shard_of(sym, self.n_workers), []).append(sym)
        job_id = uuid.uuid4().hex
        waiter = self._register(job_id)
        try:
            for idx, syms in shards.items():
                self._task_qs[idx].put(("job", job_id, ctx, syms))
            got = self._collect(job_id, waiter, len(shards), timeout_s)
        finally:
            self._unregister(job_id)
        by_symbol: Dict[str, Tuple[str, Any, Dict[str, Any]]] = {}
        for idx, (status, payload) in got.items():
            if status != "ok":
                raise RuntimeError(f"Phase1 워커 {idx} 오류: {payload}")
            for sym, item in zip(shards[idx], payload):
                by_symbol[sym] = item
        return [by_symbol[s] for s in symbols if s in by_symbol]

    def submit_rebalance_rows(self, base_payload: Dict[str, Any], periods: List[str]) -> "RebalanceRowsJob":
        """주기 목록을 워커에 나눠 제출하고 핸들을 돌려준다(비동기) — 결과는 handle.result()로.

        프레임 피클(≈수 MB)이 워커마다 반복되므로 최대 len(periods)개 워커에만 라운드로빈으로 나눈다.
        """
        n = max(1, min(self.n_workers, len(periods)))
        per_worker: Dict[int, List[str]] = {}
        for i, period in enumerate(periods):
            per_worker.setdefault(i % n, []).append(period)
        job_id = uuid.uuid4().hex
        waiter = self._register(job_id)
        for idx, ps in per_worker.items():
            payload = dict(base_payload)
            payload["periods"] = list(ps)
            self._task_qs[idx].put(("rebalance_rows", job_id, payload))
        return RebalanceRowsJob(self, job_id, waiter, expected=len(per_worker), submitted=time.monotonic())

    def session(self, action: str, timeout_s: float = 60.0) -> Dict[str, Any]:
        """최적화 세션 open/close를 전 워커에 브로드캐스트하고 응답(닫을 때 캐시 통계)을 모은다."""
        job_id = uuid.uuid4().hex
        waiter = self._register(job_id)
        try:
            for q in self._task_qs:
                q.put(("session", job_id, action))
            got = self._collect(job_id, waiter, self.n_workers, timeout_s)
        finally:
            self._unregister(job_id)
        if action == "close":
            agg = {"hits": 0, "misses": 0, "entries": 0, "bytes": 0}
            for _, payload in got.values():
                for k in agg:
                    agg[k] += int((payload or {}).get(k, 0) or 0)
            self.last_session_stats = agg
            return agg
        return {}

    def close(self) -> None:
        self._broken = True
        for q in self._task_qs:
            try:
                q.put(("stop",))
            except Exception:
                pass
        for p in self._procs:
            try:
                p.join(timeout=2.0)
                if p.is_alive():
                    p.terminate()
            except Exception:
                pass


class RebalanceRowsJob:
    """submit_rebalance_rows()의 핸들 — result()가 워커별 행을 합쳐 돌려준다(주기 순서는 호출부가 정렬)."""

    def __init__(self, pool: Phase1Pool, job_id: str, waiter, expected: int, submitted: float):
        self._pool = pool
        self._job_id = job_id
        self._waiter = waiter
        self._expected = expected
        self.submitted = submitted

    def result(self, timeout_s: float) -> List[Dict[str, Any]]:
        try:
            got = self._pool._collect(self._job_id, self._waiter, self._expected, timeout_s)
        finally:
            self._pool._unregister(self._job_id)
        rows: List[Dict[str, Any]] = []
        for idx in sorted(got):
            status, payload = got[idx]
            if status != "ok":
                raise RuntimeError(f"Phase1 워커 {idx} 리밸런싱 비교 오류: {payload}")
            rows.extend(payload)
        return rows


# ────────────────────────────────────────────────────────────────
# 상주 풀 싱글턴 (엔진 인스턴스별이 아니라 프로세스별 — 데이터 디렉터리가 같으면 공유)
# ────────────────────────────────────────────────────────────────

_pools: Dict[Tuple, Phase1Pool] = {}
_pools_lock = threading.Lock()


def get_pool(engine_spec: Dict[str, Any]) -> Optional[Phase1Pool]:
    """설정상 켜져 있으면 (없으면 띄워서) 풀을 돌려준다. 꺼져 있으면 None."""
    n = resolve_worker_count()
    if n <= 1:
        return None
    key = (n, tuple(sorted((engine_spec or {}).items())))
    with _pools_lock:
        pool = _pools.get(key)
        if pool is not None and pool.broken:
            try:
                pool.close()
            except Exception:
                pass
            pool = None
        if pool is None:
            pool = Phase1Pool(n, engine_spec)
            _pools[key] = pool
        return pool


def shutdown_all() -> None:
    with _pools_lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()
