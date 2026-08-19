"""
Walk-Forward Analysis Engine

훈련(IS)/검증(OOS) 기간 분할 최적화를 통해 전략 과적합을 탐지하고
실전 성과를 추정한다.

Rolling 방식 (anchor=False):
  - IS 창이 OOS 창과 함께 앞으로 이동
  - Window k: IS=[k*oos_size, k*oos_size+is_size], OOS=[k*oos_size+is_size, k*oos_size+is_size+oos_size]

Anchored/Expanding 방식 (anchor=True):
  - IS 창은 항상 데이터 시작부터
  - Window k: IS=[0, k*oos_size+is0_size], OOS=[k*oos_size+is0_size, ...]
"""

import copy
import math
import os
from typing import Any, Callable, Dict, List, Optional, Tuple
from engine.grid_optimizer import optimization_session, set_nested_value

# 윈도우 하나마다 IS 최적화(수십 회 백테스트)가 반복되므로 폭주 방지 상한.
MAX_WINDOWS = 24

# 창 단위 병렬 워커 수 상한 기본값 — 워커마다 엔진·데이터 캐시·Phase1 캐시를 따로 가지므로
# 코어 수와 메모리 둘 다 본다. WALK_FORWARD_WORKERS로 명시하면 그 값을 쓴다(1=순차).
DEFAULT_MAX_WORKERS = 8


def resolve_worker_count(n_windows: int) -> int:
    """창 병렬 워커 수. 창이 1개면 항상 1(프로세스 풀 기동 비용만 든다).

    WALK_FORWARD_WORKERS: 양의 정수(1=순차). 없으면 min(cpu-1, DEFAULT_MAX_WORKERS, 창 수).
    """
    if n_windows <= 1:
        return 1
    raw = os.environ.get("WALK_FORWARD_WORKERS")
    if raw not in (None, ""):
        try:
            return max(1, min(int(raw), n_windows))
        except ValueError:
            pass
    cpu = os.cpu_count() or 1
    return max(1, min(cpu - 1, DEFAULT_MAX_WORKERS, n_windows))

# 윈도우/집계 결과에 담는 성과 지표 키 (엔진 결과 키와 동일).
METRIC_KEYS = [
    "cagr", "totalReturn", "maxDrawdown", "sharpe",
    "winRate", "profitFactor", "trades", "calmar", "expectancy",
]


