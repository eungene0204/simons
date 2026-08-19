"""Phase1 — 종목 하나의 준비 계산(로드 → 워밍업 절단 → 지표 → 리졸버 → 기간 필터 → 전처리 → 유동성 → 신호).

BacktestEngine.run_backtest의 종목별 파이프라인을 **순수 함수**로 뽑아낸 것이다. 입력은
피클 가능한 컨텍스트 dict(``ctx``) + 엔진 구성요소(loader/indicator/signal)뿐이라
스레드 풀(엔진 안)에서도, 프로세스 워커(engine/phase1_pool.py)에서도 같은 코드가 돈다.
부수효과(경고·리졸버 로그·AI Phase2 대기 데이터)는 반환값에 담고 호출부가 낸다 —
캐시 적중·프로세스 경계를 넘어도 같은 결과가 나야 한다.

반환 규약 (``process_symbol``):
  (status, data, side)
    status: 'skip' | 'warning' | 'success' | 'phase1_done'
    data:   None | 경고 문자열 | 결과 패키지 dict | {'df_pl', 'pdf_for_ai'}(AI)
    side:   {'warnings': [..], 'res_logs': [..]}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import polars as pl

from engine import data_coverage
from engine.data_resolver import DataResolver
from engine.prep_cache import SymbolPrepCache, structural_signature


def date_key() -> pl.Expr:
    """백테스트 창 비교용 날짜 키(YYYY-MM-DD) — **날짜 부분만** 본다.

    타임스탬프를 통째로 문자열화해 비교하면 종료 경계가 배타적이 된다:
    `"2024-12-30 00:00:00.000000" <= "2024-12-30"` 은 거짓이다(접두가 같고 더 긴 쪽이
    크다). 그래서 **명시 종료일 당일 봉이 매번 통째로 빠졌다** — 삼성전자 실측:
    endDate=2024-12-30으로 요청하면 마지막 봉이 2024-12-27이었다(12-30 봉은 존재).
    시작 경계는 같은 규칙이 우연히 맞는 방향이라(더 긴 쪽이 크므로 `>=` 통과) 끝에서만
    하루가 사라지는 비대칭이었고, 종료일이 휴장일이면 증상이 가려져 오래 남았다.

    잘라내는 방식을 쓰는 이유는 `date` 컬럼 타입이 파일마다 갈리기 때문이다(실측:
    Datetime[us] 5,066개 · Datetime[ns] 1개 · String 1개) — Date 캐스팅은 타입을 가린다.
    """
    return pl.col("date").cast(pl.Utf8).str.slice(0, 10)


def build_context(
    *,
    entry: Optional[Dict[str, Any]],
    exit_: Optional[Dict[str, Any]],
    warmup_start_str: Optional[str],
    has_period_filter: bool,
    period_start_str: Optional[str],
    end_str: str,
    apply_dividends: bool,
    skip_risk: bool,
    skip_pos: bool,
    init_cash: float,
    pos_size_pct: float,
    liquid_limit: float,
    exec_type: str,
    delisted_symbols: Set[str],
    rank_metric_cols: List[str],
    tracked_metrics: Any,
    ai_needed: bool,
) -> Dict[str, Any]:
    """종목별 파이프라인이 읽는 요청-수준 상수 묶음(피클 가능)."""
    return {
        "entry": entry,
        "exit": exit_,
        "warmup_start_str": warmup_start_str,
        "has_period_filter": bool(has_period_filter),
        "period_start_str": period_start_str,
        "end_str": end_str,
        "apply_dividends": bool(apply_dividends),
        "skip_risk": bool(skip_risk),
        "skip_pos": bool(skip_pos),
        "init_cash": float(init_cash),
        "pos_size_pct": float(pos_size_pct),
        "liquid_limit": float(liquid_limit),
        "exec_type": exec_type,
        "delisted_symbols": set(delisted_symbols or ()),
        "rank_metric_cols": list(rank_metric_cols or []),
        "tracked_metrics": tracked_metrics,
        "ai_needed": bool(ai_needed),
        # 최적화 세션 캐시 키 재료 — 세션 밖이면 None(캐시 미사용)
        "prep_sig": structural_signature(entry, exit_),
    }


def _collect_leaf_conditions(group: Optional[Dict[str, Any]], out: List[Dict[str, Any]]) -> None:
    if not group:
        return
    for c in group.get("conditions", []):
        if "conditions" in c:
            _collect_leaf_conditions(c, out)
        else:
            out.append(c)


def filter_to_backtest_window(df_pl: pl.DataFrame, ctx: Dict[str, Any]) -> pl.DataFrame:
    if not ctx["has_period_filter"]:
        return df_pl
    date_col = date_key()
    if ctx["period_start_str"] is not None:
        df_pl = df_pl.filter(date_col >= ctx["period_start_str"])
    return df_pl.filter(date_col <= ctx["end_str"])


def close_at_last_available_row(entry_signals, exit_signals, exit_reasons, sym, ctx) -> None:
    """상폐/데이터 종료 종목: 마지막 가용 봉에서 강제 청산(next_open이면 그 전 봉에 신호)."""
    if len(exit_signals) == 0:
        return
    if ctx["exec_type"] == "next_open":
        if len(exit_signals) < 2:
            return
        exit_idx = len(exit_signals) - 2
    else:
        exit_idx = len(exit_signals) - 1
    entry_signals[exit_idx:] = False
    exit_signals[exit_idx] = True
    if not exit_reasons[exit_idx]:
        exit_reasons[exit_idx] = "상장폐지" if sym in ctx["delisted_symbols"] else "데이터 종료"


def prepare_symbol(sym: str, ctx: Dict[str, Any], loader, indicator_engine) -> Dict[str, Any]:
    """Phase1의 파라미터-불변 구간: 로드 → 워밍업 절단 → 지표 → 리졸버 → 기간 필터 → 전처리.

    호출 사이에 값이 바뀌지 않는 입력(종목·날짜 경계·구조 파라미터·배당 옵션)만 읽으므로
    최적화 세션에서 결과를 그대로 재사용할 수 있다(engine/prep_cache.py).
    outcome: 'none'(제외) | 'ai'(AI Phase2 대기) | 'ok'
    """
    df_pl = loader.load_symbol_data(sym)
    if df_pl is None or len(df_pl) == 0:
        return {"outcome": "none", "warning": f"{sym}: 데이터 없음 — 백테스트 대상에서 제외되었습니다."}

    # Pre-filter: clip to warmup window BEFORE indicator calculation.
    if ctx["warmup_start_str"] is not None:
        df_pl = df_pl.filter(date_key() >= ctx["warmup_start_str"])
    if len(df_pl) == 0:
        return {"outcome": "none"}

    indicators: List[Dict[str, Any]] = []
    _collect_leaf_conditions(ctx["entry"], indicators)
    _collect_leaf_conditions(ctx["exit"], indicators)
    df_pl = indicator_engine.calculate(df_pl, indicators)

    resolver = DataResolver()
    df_pl, res_logs = resolver.resolve(sym, df_pl, ctx["entry"], ctx["exit"])

    if ctx["ai_needed"]:
        return {"outcome": "ai", "df_pl": df_pl, "res_logs": res_logs}

    df_pl = filter_to_backtest_window(df_pl, ctx)
    if len(df_pl) < 1:
        return {"outcome": "none", "res_logs": res_logs}

    pdf = loader.preprocess_data(df_pl, apply_dividends=ctx["apply_dividends"])
    return {"outcome": "ok", "df_pl": df_pl, "pdf": pdf, "res_logs": res_logs}


def prep_cache_key(sym: str, ctx: Dict[str, Any]) -> Tuple:
    return (sym, ctx["warmup_start_str"], ctx["has_period_filter"], ctx["period_start_str"],
            ctx["end_str"], ctx["apply_dividends"], ctx["prep_sig"])


def process_symbol(
    sym: str,
    ctx: Dict[str, Any],
    loader,
    indicator_engine,
    signal_engine,
    prep_cache: Optional[SymbolPrepCache] = None,
) -> Tuple[str, Any, Dict[str, Any]]:
    """종목 하나의 Phase1 전체. 예외는 'warning'으로 흡수한다(다른 종목은 계속)."""
    side: Dict[str, Any] = {"warnings": [], "res_logs": []}
    try:
        cache = prep_cache if not ctx["ai_needed"] else None
        prep = None
        key = None
        if cache is not None:
            key = prep_cache_key(sym, ctx)
            prep = cache.get(key)
        if prep is None:
            prep = prepare_symbol(sym, ctx, loader, indicator_engine)
            if cache is not None:
                cache.put(key, prep)

        if prep.get("warning"):
            side["warnings"].append(prep["warning"])
        if prep.get("res_logs"):
            side["res_logs"].extend(prep["res_logs"])
        if prep["outcome"] == "none":
            return ("skip", None, side)
        if prep["outcome"] == "ai":
            return ("phase1_done", {"df_pl": prep["df_pl"], "pdf_for_ai": prep["df_pl"].to_pandas()}, side)

        df_pl = prep["df_pl"]
        pdf = prep["pdf"]

        # Liquidity Check — compute the mask now, but defer the exclusion warning until we
        # know the strategy actually wants to enter this symbol.
        liquidity_ok = None
        if not (ctx["skip_risk"] or ctx["skip_pos"]):
            target_pos_amount = ctx["init_cash"] * (ctx["pos_size_pct"] / 100.0)
            liquidity_ok = loader.check_liquidity(pdf, target_pos_amount, ctx["liquid_limit"])

        # Signal Generation
        entry_signals, entry_reasons = signal_engine.generate_signals(df_pl, ctx["entry"])
        exit_signals, exit_reasons = signal_engine.generate_signals(df_pl, ctx["exit"])
        close_at_last_available_row(entry_signals, exit_signals, exit_reasons, sym, ctx)

        if entry_signals is None:
            return ("skip", None, side)

        if liquidity_ok is not None:
            wanted_entry = bool(entry_signals.any())
            entry_signals = entry_signals & liquidity_ok
            if wanted_entry and not entry_signals.any():
                return ("warning", f"{sym}: 유동성 기준 미달 (거래대금 부족)", side)

        exec_type = ctx["exec_type"]
        res: Dict[str, Any] = {
            "symbol": sym,
            "price": pdf["close"],
            "exec_price": pdf["close"] if exec_type == "same_close" else pdf["open"],
            "high": pdf["high"] if "high" in pdf.columns else pdf["close"],
            "low": pdf["low"] if "low" in pdf.columns else pdf["close"],
            "entries": pd.Series(entry_signals, index=pdf.index),
            "exits": pd.Series(exit_signals, index=pdf.index),
            "entry_reasons": pd.Series(entry_reasons, index=pdf.index),
            "exit_reasons": pd.Series(exit_reasons, index=pdf.index),
            "index": pdf.index,
        }
        if not (ctx["skip_risk"] or ctx["skip_pos"]):
            res["liquidity"] = pd.Series(liquidity_ok, index=pdf.index)
        if "volume" in pdf.columns:
            res["trading_value"] = pdf["close"] * pdf["volume"]
        if "pbr" in pdf.columns:
            res["pbr"] = pdf["pbr"]
        if "roe_or_gpa" in pdf.columns:
            res["roe"] = pdf["roe_or_gpa"]
        if ctx["rank_metric_cols"]:
            res["fund_rank_values"] = {
                col: pdf[col] for col in ctx["rank_metric_cols"] if col in pdf.columns
            }
        if ctx["tracked_metrics"]:
            res["coverage"] = data_coverage.symbol_stats(pdf, ctx["tracked_metrics"])
        return ("success", res, side)
    except Exception as e:
        return ("warning", f"{sym}: 처리 오류 ({e})", side)
