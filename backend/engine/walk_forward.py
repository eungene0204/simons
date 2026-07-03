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
from typing import Dict, Any, List, Tuple, Optional
from engine.grid_optimizer import set_nested_value


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
        # 1. 전체 날짜 범위 획득
        dates = self._get_full_dates(base_request)
        if not dates:
            return {"status": "error", "message": "데이터를 불러올 수 없습니다."}

        if len(dates) < 60:
            return {"status": "error", "message": f"데이터가 너무 짧습니다: {len(dates)}일"}

        # 2. 윈도우 분할
        windows = self._split_windows(dates, n_splits, train_pct, anchor)
        if not windows:
            return {"status": "error", "message": "윈도우 분할에 실패했습니다. 기간을 늘려보세요."}

        print(f"[WFA] {len(windows)} windows, total={len(dates)} days", flush=True)

        # 3. 각 윈도우 실행
        window_results = []
        is_returns = []
        oos_returns = []

        for i, (is_start, is_end, oos_start, oos_end) in enumerate(windows):
            print(f"[WFA] Window {i+1}/{len(windows)}: IS={is_start}~{is_end}, OOS={oos_start}~{oos_end}", flush=True)

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
            )
            window_results.append(w_result)

            if w_result.get("is_metrics"):
                is_returns.append(w_result["is_metrics"].get("totalReturn", 0) or 0)
            if w_result.get("oos_metrics"):
                oos_returns.append(w_result["oos_metrics"].get("totalReturn", 0) or 0)

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

    def _get_full_dates(self, base_request: Dict[str, Any]) -> List[str]:
        """전체 기간 백테스트를 실행해 날짜 목록을 반환."""
        try:
            req = copy.deepcopy(base_request)
            req["period"] = "full"
            req.pop("startDate", None)
            req.pop("endDate", None)
            result = self.engine.run_backtest(req)
            return result.get("dates", [])
        except Exception as e:
            print(f"[WFA] _get_full_dates failed: {e}", flush=True)
            return []

    def _split_windows(
        self,
        dates: List[str],
        n_splits: int,
        train_pct: float,
        anchor: bool,
    ) -> List[Tuple[str, str, str, str]]:
        """
        (is_start, is_end, oos_start, oos_end) 튜플 리스트 반환.

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
    ) -> Dict[str, Any]:
        """단일 윈도우: IS 최적화 → OOS 검증."""
        from engine.optuna_optimizer import OptunaOptimizer

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

        optimizer = OptunaOptimizer(self.engine)
        try:
            opt_result = optimizer.optimize(
                base_request=is_req,
                ranges=ranges,
                target_metric=target_metric,
                n_trials=n_trials,
            )
            if opt_result.get("status") == "error":
                result["error"] = opt_result.get("message", "IS 최적화 실패")
                return result

            best_params = opt_result.get("best_parameters", {})
            best_is_metrics = opt_result.get("best_metrics", {})
            result["best_params"] = best_params
            result["is_metrics"] = {
                "cagr": best_is_metrics.get("cagr"),
                "totalReturn": best_is_metrics.get("totalReturn"),
                "maxDrawdown": best_is_metrics.get("maxDrawdown"),
                "sharpe": best_is_metrics.get("sharpe"),
                "winRate": best_is_metrics.get("winRate"),
                "profitFactor": best_is_metrics.get("profitFactor"),
                "trades": best_is_metrics.get("trades"),
            }
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
            result["oos_metrics"] = {
                "cagr": oos_result.get("cagr"),
                "totalReturn": oos_result.get("totalReturn"),
                "maxDrawdown": oos_result.get("maxDrawdown"),
                "sharpe": oos_result.get("sharpe"),
                "winRate": oos_result.get("winRate"),
                "profitFactor": oos_result.get("profitFactor"),
                "trades": oos_result.get("trades"),
            }
            result["oos_equity"] = oos_result.get("equity", [])
            result["oos_dates"] = oos_result.get("dates", [])
        except Exception as e:
            print(f"[WFA] Window {window_idx} OOS backtest failed: {e}", flush=True)
            result["error"] = f"OOS 백테스트 오류: {str(e)}"

        return result

    def _aggregate(self, windows: List[Dict[str, Any]]) -> Dict[str, float]:
        """OOS 메트릭 평균 집계."""
        metrics_keys = ["cagr", "totalReturn", "maxDrawdown", "sharpe", "winRate", "profitFactor", "trades"]
        sums: Dict[str, float] = {k: 0.0 for k in metrics_keys}
        counts: Dict[str, int] = {k: 0 for k in metrics_keys}

        for w in windows:
            oos = w.get("oos_metrics", {})
            for k in metrics_keys:
                val = oos.get(k)
                if val is not None:
                    sums[k] += float(val)
                    counts[k] += 1

        return {
            f"avg_oos_{k}": round(sums[k] / counts[k], 4) if counts[k] > 0 else 0.0
            for k in metrics_keys
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
