"""리밸런싱 기간별 결과 비교 (FR-BT-064) — 백테스트에 동봉되는 6주기 재시뮬레이션.

메인 백테스트가 끝난 뒤, 이미 준비된 시뮬레이터 입력(가격·신호·랭킹·거래가능 마스크)을
그대로 두고 `rebalancing_period`만 매일·매주·매월·분기·반기·연간으로 바꿔 시뮬레이션을
6번 반복한다(분위 그룹 비교 FR-BT-060과 같은 구조 — 1단계 데이터 준비는 다시 하지 않는다).
결과는 BacktestResponse.rebalanceComparison으로 실려 결과 화면의 '리밸런싱 기간별 결과'
탭이 별도 실행 없이 바로 보여준다(2026-08-18 사용자 지시 — 실행 버튼·AI 서술 없이 백테스트와
함께 계산해 표시).

수치는 전부 결정론이며, 회전율은 결과 화면(BacktestDashboard.calculateTurnoverRate)과 같은
산식(총 체결금액 ÷ 2 ÷ 기간 평균 자산 × 100)이라 메인 결과와 같은 잣대다.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from engine.result_handler import ResultHandler

# 비교 대상 6주기 — 짧은 주기 → 긴 주기 순.
REBALANCE_PERIODS: tuple[str, ...] = ("daily", "weekly", "monthly", "quarterly", "semiannual", "yearly")


def _finite(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _round(value: Optional[float], nd: int = 2) -> Optional[float]:
    return None if value is None else round(value, nd)


def rebalance_applies(risk_params: Dict[str, Any]) -> bool:
    """리밸런싱 주기가 결과에 영향을 주는 전략인가(시뮬레이터의 rebalance_mode 조건과 동일).

    보유 상한(max_positions)·비율 선정(max_positions_pct)·분위 그룹이 없거나 포지션 설정을
    건너뛰는 전략은 주기를 바꿔도 6번 모두 같은 결과가 나온다 — 막지 않고 계산하되 화면이
    그 사실을 안내할 수 있게 플래그로 알린다.
    """
    if risk_params.get("skip_position_setting"):
        return False
    return bool(
        risk_params.get("max_positions") or risk_params.get("max_positions_pct")
        or risk_params.get("ranking_quantile_groups") or risk_params.get("ranking_band")
    )


def _portfolio_value(pf) -> pd.Series:
    val = pf.value()
    if isinstance(val, pd.DataFrame):
        val = val.sum(axis=1)
    return val


def _turnover_pct(pf, val: pd.Series) -> float:
    """회전율(%) = (총 매수·매도 체결금액 / 2) / 기간 평균 자산 × 100."""
    valid = val[np.isfinite(val.values) & (val.values > 0)] if len(val) else val
    if len(valid) == 0:
        return 0.0
    try:
        orders = pf.orders.records_readable
        traded = float((orders["Size"].astype(float) * orders["Price"].astype(float)).abs().sum()) if len(orders) else 0.0
    except Exception:
        traded = 0.0
    average_assets = float(valid.mean())
    return (traded / 2.0 / average_assets) * 100.0 if average_assets > 0 else 0.0


def summarize_portfolio(pf, init_cash: float) -> Dict[str, Any]:
    """포트폴리오 1개의 비교표 한 행(결정론). 메인 결과와 같은 연환산·손익비 규약을 쓴다."""
    val = _portfolio_value(pf)
    n = len(val)
    final_eq = float(val.iloc[-1]) if n else init_cash
    total_return = (final_eq / init_cash - 1.0) * 100.0 if init_cash > 0 else 0.0
    years, ppy = ResultHandler.time_base(val.index)
    cagr = ResultHandler.annualize_return(total_return / 100.0, years)
    dd = (val / val.cummax() - 1.0) if n else None
    mdd = float(dd.min() * 100.0) if dd is not None and len(dd) else 0.0
    rets = val.pct_change().dropna() if n else None
    sharpe = (
        float(rets.mean() / rets.std(ddof=1) * np.sqrt(ppy))
        if rets is not None and len(rets) > 1 and float(rets.std(ddof=1)) > 0 else 0.0
    )
    trades = int(pf.trades.count())
    try:
        win_rate = float(pf.trades.win_rate() * 100.0) if trades else 0.0
    except Exception:
        win_rate = 0.0
    profit_factor = ResultHandler._profit_factor(pf, trades)  # None = 손실 0건(∞)
    return {
        "cagr": _round(_finite(cagr)),
        "mdd": _round(_finite(mdd)),
        "sharpe": _round(_finite(sharpe)),
        "profitFactor": _round(_finite(profit_factor)) if profit_factor is not None else None,
        "trades": trades,
        "turnover": _round(_finite(_turnover_pct(pf, val))),
        "totalReturn": _round(_finite(total_return)),
        "winRate": _round(_finite(win_rate)),
        "finalEquity": _round(_finite(final_eq)),
    }


def run_rebalance_period_comparison(
    run_simulation: Callable[[Dict[str, Any]], Any],
    risk_params: Dict[str, Any],
    init_cash: float,
    *,
    summarize: Callable[[Any, float], Dict[str, Any]] = summarize_portfolio,
    periods: tuple[str, ...] = REBALANCE_PERIODS,
) -> Dict[str, Any]:
    """`rebalancing_period`만 바꿔 시뮬레이션을 반복한다.

    run_simulation(risk_params) → vbt Portfolio. 한 주기의 실패는 그 행만 error로 남기고 계속한다.
    """
    rows: List[Dict[str, Any]] = []
    for period in periods:
        rp = dict(risk_params)
        rp["rebalancing_period"] = period
        try:
            pf = run_simulation(rp)
            row = {"period": period, **summarize(pf, init_cash), "error": None}
        except Exception as exc:  # noqa: BLE001 — 한 주기 실패가 메인 결과·다른 주기를 죽이지 않게
            row = {"period": period, "error": str(exc)}
        rows.append(row)
    return {
        "periods": rows,
        "currentPeriod": str(risk_params.get("rebalancing_period") or "none"),
        # 보유 상한이 없어 주기가 결과에 영향을 주지 않는 전략 — 화면이 "6행이 같을 수 있음"을 안내한다.
        "positionCapAbsent": not rebalance_applies(risk_params),
    }
