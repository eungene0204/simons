"""결과 심화 분석(엔진 v16.30) — 성과 귀인·팩터 노출·거래 분포·MAE/MFE·VaR/CVaR·롤링 통계·턴오버·유동성·다중 벤치마크.

체결·자산곡선·핵심 지표는 바꾸지 않는다(부가 통계). 모든 값은 과거 데이터의 기술 통계이며 예측·추천이 아니다.
계산 불가(표본 부족·자료 없음)는 null과 사유(`reason`)로 남긴다 — 0으로 위장하지 않는다.

  attribution     종목별·섹터별 손익 기여(초기 자본 대비 %).
  factorExposure  유니버스 안에서 만든 시장·규모(SMB)·가치(HML)·모멘텀(MOM) 팩터 포트폴리오에 대한 OLS 회귀
                  (유니버스 30종목·관측 60일 이상일 때만 — 5종목 전략의 '팩터 노출'은 뜻이 없다).
  tradeDistribution 거래 수익률·보유일 히스토그램, MAE/MFE(진입가 대비 보유 중 최저·최고 도달률).
  riskStats       역사적 VaR/CVaR(95·99%, 일간 %), 63거래일 롤링 샤프·롤링 베타 시계열.
  turnover        기간 회전율(총 체결금액÷2÷평균 자산)과 연환산.
  liquidity       주문금액 ÷ 최근 20거래일 평균 거래대금(참여율) 분포와 참여율 10% 기준 운용 가능 자본 추정.
  benchmarks      지역 표준 벤치마크 3종 대비 수익률·베타·알파·정보비율.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from engine.result_handler import ResultHandler, KRX_TRADING_DAYS_PER_YEAR

ROLLING_WINDOW = 63
RETURN_BINS = [-30, -20, -15, -10, -5, -2, 0, 2, 5, 10, 15, 20, 30]
HOLDING_BINS = [1, 5, 10, 20, 40, 60, 120, 250]
FACTOR_MIN_SYMBOLS = 30
FACTOR_MIN_OBS = 60
FACTOR_QUANTILE = 0.3
LIQUIDITY_PARTICIPATION_CAP = 0.10
ADV_DAYS = 20
MAX_SCATTER_POINTS = 500

BENCHMARK_SETS = {
    "kr": [("069500", "KODEX 200"), ("229200", "KODEX 코스닥150"), ("360750", "TIGER 미국S&P500")],
    "us": [("SPY", "SPY"), ("QQQ", "QQQ"), ("IWM", "IWM")],
}


def _f(v) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(x) or np.isinf(x)) else round(x, 6)


def _series_or_none(arr) -> List[Optional[float]]:
    return [None if (v is None or np.isnan(v) or np.isinf(v)) else round(float(v), 6) for v in np.asarray(arr, dtype=float)]


def _histogram(values: np.ndarray, edges: List[float], unit: str) -> List[Dict[str, Any]]:
    values = values[np.isfinite(values)]
    out = []
    bounds = [-np.inf] + list(edges) + [np.inf]
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        count = int(((values >= lo) & (values < hi)).sum())
        out.append({"from": None if np.isinf(lo) else lo, "to": None if np.isinf(hi) else hi,
                    "count": count, "unit": unit})
    return out


# ── 거래 분포·MAE/MFE ──────────────────────────────────────────────────────────

def trade_distribution(pf, high_values: Optional[np.ndarray], low_values: Optional[np.ndarray]) -> Dict[str, Any]:
    rec = pf.trades.records
    if len(rec) == 0:
        return {"trades": 0, "returnHistogram": [], "holdingHistogram": [], "mae": None, "mfe": None, "points": []}
    rets = np.asarray(rec["return"], dtype=float) * 100.0
    hold = np.asarray(rec["exit_idx"], dtype=int) - np.asarray(rec["entry_idx"], dtype=int)
    mae = np.full(len(rec), np.nan)
    mfe = np.full(len(rec), np.nan)
    if high_values is not None and low_values is not None:
        for k in range(len(rec)):
            e, x, col = int(rec["entry_idx"][k]), int(rec["exit_idx"][k]), int(rec["col"][k])
            entry = float(rec["entry_price"][k])
            if entry <= 0 or x < e:
                continue
            lows = low_values[e:x + 1, col]
            highs = high_values[e:x + 1, col]
            if len(lows) == 0:
                continue
            mae[k] = (np.nanmin(lows) / entry - 1.0) * 100.0
            mfe[k] = (np.nanmax(highs) / entry - 1.0) * 100.0
    wins = rets > 0
    finite_mae = np.isfinite(mae)

    def _stats(arr, mask=None):
        a = arr[(mask if mask is not None else np.ones(len(arr), bool)) & np.isfinite(arr)]
        if len(a) == 0:
            return None
        return {"mean": _f(a.mean()), "median": _f(np.median(a)), "worst": _f(a.min()), "best": _f(a.max()),
                "count": int(len(a))}

    idx = np.arange(len(rec))
    if len(idx) > MAX_SCATTER_POINTS:
        idx = np.linspace(0, len(rec) - 1, MAX_SCATTER_POINTS).astype(int)
    points = [[_f(mae[i]), _f(mfe[i]), _f(rets[i])] for i in idx if finite_mae[i]]
    return {
        "trades": int(len(rec)),
        "returnHistogram": _histogram(rets, RETURN_BINS, "%"),
        "holdingHistogram": _histogram(hold.astype(float), HOLDING_BINS, "days"),
        "holdingDays": {"mean": _f(hold.mean()), "median": _f(np.median(hold)), "max": int(hold.max())},
        "mae": {"all": _stats(mae), "winners": _stats(mae, wins), "losers": _stats(mae, ~wins)},
        "mfe": {"all": _stats(mfe), "winners": _stats(mfe, wins), "losers": _stats(mfe, ~wins)},
        "points": points,
    }


# ── 성과 귀인 ────────────────────────────────────────────────────────────────

def attribution(pf, symbols: List[str], init_cash: float, top_n: int = 10) -> Dict[str, Any]:
    rec = pf.trades.records
    if len(rec) == 0 or init_cash <= 0:
        return {"symbols": [], "sectors": [], "total": 0.0}
    from engine.ksic_sectors import sector_for_symbol
    try:
        from stock_analysis.symbol_resolver import resolve_by_symbol
    except Exception:  # noqa: BLE001
        resolve_by_symbol = None
    pnl_by_col: Dict[int, float] = {}
    trades_by_col: Dict[int, int] = {}
    for k in range(len(rec)):
        col = int(rec["col"][k])
        pnl_by_col[col] = pnl_by_col.get(col, 0.0) + float(rec["pnl"][k])
        trades_by_col[col] = trades_by_col.get(col, 0) + 1
    rows = []
    sectors: Dict[str, Dict[str, float]] = {}
    for col, pnl in pnl_by_col.items():
        sym = symbols[col] if col < len(symbols) else str(col)
        sector = sector_for_symbol(str(sym)) or "미분류"
        name = None
        if resolve_by_symbol is not None:
            try:
                ref = resolve_by_symbol(sym)
                name = ref.name if ref else None
            except Exception:  # noqa: BLE001
                name = None
        rows.append({"symbol": sym, "name": name or sym, "sector": sector, "pnl": _f(pnl),
                     "contributionPct": _f(pnl / init_cash * 100.0), "trades": trades_by_col[col]})
        s = sectors.setdefault(sector, {"pnl": 0.0, "symbols": 0, "trades": 0})
        s["pnl"] += pnl
        s["symbols"] += 1
        s["trades"] += trades_by_col[col]
    rows.sort(key=lambda r: -abs(r["pnl"] or 0.0))
    total = sum(pnl_by_col.values())
    sector_rows = [{"sector": k, "pnl": _f(v["pnl"]), "contributionPct": _f(v["pnl"] / init_cash * 100.0),
                    "symbols": v["symbols"], "trades": v["trades"]} for k, v in sectors.items()]
    sector_rows.sort(key=lambda r: -abs(r["pnl"] or 0.0))
    return {"symbols": rows[:top_n], "sectors": sector_rows, "total": _f(total),
            "totalContributionPct": _f(total / init_cash * 100.0), "symbolCount": len(rows)}


# ── 위험 통계 ────────────────────────────────────────────────────────────────

def risk_stats(daily_rets: np.ndarray, bench_rets: Optional[pd.Series], index: pd.Index,
               periods_per_year: float) -> Dict[str, Any]:
    r = np.asarray(daily_rets, dtype=float)
    r = np.where(np.isfinite(r), r, np.nan)
    finite = r[np.isfinite(r)]
    out: Dict[str, Any] = {"var95": None, "cvar95": None, "var99": None, "cvar99": None,
                           "rollingSharpe": [], "rollingBeta": [], "window": ROLLING_WINDOW}
    if len(finite) >= 20:
        for level in (95, 99):
            q = float(np.percentile(finite, 100 - level))
            tail = finite[finite <= q]
            out[f"var{level}"] = _f(-q * 100.0)
            out[f"cvar{level}"] = _f(-float(tail.mean()) * 100.0) if len(tail) else None
    s = pd.Series(r, index=index)
    roll_mean = s.rolling(ROLLING_WINDOW).mean()
    roll_std = s.rolling(ROLLING_WINDOW).std(ddof=1)
    sharpe = (roll_mean / roll_std) * np.sqrt(periods_per_year)
    sharpe = sharpe.where(roll_std > 0)
    out["rollingSharpe"] = _series_or_none(sharpe.values)
    if bench_rets is not None:
        b = pd.Series(bench_rets, index=index) if not isinstance(bench_rets, pd.Series) else bench_rets.reindex(index)
        cov = s.rolling(ROLLING_WINDOW).cov(b)
        var = b.rolling(ROLLING_WINDOW).var(ddof=1)
        beta = (cov / var).where(var > 0)
        out["rollingBeta"] = _series_or_none(beta.values)
    return out


# ── 턴오버·유동성 ────────────────────────────────────────────────────────────

def turnover_stats(pf, val: pd.Series, n_years: float) -> Dict[str, Any]:
    from engine.rebalance_comparison import _turnover_pct
    total = float(_turnover_pct(pf, val))
    annual = total / n_years if n_years > 0 else total
    return {"total": _f(total), "annual": _f(annual)}


def liquidity_stats(pf, trading_values: Optional[pd.DataFrame], init_cash: float) -> Dict[str, Any]:
    empty = {"orders": 0, "maxParticipation": None, "meanParticipation": None, "p95Participation": None,
             "shareAboveCap": None, "capitalAtCap": None, "cap": LIQUIDITY_PARTICIPATION_CAP * 100}
    if trading_values is None or trading_values.empty:
        return {**empty, "reason": "no_trading_value"}
    rec = pf.orders.records_arr
    if len(rec) == 0:
        return empty
    adv = trading_values.astype(float).rolling(ADV_DAYS, min_periods=1).mean().shift(1).values
    idx, col = rec["idx"].astype(int), rec["col"].astype(int)
    value = np.abs(rec["size"].astype(float) * rec["price"].astype(float))
    denom = adv[idx, col]
    with np.errstate(divide="ignore", invalid="ignore"):
        part = np.where(denom > 0, value / denom, np.nan)
    part = part[np.isfinite(part)]
    if len(part) == 0:
        return {**empty, "orders": int(len(rec)), "reason": "no_adv"}
    max_p = float(part.max())
    return {
        "orders": int(len(rec)),
        "maxParticipation": _f(max_p * 100.0),
        "meanParticipation": _f(part.mean() * 100.0),
        "p95Participation": _f(np.percentile(part, 95) * 100.0),
        "shareAboveCap": _f((part > LIQUIDITY_PARTICIPATION_CAP).mean() * 100.0),
        "capitalAtCap": _f(init_cash * LIQUIDITY_PARTICIPATION_CAP / max_p) if max_p > 0 else None,
        "cap": LIQUIDITY_PARTICIPATION_CAP * 100,
    }


# ── 팩터 노출(유니버스 내 팩터 포트폴리오 회귀) ───────────────────────────────

def _month_starts(index: pd.DatetimeIndex) -> np.ndarray:
    months = index.to_period("M")
    return np.r_[True, months[1:] != months[:-1]]


def _long_short(returns: pd.DataFrame, score: pd.DataFrame, starts: np.ndarray,
                high_is_long: bool, q: float = FACTOR_QUANTILE) -> pd.Series:
    """월초에 직전 거래일 점수로 상위/하위 q 구간을 잡고 그 달의 일별 (롱 − 숏) 균등 수익률."""
    out = pd.Series(np.nan, index=returns.index)
    long_set = short_set = None
    for i, day in enumerate(returns.index):
        if starts[i] and i > 0:
            s = score.iloc[i - 1].dropna()
            if len(s) >= 10:
                n = max(1, int(len(s) * q))
                ranked = s.sort_values()
                lo, hi = list(ranked.index[:n]), list(ranked.index[-n:])
                long_set, short_set = (hi, lo) if high_is_long else (lo, hi)
        if long_set:
            row = returns.iloc[i]
            out.iloc[i] = float(row[long_set].mean() - row[short_set].mean())
    return out


def factor_exposure(strat_rets: pd.Series, bench_rets: Optional[pd.Series], prices: pd.DataFrame,
                    market_caps: Optional[pd.DataFrame], pbr: Optional[pd.DataFrame],
                    momentum: Optional[pd.DataFrame], periods_per_year: float,
                    risk_free_rate: float = 0.0) -> Dict[str, Any]:
    n_syms = int(prices.shape[1]) if prices is not None else 0
    if prices is None or n_syms < FACTOR_MIN_SYMBOLS:
        return {"available": False, "reason": "universe_too_small", "symbols": n_syms,
                "minSymbols": FACTOR_MIN_SYMBOLS}
    returns = prices.astype(float).pct_change()
    index = pd.DatetimeIndex(returns.index)
    starts = _month_starts(index)
    factors: Dict[str, pd.Series] = {}
    if bench_rets is not None:
        factors["MKT"] = pd.Series(bench_rets, index=index) if not isinstance(bench_rets, pd.Series) \
            else bench_rets.reindex(index)
    if market_caps is not None and market_caps.notna().sum().sum() > 0:
        factors["SMB"] = _long_short(returns, market_caps.astype(float), starts, high_is_long=False)
    if pbr is not None and pbr.notna().sum().sum() > 0:
        factors["HML"] = _long_short(returns, pbr.astype(float).where(pbr > 0), starts, high_is_long=False)
    if momentum is not None and momentum.notna().sum().sum() > 0:
        factors["MOM"] = _long_short(returns, momentum.astype(float), starts, high_is_long=True)
    if not factors:
        return {"available": False, "reason": "no_factor_data", "symbols": n_syms}
    rf_daily = ((1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0) if risk_free_rate else 0.0
    df = pd.DataFrame(factors)
    df["y"] = pd.Series(strat_rets, index=index) - rf_daily
    if "MKT" in df:
        df["MKT"] = df["MKT"] - rf_daily
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    names = [c for c in df.columns if c != "y"]
    if len(df) < FACTOR_MIN_OBS or not names:
        return {"available": False, "reason": "too_few_observations", "observations": int(len(df)),
                "symbols": n_syms}
    x = np.column_stack([np.ones(len(df))] + [df[c].values for c in names])
    y = df["y"].values
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    dof = len(y) - x.shape[1]
    sigma2 = float(resid @ resid) / dof if dof > 0 else np.nan
    try:
        cov = sigma2 * np.linalg.inv(x.T @ x)
        se = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        se = np.full(len(beta), np.nan)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else None
    loadings = []
    for k, name in enumerate(names):
        loadings.append({"factor": name, "beta": _f(beta[k + 1]),
                         "tStat": _f(beta[k + 1] / se[k + 1]) if se[k + 1] > 0 else None})
    return {
        "available": True, "symbols": n_syms, "observations": int(len(df)),
        "alphaAnnualPct": _f(beta[0] * periods_per_year * 100.0),
        "alphaTStat": _f(beta[0] / se[0]) if se[0] > 0 else None,
        "r2": _f(r2), "loadings": loadings,
        "note": "universe_factors",
    }


# ── 다중 벤치마크 ────────────────────────────────────────────────────────────

def benchmark_comparisons(loader, region: str, common_index: pd.Index, strat_rets_raw, init_cash: float,
                          apply_dividends: bool, risk_free_rate: float, periods_per_year: float,
                          n_years: float) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    from engine import universe_pit
    for sym, name in BENCHMARK_SETS.get(region, []):
        try:
            df = loader.load_symbol_data(sym)
            if df is None or len(df) == 0:
                continue
            pdf = loader.preprocess_data(df, apply_dividends=apply_dividends,
                                         sanitize_corporate_actions=not universe_pit.is_us_symbol(sym))
            prices = pdf["close"].sort_index()
        except Exception:  # noqa: BLE001
            continue
        bench_rets, valid = ResultHandler.benchmark_daily_returns(prices, common_index)
        if bench_rets is None:
            continue
        cum = (1.0 + bench_rets).cumprod()
        cum = cum.where(valid, np.nan) if valid is not None else cum
        covered = cum.dropna()
        if len(covered) < 2:
            continue
        total = float(covered.iloc[-1] - 1.0) * 100.0
        peak = covered.cummax()
        mdd = float(((covered / peak) - 1.0).min()) * 100.0
        rel = ResultHandler.benchmark_relative_stats(strat_rets_raw, bench_rets, valid, risk_free_rate, periods_per_year)
        rows.append({
            "symbol": sym, "name": name,
            "totalReturn": _f(total),
            "cagr": _f(ResultHandler.annualize_return(total / 100.0, n_years)),
            "maxDrawdown": _f(mdd),
            "partial": bool(valid is not None and not bool(valid.all())),
            "beta": _f(rel["beta"]), "alpha": _f(rel["alpha"]),
            "trackingError": _f(rel["trackingError"]), "informationRatio": _f(rel["informationRatio"]),
        })
    return rows


# ── 조립 ─────────────────────────────────────────────────────────────────────

def build_analytics(*, pf, symbols: List[str], common_index: pd.Index, init_cash: float,
                    high_values: Optional[np.ndarray], low_values: Optional[np.ndarray],
                    trading_values: Optional[pd.DataFrame], market_caps: Optional[pd.DataFrame],
                    pbr: Optional[pd.DataFrame], prices: Optional[pd.DataFrame],
                    momentum: Optional[pd.DataFrame], benchmark_prices: Optional[pd.Series],
                    loader, region: str, apply_dividends: bool, risk_free_rate: float = 0.0) -> Dict[str, Any]:
    n_years, periods_per_year = ResultHandler.time_base(common_index)
    val = pf.value()
    if isinstance(val, pd.DataFrame):
        val = val.sum(axis=1)
    equity = np.asarray(val.values, dtype=float)
    daily = ResultHandler.anchored_returns(equity, init_cash) if len(equity) else np.array([])
    # anchored_returns는 초기자본→첫 평가액 수익률을 포함해 길이가 n이다(결과 지표와 같은 규약).
    strat_series = pd.Series(daily[-len(common_index):] if len(daily) >= len(common_index) else daily,
                             index=common_index[-len(daily):] if len(daily) else common_index[:0])
    bench_rets, bench_valid = ResultHandler.benchmark_daily_returns(benchmark_prices, common_index)
    bench_series = None
    if bench_rets is not None:
        bench_series = pd.Series(bench_rets, index=common_index)
        if bench_valid is not None:
            bench_series = bench_series.where(pd.Series(bench_valid, index=common_index).astype(bool))
    strat_rets_raw = pf.returns(group_by=True)
    return {
        "attribution": attribution(pf, symbols, init_cash),
        "factorExposure": factor_exposure(strat_series, bench_series, prices, market_caps, pbr, momentum,
                                         periods_per_year, risk_free_rate),
        "tradeDistribution": trade_distribution(pf, high_values, low_values),
        "riskStats": risk_stats(strat_series.values, bench_series, common_index, periods_per_year),
        "turnover": turnover_stats(pf, val, n_years),
        "liquidity": liquidity_stats(pf, trading_values, init_cash),
        "benchmarks": benchmark_comparisons(loader, region, common_index, strat_rets_raw, init_cash,
                                            apply_dividends, risk_free_rate, periods_per_year, n_years),
    }