def _finite(value: Any) -> Optional[float]:
    """숫자이면서 유한한 값만 float로 반환, 아니면 None (NaN/Infinity 전파 방지)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


class WalkForwardAnalyzer:
    def __init__(self, engine):
        """
        engine: BacktestEngine instance
        """
        self.engine = engine

    # ─────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────

    def analyze(
        self,
        base_request: Dict[str, Any],
        ranges: Dict[str, Any],
        n_splits: int = 5,
        train_pct: float = 0.7,
        anchor: bool = False,
        target_metric: str = "cagr",
        n_trials: int = 30,
        method: str = "bayesian",
        is_bars: Optional[int] = None,
        oos_bars: Optional[int] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Walk-Forward Analysis 실행.

        전체를 엔진의 최적화 세션 안에서 돈다 — 창 안의 IS 시도들이 Phase1 산출물을
        재사용하고, 기간 확인·OOS 백테스트도 결과 화면 전용 부가 산출물을 만들지 않는다.
        (재계산 제거, 2026-08-19 실측: 백테스트 시간의 97%가 Phase1)
        """
        with optimization_session(self.engine):
            return self._analyze(
                base_request, ranges, n_splits, train_pct, anchor, target_metric,
                n_trials, method, is_bars, oos_bars, progress_callback, should_cancel,
            )

    def _analyze(
        self, base_request, ranges, n_splits, train_pct, anchor, target_metric,
        n_trials, method, is_bars, oos_bars, progress_callback, should_cancel,
    ) -> Dict[str, Any]:
        """
        Returns:
          {
            status, n_splits, anchor, target_metric,
            windows: [{ window, is_period, oos_period, best_params,
                        is_metrics, oos_metrics, oos_equity, oos_dates }],
            aggregate: { avg_oos_cagr, avg_oos_mdd, avg_oos_sharpe,
                         avg_oos_win_rate, avg_oos_trades },
            combined_equity, combined_dates,
            walk_forward_efficiency,   # 창별 OOS CAGR 평균 ÷ 창별 IS CAGR 평균 (연환산 기준)
            wfe_valid, wfe_basis,
            message
          }
        """
        def _notify(payload: Dict[str, Any]):
            if progress_callback is None:
                return
            try:
                progress_callback(payload)
            except Exception:
                pass

        # 0. 창 병렬 워커 풀을 먼저 띄운다 — 워커 기동(spawn+import ≈ 5~9s)이 아래 '기간 확인'
        # 백테스트와 겹치게. 창 수는 아직 모르므로 힌트(n_splits, 명시 창이면 상한)로 잡고,
        # 실제 창 수가 1이거나 워커가 1이면 순차로 돌고 풀은 닫는다.
        # 워커는 엔진을 자기 프로세스에서 다시 만들어야 하므로 worker_spec()을 제공하는
        # 엔진(BacktestEngine)만 병렬 대상이다 — 테스트용 스텁 엔진은 순차로 돈다.
        pool = None
        can_parallel = callable(getattr(self.engine, "worker_spec", None))
        if can_parallel:
            hint = int(n_splits or 0) if not (is_bars and oos_bars) else MAX_WINDOWS
            hinted_workers = resolve_worker_count(hint)
            if hinted_workers > 1:
                pool = self._start_pool(hinted_workers)
        try:
            return self._analyze_with_pool(
                pool, base_request, ranges, n_splits, train_pct, anchor, target_metric,
                n_trials, method, is_bars, oos_bars, _notify, should_cancel,
            )
        finally:
            if pool is not None:
                pool.close()

    def _start_pool(self, n_workers: int):
        from engine.wfa_workers import WindowPool
        pool = WindowPool(n_workers, self.engine.worker_spec())
        pool.start()
        return pool

    def _analyze_with_pool(
        self, pool, base_request, ranges, n_splits, train_pct, anchor, target_metric,
        n_trials, method, is_bars, oos_bars, _notify, should_cancel,
    ) -> Dict[str, Any]:
        # 1. 백테스트 날짜 범위 획득 (표시=실행: 화면에 보인 기간과 동일)
        _notify({"stage": "prepare", "message": "백테스트 기간 데이터를 확인하는 중..."})
        dates = self._get_backtest_dates(base_request)
        if not dates:
            return {"status": "error", "message": "데이터를 불러올 수 없습니다."}

        if len(dates) < 60:
            return {"status": "error", "message": f"데이터가 너무 짧습니다: {len(dates)}일"}

        # 2. 윈도우 분할 — is_bars/oos_bars가 명시되면 UI가 보여준 거래일 수를 그대로 사용
        windows = self._split_windows(dates, n_splits, train_pct, anchor, is_bars, oos_bars)
        if not windows:
            return {"status": "error", "message": "윈도우 분할에 실패했습니다. 기간을 늘려보세요."}
        if len(windows) > MAX_WINDOWS:
            return {
                "status": "error",
                "message": (
                    f"윈도우 수({len(windows)}개)가 상한({MAX_WINDOWS}개)을 초과했습니다. "
                    "학습/검증 기간을 늘려 구간 수를 줄여 주세요."
                ),
            }

        print(f"[WFA] {len(windows)} windows, total={len(dates)} days", flush=True)

        # 3. 각 윈도우 실행 — 창은 서로 독립이라 워커 풀이 있고 창이 2개 이상이면 병렬 실행.
        run_args = (windows, base_request, ranges, target_metric, n_trials, method, _notify, should_cancel)
        if pool is not None and len(windows) > 1:
            outcome = self._run_windows_parallel(pool, *run_args)
        else:
            outcome = self._run_windows_sequential(*run_args)
        if outcome.get("status") in ("cancelled", "error"):
            return outcome
        window_results = outcome["windows"]

        # WFE 표본: 창 단위로 (IS CAGR, OOS CAGR) 짝을 맞춰 모은다 — 한쪽만 있는 창은 제외.
        wfe_pairs: List[Tuple[float, float]] = []
        for w_result in window_results:
            is_cagr = _finite(w_result.get("is_metrics", {}).get("cagr"))
            oos_cagr = _finite(w_result.get("oos_metrics", {}).get("cagr"))
            if is_cagr is not None and oos_cagr is not None:
                wfe_pairs.append((is_cagr, oos_cagr))

        # 모든 윈도우가 실패했으면 부분 결과 대신 즉시 에러로 알린다 (Fail Fast).
        errors = [w.get("error") for w in window_results]
        if all(errors):
            return {
                "status": "error",
                "message": f"모든 윈도우가 실패했습니다: {errors[0]}",
            }

        # 4. 집계
        aggregate = self._aggregate(window_results)
        combined_equity, combined_dates = self._combine_equity(window_results)

        # Walk-Forward Efficiency (WFE) = 창별 OOS CAGR 평균 / 창별 IS CAGR 평균 (Pardo 정의: 연환산끼리).
        # 총수익률(totalReturn)로 나누면 안 된다 — IS 창이 OOS 창보다 길어(기본 50%:15%≈3.3배)
        # 정상성 있는 전략(IS=OOS CAGR)조차 WFE≈0.3으로 '과최적화'로 찍힌다(2026-08-19 감사).
        # IS·OOS 한쪽만 유효한 창은 표본에서 함께 제외해 분자·분모의 창 집합을 일치시킨다.
        # IS 평균이 0 이하이면 비율의 부호가 뒤집혀 해석 불능이므로(감사 M9)
        # wfe_valid=False로 표시하고 0을 반환한다.
        avg_is = sum(p[0] for p in wfe_pairs) / len(wfe_pairs) if wfe_pairs else 0.0
        avg_oos = sum(p[1] for p in wfe_pairs) / len(wfe_pairs) if wfe_pairs else 0.0
        wfe_valid = avg_is > 0
        wfe = (avg_oos / avg_is) if wfe_valid else 0.0

        return {
            "status": "ok",
            "n_splits": len(windows),
            "anchor": anchor,
            "target_metric": target_metric,
            "windows": window_results,
            "aggregate": aggregate,
            "combined_equity": combined_equity,
            "combined_dates": combined_dates,
            "walk_forward_efficiency": round(wfe, 4),
            "wfe_valid": wfe_valid,
            # WFE 산정 기준. 구버전 저장 결과(총수익률 기준)에는 이 키가 없다 — UI가 문구를 구분한다.
            "wfe_basis": "cagr",
        }

    # ─────────────────────────────────────────────────────────
    # 창 실행 — 순차 / 병렬
    # ─────────────────────────────────────────────────────────

    def _run_windows_sequential(
        self, windows, base_request, ranges, target_metric, n_trials, method, _notify, should_cancel,
    ) -> Dict[str, Any]:
        """창을 이 프로세스에서 순서대로 실행한다(WALK_FORWARD_WORKERS=1 또는 창 1개)."""
        window_results: List[Dict[str, Any]] = []
        for i, (is_start, is_end, oos_start, oos_end) in enumerate(windows):
            # 협조적 취소: 창 경계 + (아래 _run_window를 통해) 창 내부 시도/조합 단위로도 확인
            if should_cancel is not None and should_cancel():
                print(f"[WFA] cancelled at window {i+1}/{len(windows)}", flush=True)
                return {"status": "cancelled", "message": f"창 {i}/{len(windows)} 완료 후 취소되었습니다."}

            print(f"[WFA] Window {i+1}/{len(windows)}: IS={is_start}~{is_end}, OOS={oos_start}~{oos_end}", flush=True)

            window_payload = {
                "stage": "window",
                "window": i + 1,
                "total": len(windows),
                "is_period": f"{is_start} ~ {is_end}",
                "oos_period": f"{oos_start} ~ {oos_end}",
            }
            _notify(window_payload)

            # 창 내부 IS 최적화(수십 회 백테스트)는 수 분간 침묵할 수 있으므로,
            # 시도(trial)마다 창 진행률에 trial/trial_total(+단계별 소요 timing)을 얹어 다시 알린다.
            def _on_trial(done: int, total: int, timing: Optional[Dict[str, Any]] = None, _payload=window_payload):
                event = {**_payload, "trial": done, "trial_total": total}
                if timing:
                    event["timing"] = timing
                _notify(event)

            w_result = self._run_window(
                base_request=base_request,
                ranges=ranges,
                is_start=is_start,
                is_end=is_end,
                oos_start=oos_start,
                oos_end=oos_end,
                target_metric=target_metric,
                n_trials=n_trials,
                window_idx=i + 1,
                method=method,
                on_trial=_on_trial,
                should_cancel=should_cancel,
            )
            if w_result.get("cancelled"):
                print(f"[WFA] cancelled during window {i+1}/{len(windows)}", flush=True)
                return {"status": "cancelled", "message": f"창 {i+1}/{len(windows)} 진행 중 취소되었습니다."}
            window_results.append(w_result)
        return {"status": "ok", "windows": window_results}

    def _run_windows_parallel(
        self, pool, windows, base_request, ranges, target_metric, n_trials, method, _notify, should_cancel,
    ) -> Dict[str, Any]:
        """창을 spawn 프로세스 풀(engine/wfa_workers.WindowPool)에 흩뿌려 병렬 실행한다.

        결과는 순차 실행과 동일하다 — 창은 독립이고 옵튜나 샘플러는 시드가 고정돼 있다.
        진행률은 워커가 큐로 올린 창별 시도 이벤트를 부모가 합산해 알린다:
          {stage:'window', window, total, is_period, oos_period, trial, trial_total, timing,
           windows_done, trials_done, workers, active_windows}
        취소는 부모가 mp.Event를 세우면 워커가 시도 경계에서 협조적으로 멈춘다.
        """
        import concurrent.futures as cf

        total = len(windows)
        n_workers = pool.n_workers
        periods = {i + 1: (f"{w[0]} ~ {w[1]}", f"{w[2]} ~ {w[3]}") for i, w in enumerate(windows)}
        print(f"[WFA] {total} windows on {n_workers} worker processes", flush=True)

        # 진행 상태(창별) — 부모가 합산해 한 이벤트로 알린다.
        trial_state: Dict[int, Dict[str, Any]] = {}
        active: List[int] = []
        done_windows: List[int] = []
        results: Dict[int, Dict[str, Any]] = {}

        def _emit_progress(from_window: int) -> None:
            st = trial_state.get(from_window, {})
            is_p, oos_p = periods[from_window]
            trials_done = sum(int(v.get("trial") or 0) for v in trial_state.values())
            event: Dict[str, Any] = {
                "stage": "window",
                "window": from_window,
                "total": total,
                "is_period": is_p,
                "oos_period": oos_p,
                "windows_done": len(done_windows),
                "trials_done": trials_done,
                "workers": n_workers,
                "active_windows": sorted(active),
            }
            if st.get("trial_total"):
                event["trial"] = st.get("trial", 0)
                event["trial_total"] = st["trial_total"]
            if st.get("timing"):
                event["timing"] = st["timing"]
            _notify(event)

        def _handle_msg(msg: Dict[str, Any]) -> None:
            w = int(msg.get("window", 0))
            if w not in periods:
                return
            kind = msg.get("event")
            if kind == "start":
                if w not in active:
                    active.append(w)
                trial_state.setdefault(w, {})
                print(f"[WFA] Window {w}/{total} started: IS={periods[w][0]}, OOS={periods[w][1]}", flush=True)
            elif kind == "trial":
                st = trial_state.setdefault(w, {})
                st["trial"] = msg.get("trial", 0)
                st["trial_total"] = msg.get("trial_total")
                if msg.get("timing"):
                    st["timing"] = msg["timing"]
            elif kind == "done":
                if w in active:
                    active.remove(w)
                if w not in done_windows:
                    done_windows.append(w)
                st = trial_state.setdefault(w, {})
                if st.get("trial_total"):
                    st["trial"] = st["trial_total"]
            _emit_progress(w)

        cancelled = False
        try:
            futures = {}
            for i, (is_start, is_end, oos_start, oos_end) in enumerate(windows):
                spec = {
                    "window_idx": i + 1,
                    "base_request": base_request, "ranges": ranges,
                    "is_start": is_start, "is_end": is_end, "oos_start": oos_start, "oos_end": oos_end,
                    "target_metric": target_metric, "n_trials": n_trials, "method": method,
                }
                futures[pool.submit_window(spec)] = i + 1
            pending = set(futures)
            while pending:
                if not cancelled and should_cancel is not None and should_cancel():
                    cancelled = True
                    pool.cancel()
                    print("[WFA] cancel requested — signalling workers", flush=True)
                finished, pending = cf.wait(pending, timeout=0.2, return_when=cf.FIRST_COMPLETED)
                pool.drain(_handle_msg)
                for fut in finished:
                    w = futures[fut]
                    try:
                        results[w] = fut.result()
                    except Exception as exc:  # 워커 안의 예외 → 창 단위 오류(다른 창은 계속)
                        print(f"[WFA] Window {w} failed in worker: {exc}", flush=True)
                        is_p, oos_p = periods[w]
                        results[w] = {
                            "window": w, "is_period": is_p, "oos_period": oos_p,
                            "best_params": {}, "is_metrics": {}, "oos_metrics": {},
                            "oos_equity": [], "oos_dates": [], "error": f"창 실행 오류: {exc}",
                        }
                if cancelled:
                    # 워커는 시도 경계에서 멈춰 cancelled 결과를 돌려준다 — 아직 시작 안 한 제출분은 취소
                    for fut in pending:
                        fut.cancel()
                    pending = {f for f in pending if not f.cancelled()}
            pool.drain(_handle_msg)
        except cf.process.BrokenProcessPool as exc:
            return {
                "status": "error",
                "message": (
                    "병렬 창 실행 프로세스가 중단되었습니다(메모리 부족 가능). "
                    f"WALK_FORWARD_WORKERS를 줄여 다시 시도해 주세요. ({exc})"
                ),
            }

        if cancelled or any(r.get("cancelled") for r in results.values()):
            done_n = sum(1 for r in results.values() if r and not r.get("cancelled") and not r.get("error"))
            return {"status": "cancelled", "message": f"창 {done_n}/{total} 완료 후 취소되었습니다."}

        window_results = [results[i + 1] for i in range(total) if (i + 1) in results]
        if len(window_results) != total:
            return {"status": "error", "message": "일부 창의 결과를 받지 못했습니다."}
        return {"status": "ok", "windows": window_results}

    # ─────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────

    def _get_backtest_dates(self, base_request: Dict[str, Any]) -> List[str]:
        """백테스트가 실제로 사용하는 날짜 목록을 반환.

        워크포워드는 사용자가 백테스트한 바로 그 기간(base_request의 period·
        날짜 범위)에서 구간을 나눈다. 여기서 기간을 'full'로 강제 확장하면
        화면에 표시된 구간 수(result.dates 기준 추정)와 실제 실행 구간 수가
        어긋나(표시=실행 위반) '실행 가능'이라던 설정이 백엔드에서 상한 초과로
        실패하므로, base_request를 그대로 실행해 표시와 동일한 날짜를 쓴다.
        """
        try:
            req = copy.deepcopy(base_request)
            result = self.engine.run_backtest(req)
            return result.get("dates", [])
        except Exception as e:
            print(f"[WFA] _get_backtest_dates failed: {e}", flush=True)
            return []

    def _split_windows(
        self,
        dates: List[str],
        n_splits: int,
        train_pct: float,
        anchor: bool,
        is_bars: Optional[int] = None,
        oos_bars: Optional[int] = None,
    ) -> List[Tuple[str, str, str, str]]:
        """
        (is_start, is_end, oos_start, oos_end) 튜플 리스트 반환.

        명시적 bars 방식 (is_bars/oos_bars 지정):
          UI에서 사용자가 고른 학습/검증 거래일 수를 그대로 사용해
          화면에 표시된 구간 날짜와 실제 실행 구간이 일치하도록 한다.

        Rolling 방식:
          ratio = train_pct / (1 - train_pct)
          oos_size = T / (ratio + n_splits)
          is_size = oos_size * ratio

        Anchored 방식:
          oos_size = (T - min_is) / n_splits  where min_is = T * train_pct
          Window k: IS=[0, min_is + k*oos_size], OOS=[min_is+k*oos_size, min_is+(k+1)*oos_size]
        """
        T = len(dates)
        windows = []

        if is_bars and oos_bars and is_bars > 0 and oos_bars > 0:
            is_size, oos_size = int(is_bars), int(oos_bars)
            if is_size + oos_size > T:
                return []

            if not anchor:
                k = 0
                while True:
                    is_s = k * oos_size
                    is_e = is_s + is_size
                    oos_s = is_e
                    oos_e = oos_s + oos_size
                    if oos_e > T:
                        break
                    windows.append((
                        dates[is_s],
                        dates[is_e - 1],
                        dates[oos_s],
                        dates[oos_e - 1],
                    ))
                    k += 1
            else:
                # 롤링과 같은 규칙: 검증 길이(oos_bars)를 다 채우지 못하는 마지막 조각 창은 만들지 않는다.
                # 예전엔 `while is_e < T` + `min(…, T)`로 잘린 창을 하나 더 만들어 UI 예상 구간 수
                # (floor((T-is)/oos))보다 1개 많았고(표시≠실행), 며칠짜리 검증 창의 CAGR 연환산이
                # 집계를 오염시켰다(2026-08-19 감사).
                is_e = is_size
                while is_e + oos_size <= T:
                    oos_s = is_e
                    oos_e = oos_s + oos_size
                    windows.append((
                        dates[0],
                        dates[is_e - 1],
                        dates[oos_s],
                        dates[oos_e - 1],
                    ))
                    is_e += oos_size
            return windows

        if not anchor:
            # Rolling walk-forward
            ratio = train_pct / (1.0 - train_pct)
            oos_size = max(1, int(T / (ratio + n_splits)))
            is_size = max(1, int(oos_size * ratio))

            for k in range(n_splits):
                is_s = k * oos_size
                is_e = is_s + is_size
                oos_s = is_e
                oos_e = oos_s + oos_size

                if oos_e > T:
                    break
                if is_s >= T or is_e > T:
                    break

                windows.append((
                    dates[is_s],
                    dates[is_e - 1],
                    dates[oos_s],
                    dates[min(oos_e - 1, T - 1)],
                ))
        else:
            # Anchored (expanding) walk-forward
            min_is = max(20, int(T * train_pct))
            remaining = T - min_is
            if remaining < n_splits:
                return []
            oos_size = max(1, remaining // n_splits)

            for k in range(n_splits):
                is_s = 0
                is_e = min_is + k * oos_size
                oos_s = is_e
                oos_e = oos_s + oos_size

                if oos_e > T:
                    oos_e = T
                if oos_s >= T:
                    break

                windows.append((
                    dates[is_s],
                    dates[is_e - 1],
                    dates[oos_s],
                    dates[min(oos_e - 1, T - 1)],
                ))

        return windows

    def _run_window(
        self,
        base_request: Dict[str, Any],
        ranges: Dict[str, Any],
        is_start: str,
        is_end: str,
        oos_start: str,
        oos_end: str,
        target_metric: str,
        n_trials: int,
        window_idx: int,
        method: str = "bayesian",
        on_trial: Optional[Callable[..., None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """단일 윈도우: IS 최적화 → OOS 검증. 취소 시 result["cancelled"]=True로 반환."""
        result: Dict[str, Any] = {
            "window": window_idx,
            "is_period": f"{is_start} ~ {is_end}",
            "oos_period": f"{oos_start} ~ {oos_end}",
            "best_params": {},
            "is_metrics": {},
            "oos_metrics": {},
            "oos_equity": [],
            "oos_dates": [],
        }

        # ── IS 최적화 ─────────────────────────────────────────
        is_req = copy.deepcopy(base_request)
        is_req["startDate"] = is_start
        is_req["endDate"] = is_end
        is_req["period"] = "full"

        try:
            if method == "grid":
                from engine.grid_optimizer import StrategyOptimizer

                optimizer = StrategyOptimizer(self.engine)
                opt_result = optimizer.optimize(
                    base_request=is_req,
                    ranges=ranges,
                    target_metric=target_metric,
                    progress_callback=on_trial,
                    should_cancel=should_cancel,
                )
            else:
                from engine.optuna_optimizer import OptunaOptimizer

                optimizer = OptunaOptimizer(self.engine)
                opt_result = optimizer.optimize(
                    base_request=is_req,
                    ranges=ranges,
                    target_metric=target_metric,
                    n_trials=n_trials,
                    progress_callback=on_trial,
                    should_cancel=should_cancel,
                )
            if opt_result.get("status") == "cancelled":
                result["cancelled"] = True
                return result
            if opt_result.get("status") == "error":
                result["error"] = opt_result.get("message", "IS 최적화 실패")
                return result

            best_params = opt_result.get("best_parameters") or {}
            best_is_metrics = opt_result.get("best_metrics") or {}
            result["best_params"] = best_params
            result["is_metrics"] = {k: best_is_metrics.get(k) for k in METRIC_KEYS}
        except Exception as e:
            print(f"[WFA] Window {window_idx} IS optimization failed: {e}", flush=True)
            result["error"] = f"IS 최적화 오류: {str(e)}"
            return result

        # ── OOS 검증 ─────────────────────────────────────────
        if should_cancel is not None and should_cancel():
            result["cancelled"] = True
            return result

        oos_req = copy.deepcopy(base_request)
        for path, value in best_params.items():
            try:
                set_nested_value(oos_req, path, value)
            except Exception as e:
                print(f"[WFA] set_nested_value failed for {path}: {e}", flush=True)

        oos_req["startDate"] = oos_start
        oos_req["endDate"] = oos_end
        oos_req["period"] = "full"

        try:
            oos_result = self.engine.run_backtest(oos_req)
            result["oos_metrics"] = {k: oos_result.get(k) for k in METRIC_KEYS}
            result["oos_equity"] = oos_result.get("equity", [])
            result["oos_dates"] = oos_result.get("dates", [])
        except Exception as e:
            print(f"[WFA] Window {window_idx} OOS backtest failed: {e}", flush=True)
            result["error"] = f"OOS 백테스트 오류: {str(e)}"

        return result

    def _aggregate(self, windows: List[Dict[str, Any]]) -> Dict[str, float]:
        """OOS 메트릭 평균 집계 (NaN/Infinity는 표본에서 제외)."""
        sums: Dict[str, float] = {k: 0.0 for k in METRIC_KEYS}
        counts: Dict[str, int] = {k: 0 for k in METRIC_KEYS}

        for w in windows:
            oos = w.get("oos_metrics", {})
            for k in METRIC_KEYS:
                val = _finite(oos.get(k))
                if val is not None:
                    sums[k] += val
                    counts[k] += 1

        return {
            f"avg_oos_{k}": round(sums[k] / counts[k], 4) if counts[k] > 0 else 0.0
            for k in METRIC_KEYS
        }

    def _combine_equity(
        self, windows: List[Dict[str, Any]]
    ) -> Tuple[List[float], List[str]]:
        """모든 OOS 구간의 에퀴티 커브를 연결 (체인 방식)."""
        combined_equity: List[float] = []
        combined_dates: List[str] = []
        running_base = 1.0  # normalized to 1

        for w in windows:
            eq = w.get("oos_equity", [])
            dt = w.get("oos_dates", [])
            if not eq or not dt:
                continue

            # Normalize this window's equity to start from running_base
            first_val = eq[0] if eq[0] != 0 else 1.0
            for i, (e, d) in enumerate(zip(eq, dt)):
                norm = e / first_val * running_base
                combined_equity.append(round(norm, 2))
                combined_dates.append(d)

            # Next window starts where this one ended
            if eq:
                running_base = combined_equity[-1]

        return combined_equity, combined_dates
