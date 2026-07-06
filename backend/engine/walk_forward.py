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
from typing import Any, Callable, Dict, List, Optional, Tuple
from engine.grid_optimizer import set_nested_value

# 윈도우 하나마다 IS 최적화(수십 회 백테스트)가 반복되므로 폭주 방지 상한.
MAX_WINDOWS = 24

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

        Returns:
          {
            status, n_splits, anchor, target_metric,
            windows: [{ window, is_period, oos_period, best_params,
                        is_metrics, oos_metrics, oos_equity, oos_dates }],
            aggregate: { avg_oos_cagr, avg_oos_mdd, avg_oos_sharpe,
                         avg_oos_win_rate, avg_oos_trades },
            combined_equity, combined_dates,
            walk_forward_efficiency,
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

        # 3. 각 윈도우 실행
        window_results = []
        is_returns = []
        oos_returns = []

        for i, (is_start, is_end, oos_start, oos_end) in enumerate(windows):
            # 협조적 취소: 창 경계에서만 확인 (창 내부 최적화는 중단 불가)
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
            )
            window_results.append(w_result)

            is_ret = _finite(w_result.get("is_metrics", {}).get("totalReturn"))
            if is_ret is not None:
                is_returns.append(is_ret)
            oos_ret = _finite(w_result.get("oos_metrics", {}).get("totalReturn"))
            if oos_ret is not None:
                oos_returns.append(oos_ret)

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

        # Walk-Forward Efficiency (WFE) = avg OOS return / avg IS return.
        # IS 평균이 0 이하이면 비율의 부호가 뒤집혀 해석 불능이므로(감사 M9)
        # wfe_valid=False로 표시하고 0을 반환한다.
        avg_is = sum(is_returns) / len(is_returns) if is_returns else 0
        avg_oos = sum(oos_returns) / len(oos_returns) if oos_returns else 0
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
        }

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
                is_e = is_size
                while is_e < T:
                    oos_s = is_e
                    oos_e = min(oos_s + oos_size, T)
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
    ) -> Dict[str, Any]:
        """단일 윈도우: IS 최적화 → OOS 검증."""
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
                )
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
