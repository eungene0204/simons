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

import numpy as np
import pandas as pd
import polars as pl

from engine import data_coverage
from engine import universe_pit
from engine import market_index
from engine.data_resolver import DataResolver
from engine import trade_reason as tr
from engine import result_warnings as rw
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
    signal_delay: int = 1,
    exec_price_basis: str = "open",
) -> Dict[str, Any]:
    """종목별 파이프라인이 읽는 요청-수준 상수 묶음(피클 가능)."""
    return {
        # 익일 체결가 열(v16.28): 'open'=시가(종전), 'avg'=시가·고가·저가·종가 평균.
        "exec_price_basis": exec_price_basis,
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
        # 신호 후 N거래일 지연 체결(next_open shift 폭, 기본 1) — 강제청산 신호 위치가 이를 따른다.
        "signal_delay": int(signal_delay),
        "delisted_symbols": set(delisted_symbols or ()),
        "rank_metric_cols": list(rank_metric_cols or []),
        "tracked_metrics": tracked_metrics,
        "ai_needed": bool(ai_needed),
        # 최적화 세션 캐시 키 재료 — 세션 밖이면 None(캐시 미사용)
        "prep_sig": structural_signature(entry, exit_),
    }


def exec_price_series(pdf: pd.DataFrame, exec_type: str, basis: str = "open") -> pd.Series:
    """체결가 열 — same_close=종가, next_open=시가(기본) 또는 익일 평균가(basis='avg', v16.28)."""
    if exec_type == "same_close":
        return pdf["close"]
    if basis == "avg" and all(c in pdf.columns for c in ("open", "high", "low", "close")):
        return (pdf["open"] + pdf["high"] + pdf["low"] + pdf["close"]) / 4.0
    return pdf["open"]


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


def window_boundary_prep(df_pl: pl.DataFrame, sym: str, ctx: Dict[str, Any], loader) -> Dict[str, Any]:
    """창 경계 준비물(v16.12) — 창 시작 절단 **전** 프레임에서 뽑는다.

    ① ``warm_close``: 워밍업 구간을 포함한 종가 — 랭킹 lookback 패널(N거래일 수익률·변동성·
       초과수익률) 전용. 창으로 잘린 종가로 계산하면 창의 첫 lookback 거래일 동안 순위가 없어
       전략이 현금으로 앉아 있었다(2026-09-17 실측: 60거래일 수익률 랭킹, 2023-09-18 시작 →
       첫 매수 2024-01-02).
    ② ``pre_df_pl``·``pre_close``·``pre_volume``: 창 직전 ``signal_delay + 1``봉 — next_open의
       N일 shift(신호·순위·유동성·시총 마스크)가 창 첫날에 **창 직전 거래일의 정보**를 끌어오게
       하는 원천이다. 창 안에서만 shift하면 첫날(=첫 리밸런싱일)은 늘 비어 첫 주기가 현금이었다.
       +1봉은 창 첫 봉·원천 첫 봉의 '전일' 참조(교차 신호·전일 거래대금 유동성)용.

    창 종가 패널(raw_price_df)의 의미(상장·상폐·가용성 판정)는 바꾸지 않는다 — 이 준비물은 따로
    실린다. 전처리(수정주가·배당 토탈리턴·기업행위 정제)는 창 종가와 같은 함수를 워밍업 포함
    프레임 전체에 적용하고, 종가 결과는 종가·조정 컬럼만으로 정해지므로 그 컬럼(+거래량)만 넘긴다.
    창 시작 절단이 없는 요청(FULL 등)은 창 종가가 곧 전체 이력이므로 전부 None.
    """
    out: Dict[str, Any] = {"warm_close": None, "pre_df_pl": None, "pre_close": None, "pre_volume": None}
    if not ctx["has_period_filter"] or ctx["warmup_start_str"] is None or ctx["period_start_str"] is None:
        return out
    frame = df_pl.filter(date_key() <= ctx["end_str"])
    if len(frame) == 0:
        return out
    cols = [c for c in ("date", "close", "adj_close", "dividends", "volume") if c in frame.columns]
    warm = loader.preprocess_data(
        frame.select(cols), apply_dividends=ctx["apply_dividends"],
        sanitize_corporate_actions=not universe_pit.is_us_symbol(sym),
    )
    out["warm_close"] = warm["close"]
    pre = frame.filter(date_key() < ctx["period_start_str"])
    if len(pre) == 0:
        return out   # 창 이전 이력 없음(창 안 신규 상장 등) — 창 첫날 원천도 없다
    pre = pre.tail(int(ctx.get("signal_delay", 1)) + 1)
    dates = pd.DatetimeIndex(pd.to_datetime(pre["date"].to_pandas()))
    out["pre_df_pl"] = pre
    out["pre_close"] = warm["close"].reindex(dates)
    out["pre_volume"] = warm["volume"].reindex(dates) if "volume" in warm.columns else None
    return out


