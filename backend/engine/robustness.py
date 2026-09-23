"""견고성 도구(엔진 v16.30) — 롤링 시작일 백테스트·거래비용 민감도 스윕.

두 도구 모두 같은 전략을 설정만 바꿔 여러 번 돌리고 핵심 지표를 표로 돌려준다(엔진 결과 자체는 그대로).
최적화 세션(Phase1 캐시)을 열어 반복 비용을 줄이며, 값은 과거 데이터의 통계이지 예측·추천이 아니다.

  rolling_start  창 길이를 고정한 채 시작일을 step개월씩 미루며 N번 실행 → 시작 시점에 따른 결과 분포
                 (평균·중앙값·최악·최선·표준편차).
  cost_sweep     수수료 × 슬리피지 격자(각 최대 6단계)로 실행 → 비용 수준별 CAGR·MDD·샤프.
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from engine.grid_optimizer import optimization_session

MAX_ROLLING_RUNS = 24
MAX_COST_LEVELS = 6
METRIC_KEYS = ("totalReturn", "cagr", "maxDrawdown", "sharpe", "profitFactor", "winRate", "trades")


def _metrics(res: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key in METRIC_KEYS:
        v = res.get(key)
        if isinstance(v, (int, float)) and np.isfinite(v):
            out[key] = round(float(v), 6)
        else:
            out[key] = None
    return out


def _summary(rows: List[Dict[str, Any]], key: str) -> Optional[Dict[str, Any]]:
    vals = np.array([r["metrics"][key] for r in rows if r.get("metrics") and r["metrics"].get(key) is not None],
                    dtype=float)
    if len(vals) == 0:
        return None
    return {"mean": round(float(vals.mean()), 6), "median": round(float(np.median(vals)), 6),
            "min": round(float(vals.min()), 6), "max": round(float(vals.max()), 6),
            "std": round(float(vals.std(ddof=1)), 6) if len(vals) > 1 else 0.0, "count": int(len(vals))}


def rolling_start(engine, base_request: Dict[str, Any], *, window_months: int, step_months: int,
                  runs: int, should_cancel: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    runs = max(1, min(int(runs), MAX_ROLLING_RUNS))
    start = pd.Timestamp(base_request.get("startDate") or "2015-01-01")
    end_limit = pd.Timestamp(base_request.get("endDate") or pd.Timestamp.today().normalize())
    rows: List[Dict[str, Any]] = []
    with optimization_session(engine):
        for k in range(runs):
            if should_cancel is not None and should_cancel():
                break
            s = start + pd.DateOffset(months=step_months * k)
            e = s + pd.DateOffset(months=window_months) - pd.Timedelta(days=1)
            if e > end_limit:
                break
            req = copy.deepcopy(base_request)
            req["startDate"] = s.strftime("%Y-%m-%d")
            req["endDate"] = e.strftime("%Y-%m-%d")
            try:
                res = engine.run_backtest(req)
                rows.append({"run": k + 1, "startDate": req["startDate"], "endDate": req["endDate"],
                             "metrics": _metrics(res), "error": None})
            except Exception as exc:  # noqa: BLE001 — 한 창의 실패가 표를 죽이지 않게
                rows.append({"run": k + 1, "startDate": req["startDate"], "endDate": req["endDate"],
                             "metrics": None, "error": str(exc)})
    ok = [r for r in rows if r.get("metrics")]
    return {
        "status": "ok" if ok else "error",
        "message": None if ok else "실행 가능한 창이 없습니다 — 시작일·창 길이·종료일을 확인해 주세요.",
        "windowMonths": window_months, "stepMonths": step_months,
        "runs": rows,
        "summary": {key: _summary(ok, key) for key in ("cagr", "maxDrawdown", "sharpe", "totalReturn")},
        "positiveShare": (round(float(np.mean([r["metrics"]["totalReturn"] > 0 for r in ok
                                                if r["metrics"]["totalReturn"] is not None])) * 100.0, 2)
                          if ok else None),
    }


def cost_sweep(engine, base_request: Dict[str, Any], *, fee_rates_pct: List[float],
               slippage_rates_pct: List[float], should_cancel: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    fees = sorted({float(f) for f in fee_rates_pct})[:MAX_COST_LEVELS]
    slips = sorted({float(s) for s in slippage_rates_pct})[:MAX_COST_LEVELS]
    if not fees or not slips:
        return {"status": "error", "message": "수수료·슬리피지 단계를 하나 이상 지정해 주세요."}
    if any(f < 0 for f in fees) or any(s < 0 for s in slips):
        return {"status": "error", "message": "거래 비용은 음수일 수 없습니다."}
    cells: List[Dict[str, Any]] = []
    with optimization_session(engine):
        for fee in fees:
            for slip in slips:
                if should_cancel is not None and should_cancel():
                    break
                req = copy.deepcopy(base_request)
                opts = dict(req.get("options") or {})
                opts["fee_rate"] = fee / 100.0
                opts["slippage_rate"] = slip / 100.0
                req["options"] = opts
                try:
                    res = engine.run_backtest(req)
                    cells.append({"feePct": fee, "slippagePct": slip, "metrics": _metrics(res), "error": None})
                except Exception as exc:  # noqa: BLE001
                    cells.append({"feePct": fee, "slippagePct": slip, "metrics": None, "error": str(exc)})
    ok = [c for c in cells if c.get("metrics")]
    base = next((c for c in ok if c["feePct"] == min(fees) and c["slippagePct"] == min(slips)), None)
    worst = next((c for c in ok if c["feePct"] == max(fees) and c["slippagePct"] == max(slips)), None)
    return {
        "status": "ok" if ok else "error",
        "message": None if ok else "모든 비용 조합의 백테스트가 실패했습니다.",
        "feeLevels": fees, "slippageLevels": slips, "cells": cells,
        "cagrDrop": (round(float(base["metrics"]["cagr"] - worst["metrics"]["cagr"]), 6)
                     if base and worst and base["metrics"]["cagr"] is not None and worst["metrics"]["cagr"] is not None
                     else None),
    }
