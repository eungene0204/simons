"""엔진 결과 → 공개 요약 DTO(docs/development/strategy-simulation.md §3.3~§3.6, §4.3).

엔진이 낸 값을 고르고 잘라 낼 뿐 재계산하지 않는다. 엔진 값끼리 어긋나면(총 수익률·종목 합계)
가짜 값을 만들지 않고 실패로 돌려준다. 순수 함수 — 엔진·DB·네트워크를 부르지 않는다.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from engine.contributions import contribution_settings, withdrawal_settings
from engine.universe_pit import is_us_symbol, us_universe_kind
from public_simulation.window import SimulationWindow, WindowError, actual_period

AI_SIGNAL_IDS = ("ai_model", "ai_drop_model")
RETURN_TOLERANCE_PP = 0.01
CONTRIBUTOR_LIMIT = 3


class SimulationResultError(Exception):
    """엔진 결과를 공개 요약으로 만들 수 없음 — 호출자는 이를 failed 상태로 다룬다(0%·거래 없음 금지)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _has_ai_signal(group: Any) -> bool:
    for cond in (group or {}).get("conditions", []) if isinstance(group, dict) else []:
        if not isinstance(cond, dict):
            continue
        if cond.get("id") in AI_SIGNAL_IDS or _has_ai_signal(cond):
            return True
    return False


def check_executable(snapshot: Any) -> Optional[Dict[str, Any]]:
    """실행 가능하면 None, 아니면 {"reason": 코드, "detail": [...]} (명세 §3.3 판정 순서)."""
    if not isinstance(snapshot, dict):
        return {"reason": "NO_EXECUTABLE_SNAPSHOT", "detail": []}
    entry, exit_, risk = snapshot.get("entry"), snapshot.get("exit"), snapshot.get("risk")
    symbols = snapshot.get("symbols")
    has_universe = bool(snapshot.get("universe_id")) or (isinstance(symbols, list) and len(symbols) > 0)
    if not (isinstance(entry, dict) and isinstance(exit_, dict) and isinstance(risk, dict) and has_universe):
        return {"reason": "NO_EXECUTABLE_SNAPSHOT", "detail": []}

    options = snapshot.get("options") if isinstance(snapshot.get("options"), dict) else {}
    missing = []
    if _num(risk.get("init_cash")) is None or risk["init_cash"] <= 0:
        missing.append("risk.init_cash")
    for key in ("fee_rate", "slippage_rate"):
        if _num(options.get(key)) is None:
            missing.append(f"options.{key}")
    if missing:
        return {"reason": "MISSING_RUN_CONDITION", "detail": missing}

    try:
        cash_flow = contribution_settings(risk) is not None or withdrawal_settings(risk) is not None
    except ValueError:
        return {"reason": "INVALID_SNAPSHOT", "detail": ["risk.contribution/withdrawal"]}
    if cash_flow:
        return {"reason": "UNSUPPORTED_CONTRIBUTIONS", "detail": []}
    if us_universe_kind(snapshot.get("universe_id")) or any(
        is_us_symbol(str(s)) for s in (symbols if isinstance(symbols, list) else [])
    ):
        return {"reason": "UNSUPPORTED_REGION", "detail": []}
    if _has_ai_signal(entry) or _has_ai_signal(exit_):
        return {"reason": "UNSUPPORTED_AI_SIGNAL", "detail": []}
    return None


def _return_pct(equity: float, initial: float) -> float:
    return (equity / initial - 1.0) * 100.0


def summarize(result: Dict[str, Any]) -> Dict[str, Any]:
    equity, dates = result.get("equity"), result.get("dates")
    initial = _num(result.get("initialCapital"))
    if not equity or not dates or len(equity) != len(dates) or initial is None or initial <= 0:
        raise SimulationResultError("EMPTY_RESULT", "엔진 결과에 수익 곡선이 없습니다.")
    final = _num(equity[-1])
    total_return, mdd = _num(result.get("totalReturn")), _num(result.get("maxDrawdown"))
    if final is None or total_return is None or mdd is None:
        raise SimulationResultError("INCONSISTENT_RESULT", "엔진 결과 값이 올바르지 않습니다.")
    if abs(_return_pct(final, initial) - total_return) > RETURN_TOLERANCE_PP:
        raise SimulationResultError("INCONSISTENT_RESULT", "누적 수익률이 평가자산과 맞지 않습니다.")

    reasons: Dict[str, str] = {}
    trades = int(result.get("trades") or 0)
    days = (datetime.fromisoformat(dates[-1][:10]) - datetime.fromisoformat(dates[0][:10])).days
    cagr = _num(result.get("cagr")) if days >= 365 else None
    if cagr is None:
        reasons["cagrPct"] = "기간이 1년 미만이라 연환산하지 않습니다."
    sharpe = _num(result.get("sharpe"))
    if sharpe is None or not _num(result.get("volatility")):
        sharpe = None
        reasons["sharpe"] = "수익률 변동이 없어 계산할 수 없습니다."
    win_rate = _num(result.get("winRate")) if trades > 0 else None
    if win_rate is None:
        reasons["winRatePct"] = "거래가 없습니다."
    return {
        "initialCapital": initial,
        "finalEquity": final,
        "totalProfit": final - initial,
        "totalReturnPct": total_return,
        "maxDrawdownPct": mdd,
        "cagrPct": cagr,
        "sharpe": sharpe,
        "winRatePct": win_rate,
        "trades": trades,
        "unavailableReasons": reasons,
    }