def symbol_signals(df_pl: pl.DataFrame, pdf: pd.DataFrame, bprep: Optional[Dict[str, Any]],
                   sym: str, ctx: Dict[str, Any], loader, signal_engine) -> Optional[Dict[str, Any]]:
    """창 신호·유동성 + (next_open이면) 창 직전 N봉의 shift 원천 패키지.

    창 직전 봉(bprep["pre_df_pl"])이 있으면 신호·유동성을 **창 직전 봉을 이어 붙인 프레임**에서
    계산해 나눈다 — 창 첫 봉도 창 중간 봉과 같이 전일 봉을 본다(교차 신호, 전일 거래대금).
    창 이후 봉의 값은 전일 한 봉만 참조하므로 종전과 같다. 반환 None = 신호 없음(skip).
    """
    pre_df_pl = (bprep or {}).get("pre_df_pl")
    n_pre = 0 if pre_df_pl is None else len(pre_df_pl)
    sig_frame = pl.concat([pre_df_pl, df_pl], how="vertical") if n_pre else df_pl

    entries, entry_reasons = signal_engine.generate_signals(sig_frame, ctx["entry"])
    exits, exit_reasons = signal_engine.generate_signals(sig_frame, ctx["exit"])
    if entries is None:
        return None
    pre_entries, entries = entries[:n_pre], entries[n_pre:]
    pre_exits, exits = exits[:n_pre], exits[n_pre:]
    pre_entry_reasons, entry_reasons = entry_reasons[:n_pre], entry_reasons[n_pre:]
    pre_exit_reasons, exit_reasons = exit_reasons[:n_pre], exit_reasons[n_pre:]
    close_at_last_available_row(entries, exits, exit_reasons, sym, ctx)

    # Liquidity Check — compute the mask now, but defer the exclusion warning until we
    # know the strategy actually wants to enter this symbol.
    liquidity_ok = pre_liquidity = None
    if not (ctx["skip_risk"] or ctx["skip_pos"]):
        target_pos_amount = ctx["init_cash"] * (ctx["pos_size_pct"] / 100.0)
        if n_pre and bprep.get("pre_volume") is not None and "volume" in pdf.columns:
            ext = pd.DataFrame({
                "close": np.concatenate([bprep["pre_close"].to_numpy(dtype=float), pdf["close"].to_numpy(dtype=float)]),
                "volume": np.concatenate([bprep["pre_volume"].to_numpy(dtype=float), pdf["volume"].to_numpy(dtype=float)]),
            })
            liq = loader.check_liquidity(ext, target_pos_amount, ctx["liquid_limit"])
            pre_liquidity, liquidity_ok = liq[:n_pre], liq[n_pre:]
        else:
            liquidity_ok = loader.check_liquidity(pdf, target_pos_amount, ctx["liquid_limit"])

    liquidity_blocked = False
    if liquidity_ok is not None:
        wanted_entry = bool(entries.any())
        entries = entries & liquidity_ok
        if pre_liquidity is not None:
            pre_entries = pre_entries & pre_liquidity
        liquidity_blocked = wanted_entry and not entries.any()

    pre = None
    if n_pre and ctx["exec_type"] == "next_open":
        k = min(int(ctx.get("signal_delay", 1)), n_pre)
        idx = pd.DatetimeIndex(pd.to_datetime(pre_df_pl["date"].to_pandas()))[-k:]
        close = bprep["pre_close"].to_numpy(dtype=float)[-k:]
        pre = {
            "index": idx,
            "entries": pd.Series(pre_entries[-k:], index=idx),
            "exits": pd.Series(pre_exits[-k:], index=idx),
            "entry_reasons": pd.Series(pre_entry_reasons[-k:], index=idx, dtype=object),
            "exit_reasons": pd.Series(pre_exit_reasons[-k:], index=idx, dtype=object),
            "close": pd.Series(close, index=idx),
        }
        if pre_liquidity is not None:
            pre["liquidity"] = pd.Series(pre_liquidity[-k:], index=idx)
        if bprep.get("pre_volume") is not None:
            pre["trading_value"] = pd.Series(close * bprep["pre_volume"].to_numpy(dtype=float)[-k:], index=idx)
        tail = pre_df_pl.tail(k)
        if "market_cap" in tail.columns:
            pre["market_cap"] = pd.Series(tail["market_cap"].cast(pl.Float64).to_numpy(), index=idx)
        for _fin_col in ("net_income", "ebit"):
            # 적자기업 제외 필터(v16.32)도 신호와 같은 지연으로 판정한다 — 창 직전 원천이 없으면
            # 창 첫날이 판정 불가가 된다(fail-open이라 통과하지만 필터가 하루 늦게 걸린다).
            if _fin_col in tail.columns:
                pre[_fin_col] = pd.Series(
                    tail[_fin_col].cast(pl.Float64, strict=False).to_numpy(), index=idx)
        pre["fund_rank_values"] = {
            col: pd.Series(tail[col].cast(pl.Float64, strict=False).to_numpy(), index=idx)
            for col in ctx["rank_metric_cols"] if col in tail.columns
        }
    return {
        "entries": entries, "entry_reasons": entry_reasons,
        "exits": exits, "exit_reasons": exit_reasons,
        "liquidity": liquidity_ok, "liquidity_blocked": liquidity_blocked, "pre": pre,
    }