def contributors(
    result: Dict[str, Any], total_profit: float, name_lookup: Optional[Callable[[str], Optional[str]]] = None
) -> Dict[str, Any]:
    """손익 기여 상·하위 3종목. 종목 합계가 총 손익과 어긋나면 표시하지 않는다(hidden)."""
    rows = []
    for symbol, stat in (result.get("perAssetStats") or {}).items():
        profit = _num((stat or {}).get("profit"))
        if profit is None:
            return {"top": [], "bottom": [], "hidden": "INCONSISTENT"}
        if int((stat or {}).get("trades") or 0) > 0 or profit != 0:
            rows.append((str(symbol), profit))
    if abs(sum(p for _, p in rows) - total_profit) > max(1.0, abs(total_profit) * 1e-4):
        return {"top": [], "bottom": [], "hidden": "INCONSISTENT"}

    def row(item):
        symbol, profit = item
        return {"symbol": symbol, "name": (name_lookup(symbol) if name_lookup else None) or symbol, "profit": profit}

    gains = sorted((r for r in rows if r[1] > 0), key=lambda r: (-r[1], r[0]))
    losses = sorted((r for r in rows if r[1] < 0), key=lambda r: (r[1], r[0]))
    return {"top": [row(r) for r in gains[:CONTRIBUTOR_LIMIT]], "bottom": [row(r) for r in losses[:CONTRIBUTOR_LIMIT]]}


def downsample(curve: Dict[str, List[Any]], max_points: int) -> Dict[str, List[Any]]:
    """카드 미니 그래프용 — 첫·마지막 점을 포함해 등간격으로 줄인다."""
    n = len(curve["dates"])
    if max_points < 2 or n <= max_points:
        return curve
    idx = sorted({round(i * (n - 1) / (max_points - 1)) for i in range(max_points)})
    return {"dates": [curve["dates"][i] for i in idx], "returnPct": [curve["returnPct"][i] for i in idx]}


def build_public_result(
    result: Dict[str, Any],
    snapshot: Dict[str, Any],
    window: SimulationWindow,
    *,
    name_lookup: Optional[Callable[[str], Optional[str]]] = None,
    computed_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """공개 DTO. 실패는 SimulationResultError/WindowError — 호출자가 failed로 기록한다."""
    summary = summarize(result)
    costs = result.get("tradingCosts")
    if not isinstance(costs, dict):
        raise SimulationResultError("MISSING_TRADING_COSTS", "적용된 거래 비용 정보가 없습니다.")
    dates = [str(d)[:10] for d in result["dates"]]
    initial = summary["initialCapital"]
    risk = snapshot.get("risk") or {}
    return {
        "status": "no_trades" if summary["trades"] == 0 else "ready",
        "window": actual_period(window, dates[0], dates[-1]),
        "computedAt": (computed_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
        "conditions": {
            "initialCapital": initial,
            "buyFeeRate": costs.get("buyFeeRate"),
            "sellFeeRate": costs.get("sellFeeRate"),
            "slippageRate": costs.get("slippageRate"),
            "sellTaxRate": costs.get("sellTaxRate"),
            "sellTaxRateRange": costs.get("sellTaxRateRange"),
            "executionTiming": risk.get("execution_timing"),
            "executionDelayDays": risk.get("execution_delay_days"),
            "savedPeriod": snapshot.get("period"),
        },
        "summary": summary,
        "curve": {
            "dates": dates,
            "returnPct": [round(_return_pct(float(e), initial), 4) for e in result["equity"]],
        },
        "contributors": contributors(result, summary["totalProfit"], name_lookup),
        "engineVersion": result.get("version"),
    }


__all__ = [
    "SimulationResultError", "WindowError", "check_executable", "summarize", "contributors",
    "downsample", "build_public_result",
]