def close_at_last_available_row(entry_signals, exit_signals, exit_reasons, sym, ctx) -> None:
    """상폐/데이터 종료 종목: 마지막 가용 봉에서 강제 청산(next_open이면 지연 폭만큼 앞 봉에 신호)."""
    if len(exit_signals) == 0:
        return
    if ctx["exec_type"] == "next_open":
        delay = int(ctx.get("signal_delay", 1))
        if len(exit_signals) < delay + 1:
            return
        exit_idx = len(exit_signals) - 1 - delay
    else:
        exit_idx = len(exit_signals) - 1
    entry_signals[exit_idx:] = False
    exit_signals[exit_idx] = True
    if not exit_reasons[exit_idx]:
        exit_reasons[exit_idx] = tr.encode([tr.part(
            tr.DELISTED if sym in ctx["delisted_symbols"] else tr.DATA_END
        )])


def prepare_symbol(sym: str, ctx: Dict[str, Any], loader, indicator_engine) -> Dict[str, Any]:
    """Phase1의 파라미터-불변 구간: 로드 → 워밍업 절단 → 지표 → 리졸버 → (창 경계 준비물) → 기간 필터 → 전처리.

    호출 사이에 값이 바뀌지 않는 입력(종목·날짜 경계·구조 파라미터·배당 옵션)만 읽으므로
    최적화 세션에서 결과를 그대로 재사용할 수 있다(engine/prep_cache.py).
    outcome: 'none'(제외) | 'ai'(AI Phase2 대기) | 'ok'
    """
    df_pl = loader.load_symbol_data(sym)
    if df_pl is None or len(df_pl) == 0:
        return {"outcome": "none", "warning": rw.warning(rw.SYMBOL_NO_DATA, sym)}

    # Pre-filter: clip to warmup window BEFORE indicator calculation.
    if ctx["warmup_start_str"] is not None:
        df_pl = df_pl.filter(date_key() >= ctx["warmup_start_str"])
    if len(df_pl) == 0:
        return {"outcome": "none"}

    indicators: List[Dict[str, Any]] = []
    _collect_leaf_conditions(ctx["entry"], indicators)
    _collect_leaf_conditions(ctx["exit"], indicators)
    # 시장 대비 초과수익률 조건은 종목의 상장 시장 지수 종가가 있어야 계산된다 —
    # 지표 엔진은 심볼을 모르므로 여기서(심볼을 아는 유일한 지점) 날짜 조인으로 붙인다.
    df_pl = market_index.attach_index_close(df_pl, sym, indicators, loader.data_dir)
    df_pl = indicator_engine.calculate(df_pl, indicators)

    resolver = DataResolver()
    df_pl, res_logs = resolver.resolve(sym, df_pl, ctx["entry"], ctx["exit"])
    # 랭킹 지표가 parquet 컬럼에 없으면(런타임 계산 지표 — FCF 수익률·자산성장률·발생액 비율, v16.25)
    # 조건과 같은 경로로 해결한다. 종전엔 조건에 쓰인 지표만 해결돼 랭킹 전용 지표는 '데이터 없음'으로
    # 랭킹이 빠졌다. 컬럼이 이미 있으면 호출이 없어 결과 불변.
    _rank_missing = [c for c in (ctx.get("rank_metric_cols") or []) if c not in df_pl.columns]
    if _rank_missing:
        df_pl, _more = resolver.resolve(
            sym, df_pl,
            {"conditions": [{"type": "fundamental", "id": c, "params": {}} for c in _rank_missing]},
            None,
        )
        res_logs = list(res_logs) + list(_more)

    if ctx["ai_needed"]:
        return {"outcome": "ai", "df_pl": df_pl, "res_logs": res_logs}

    bprep = window_boundary_prep(df_pl, sym, ctx, loader)
    df_pl = filter_to_backtest_window(df_pl, ctx)
    if len(df_pl) < 1:
        return {"outcome": "none", "res_logs": res_logs}

    pdf = loader.preprocess_data(
        df_pl, apply_dividends=ctx["apply_dividends"],
        sanitize_corporate_actions=not universe_pit.is_us_symbol(sym),
    )
    return {"outcome": "ok", "df_pl": df_pl, "pdf": pdf, "res_logs": res_logs, **bprep}


def prep_cache_key(sym: str, ctx: Dict[str, Any]) -> Tuple:
    # signal_delay: 창 직전 원천 봉 수(delay+1)가 산출물에 들어간다(window_boundary_prep).
    return (sym, ctx["warmup_start_str"], ctx["has_period_filter"], ctx["period_start_str"],
            ctx["end_str"], ctx["apply_dividends"], ctx["prep_sig"], int(ctx.get("signal_delay", 1)))


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

        sig = symbol_signals(df_pl, pdf, prep, sym, ctx, loader, signal_engine)
        if sig is None:
            return ("skip", None, side)
        if sig["liquidity_blocked"]:
            return ("warning", rw.warning(rw.SYMBOL_LIQUIDITY_BELOW, sym), side)
        entry_signals, entry_reasons = sig["entries"], sig["entry_reasons"]
        exit_signals, exit_reasons = sig["exits"], sig["exit_reasons"]
        liquidity_ok = sig["liquidity"]

        exec_type = ctx["exec_type"]
        res: Dict[str, Any] = {
            "symbol": sym,
            "price": pdf["close"],
            "exec_price": exec_price_series(pdf, exec_type, ctx.get("exec_price_basis", "open")),
            "high": pdf["high"] if "high" in pdf.columns else pdf["close"],
            "low": pdf["low"] if "low" in pdf.columns else pdf["close"],
            "entries": pd.Series(entry_signals, index=pdf.index),
            "exits": pd.Series(exit_signals, index=pdf.index),
            "entry_reasons": pd.Series(entry_reasons, index=pdf.index),
            "exit_reasons": pd.Series(exit_reasons, index=pdf.index),
            "index": pdf.index,
        }
        if prep.get("warm_close") is not None:
            res["warm_close"] = prep["warm_close"]
        if sig["pre"] is not None:
            res["pre"] = sig["pre"]
        if not (ctx["skip_risk"] or ctx["skip_pos"]):
            res["liquidity"] = pd.Series(liquidity_ok, index=pdf.index)
        if "volume" in pdf.columns:
            res["trading_value"] = pdf["close"] * pdf["volume"]
        if "market_cap" in pdf.columns:
            # 일별 실측 시가총액(억원, KRX 스냅샷) — 지수 유니버스 상위 N 판정의 정본.
            res["market_cap"] = pdf["market_cap"]
        if "pbr" in pdf.columns:
            res["pbr"] = pdf["pbr"]
        # 적자기업 제외 필터(v16.32)의 판정 재료 — 그 시점에 알려진 최신 연간 재무가
        # 일자별로 전진충전돼 있다. 필터를 켰는지와 무관하게 싣는다(캐시된 Phase1 결과가
        # 필터 설정에 따라 달라지면 재사용이 깨진다 — market_cap·pbr와 같은 계약).
        if "net_income" in pdf.columns:
            res["net_income"] = pdf["net_income"]
        if "ebit" in pdf.columns:
            res["ebit"] = pdf["ebit"]
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
        return ("warning", rw.warning(rw.SYMBOL_PROCESSING_ERROR, sym, e), side)
