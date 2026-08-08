import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any

from engine.version import ENGINE_VERSION

class ResultHandler:
    @staticmethod
    def safe(val):
        try:
            if val is None: return 0.0
            if isinstance(val, (pd.Series, pd.Index, np.ndarray)):
                if len(val) == 0: return 0.0
                m = val.mean()
                if hasattr(m, 'iloc'): m = m.iloc[0]
                elif hasattr(m, '__getitem__'): m = m[0]
                return float(m)
            if isinstance(val, pd.DataFrame):
                if val.empty: return 0.0
                return float(val.values.mean())
            if isinstance(val, (int, float, np.number)):
                if np.isnan(val) or np.isinf(val): return 0.0
                return float(val)
            if hasattr(val, 'item'): return float(val.item())
            return float(val)
        except: return 0.0

    @classmethod
    def format_results(cls, pf, processed_symbols, _all_entries, _all_exits,
                       all_entry_reasons, all_exit_reasons, common_index,
                       risk_params, exec_type, init_cash,
                       benchmark_prices: "pd.Series | None" = None,
                       benchmark_label: str = "매수 후 보유",
                       risk_free_rate: float = 0.0,
                       exit_reason_overrides: "Dict[str, Dict[str, str]] | None" = None) -> Dict[str, Any]:

        signals_list = []
        sl_pct = float(risk_params.get('stop_loss_pct') or 0)
        tp_pct = float(risk_params.get('take_profit_pct') or 0)
        ts_pct = float(risk_params.get('trailing_stop_pct') or 0)
        max_hold = int(risk_params.get('max_holding_days') or 0)

        # 종목별 실투입원가 누적 (진입가 × 수량) — 종목 분석 표의 수익률을
        # 계좌 전체자본이 아닌 해당 종목 거래 원가 기준으로 계산하기 위함.
        per_symbol_cost: Dict[str, float] = {}

        if len(pf.trades.records) > 0:
            vbt_trades = pf.trades.records_readable
            raw_records = pf.trades.records

            def norm_dt(ts):
                try:
                    return pd.to_datetime(ts).tz_localize(None).normalize()
                except: return ts

            def get_dt_str(ts):
                try:
                    return pd.Timestamp(ts).strftime('%Y-%m-%d')
                except Exception:
                    return str(ts)

            # ── O(log n) reason lookup via searchsorted ───────────────────────
            def build_reason_array(ser):
                """Normalize DatetimeIndex → sorted int64 array for searchsorted."""
                valid = ser.dropna()
                if len(valid) == 0:
                    return None
                idx = pd.DatetimeIndex(valid.index)
                if idx.tz is not None:
                    idx = idx.tz_localize(None)
                idx = idx.normalize()
                # Pandas can preserve microsecond-backed indexes from Polars.
                # Cast to ns so these values are comparable with Timestamp.value.
                ts_vals = idx.astype("datetime64[ns]").asi8
                sort_idx = np.argsort(ts_vals)
                return {'timestamps': ts_vals[sort_idx], 'values': valid.values[sort_idx]}

            def fast_reason_lookup(reason_arr, lookup_dt, max_diff_days=3):
                """Find reason at or before lookup_dt within max_diff_days."""
                if reason_arr is None:
                    return None
                lookup_ts = np.int64(pd.Timestamp(lookup_dt).value)
                idx = int(np.searchsorted(reason_arr['timestamps'], lookup_ts, side='right')) - 1
                if idx < 0:
                    return None
                diff_days = float(lookup_ts - reason_arr['timestamps'][idx]) / 86_400_000_000_000.0
                if diff_days <= max_diff_days:
                    val = reason_arr['values'][idx]
                    return val if val else None
                return None

            def get_reason_arr(sym, fast_dict, col_idx=None):
                """정확 매칭 → 컬럼 인덱스 순으로 사유 배열을 찾는다.

                부분 문자열 매칭은 유사 심볼 간 오귀속(예: '0059' vs '005930')을
                일으킬 수 있어 제거함 (감사 M5).
                """
                if sym in fast_dict:
                    return fast_dict[sym]
                if col_idx is not None and 0 <= col_idx < len(processed_symbols):
                    target = processed_symbols[col_idx]
                    if target in fast_dict:
                        return fast_dict[target]
                if len(fast_dict) == 1:
                    return next(iter(fast_dict.values()))
                return None

            # Pre-build lookup arrays once (vectorized — no per-element norm_dt)
            fast_entries = {}
            for s, ser in all_entry_reasons.items():
                fast_entries[s] = build_reason_array(ser)

            fast_exits = {}
            for s, ser in all_exit_reasons.items():
                fast_exits[s] = build_reason_array(ser)

            def fmt_pct(v): return str(int(v)) if v == int(v) else str(v)

            # ── Pre-extract DataFrame columns as numpy arrays ─────────────────
            # Avoids per-row Series object creation from iterrows()
            cols = set(vbt_trades.columns.tolist())

            arr_column  = vbt_trades['Column'].values    if 'Column'     in cols else None
            arr_col_idx = vbt_trades['Column Idx'].values if 'Column Idx' in cols else None

            e_ts_key    = next((c for c in ['Entry Timestamp', 'Entry Index', 'Entry Idx'] if c in cols), None)
            x_ts_key    = next((c for c in ['Exit Timestamp',  'Exit Index',  'Exit Idx']  if c in cols), None)
            e_price_key = next((c for c in ['Avg Entry Price', 'Entry Price'] if c in cols), None)
            x_price_key = next((c for c in ['Avg Exit Price',  'Exit Price']  if c in cols), None)

            n_trades = len(vbt_trades)
            arr_e_ts    = vbt_trades[e_ts_key].values    if e_ts_key    else [None] * n_trades
            arr_x_ts    = vbt_trades[x_ts_key].values    if x_ts_key    else [None] * n_trades
            arr_e_price = vbt_trades[e_price_key].values if e_price_key else np.zeros(n_trades)
            arr_x_price = vbt_trades[x_price_key].values if x_price_key else np.zeros(n_trades)
            arr_size    = vbt_trades['Size'].values       if 'Size'   in cols else np.zeros(n_trades)
            arr_pnl     = vbt_trades['PnL'].values        if 'PnL'    in cols else np.zeros(n_trades)
            arr_ret     = vbt_trades['Return'].values     if 'Return' in cols else np.zeros(n_trades)

            # Raw records numpy arrays
            rc_cols = set(raw_records.columns.tolist())
            arr_exit_type  = raw_records['exit_type'].values.astype(int)  if 'exit_type'  in rc_cols else np.full(n_trades, -1, dtype=int)
            arr_exit_idx   = raw_records['exit_idx'].values.astype(int)   if 'exit_idx'   in rc_cols else np.zeros(n_trades, dtype=int)
            arr_entry_idx  = raw_records['entry_idx'].values.astype(int)  if 'entry_idx'  in rc_cols else np.zeros(n_trades, dtype=int)

            last_date_str = common_index[-1].strftime('%Y-%m-%d') if len(common_index) > 0 else ''

            # ── Main loop: index-based (no iterrows/itertuples overhead) ──────
            for i in range(n_trades):
                # 1. Symbol Identification
                sym_raw = arr_column[i] if arr_column is not None else None
                if isinstance(sym_raw, tuple) and len(sym_raw) > 0: sym_raw = sym_raw[0]
                sym = str(sym_raw) if sym_raw is not None else None

                col_idx_val = int(arr_col_idx[i]) if arr_col_idx is not None else None
                if sym is None or sym not in processed_symbols:
                    if col_idx_val is not None and 0 <= col_idx_val < len(processed_symbols):
                        sym = processed_symbols[col_idx_val]

                if sym is None or sym not in processed_symbols:
                    sym = processed_symbols[0] if len(processed_symbols) == 1 else "unknown"

                # 2. Trade Data
                e_idx   = arr_e_ts[i]
                x_idx   = arr_x_ts[i]
                e_price = cls.safe(arr_e_price[i])
                x_price = cls.safe(arr_x_price[i])
                size    = cls.safe(arr_size[i])
                pnl     = cls.safe(arr_pnl[i])
                ret_val = cls.safe(arr_ret[i]) * 100
                per_symbol_cost[sym] = per_symbol_cost.get(sym, 0.0) + e_price * size
                exit_type = int(arr_exit_type[i])
                duration  = int(arr_exit_idx[i] - arr_entry_idx[i])

                # 3. Entry Reason (O(log n) searchsorted)
                e_reason = "매수 조건 충족 (전략 시그널)"
                try:
                    sym_arr_e = get_reason_arr(sym, fast_entries, col_idx_val)
                    if sym_arr_e is not None:
                        lookup_dt = norm_dt(e_idx)
                        if exec_type == 'next_open' and sym_arr_e is not None:
                            lookup_ts_ns = np.int64(pd.Timestamp(lookup_dt).value)
                            idx2 = int(np.searchsorted(sym_arr_e['timestamps'], lookup_ts_ns, side='left')) - 1
                            if idx2 >= 0:
                                lookup_dt = pd.Timestamp(sym_arr_e['timestamps'][idx2])
                        val = fast_reason_lookup(sym_arr_e, lookup_dt)
                        if val: e_reason = val
                except: pass

                final_qty = int(np.floor(size))
                if final_qty >= 1:
                    signals_list.append({
                        "date": get_dt_str(e_idx), "symbol": str(sym), "type": "buy",
                        "price": float(round(e_price)), "quantity": final_qty,
                        "amount": float(round(e_price) * final_qty), "condition": e_reason
                    })

                    # 4. Exit Reason (O(log n) searchsorted)
                    reason_kr = "전략 매도 조건 충족"
                    try:
                        sym_arr_x = get_reason_arr(sym, fast_exits, col_idx_val)
                        if sym_arr_x is not None:
                            lookup_dt_x = norm_dt(x_idx)
                            if exec_type == 'next_open':
                                lookup_ts_ns_x = np.int64(pd.Timestamp(lookup_dt_x).value)
                                idx3 = int(np.searchsorted(sym_arr_x['timestamps'], lookup_ts_ns_x, side='left')) - 1
                                if idx3 >= 0:
                                    lookup_dt_x = pd.Timestamp(sym_arr_x['timestamps'][idx3])
                            val_x = fast_reason_lookup(sym_arr_x, lookup_dt_x)
                            if val_x: reason_kr = val_x
                    except: pass

                    # 5. Risk Management Overrides
                    if exit_type == 1:   reason_kr = f"손절매 실행 (-{fmt_pct(sl_pct)}%)" if sl_pct > 0 else "손절매 실행"
                    elif exit_type == 2: reason_kr = f"트레일링 스탑 (-{fmt_pct(ts_pct)}%)" if ts_pct > 0 else "트레일링 스탑 실행"
                    elif exit_type == 3: reason_kr = f"익절매 실행 (+{fmt_pct(tp_pct)}%)" if tp_pct > 0 else "익절매 실행"
                    elif exit_type == 4:
                        reason_kr = f"보유 기간 만료 ({duration}거래일 보유)" if duration > 0 else "보유 기간 만료"
                    else:
                        # Fix 8: 종료 이유 추론 — 허용 오차를 1%로 축소하고 우선순위 명확화
                        _TOLERANCE = 1.0
                        if max_hold > 0 and duration >= max_hold:
                            reason_kr = f"보유 기간 만료 ({duration}거래일 보유)"
                        elif sl_pct > 0 and pnl < 0 and abs(ret_val + sl_pct) < _TOLERANCE:
                            reason_kr = f"손절매 실행 (-{fmt_pct(sl_pct)}%)"
                        elif tp_pct > 0 and pnl > 0 and abs(ret_val - tp_pct) < _TOLERANCE:
                            reason_kr = f"익절매 실행 (+{fmt_pct(tp_pct)}%)"
                        elif ts_pct > 0 and pnl > 0 and reason_kr == "전략 매도 조건 충족":
                            reason_kr = f"트레일링 스탑 실행 (-{fmt_pct(ts_pct)}%)"

                    # 6. 시뮬레이터가 남긴 정밀 청산 사유(리밸런싱 편출 등)를 최우선 적용.
                    # 신호/리스크 청산과 상호 배타적이므로 위 추론을 덮어써도 안전하다.
                    if exit_reason_overrides:
                        ov = exit_reason_overrides.get(sym)
                        if ov:
                            ov_reason = ov.get(get_dt_str(x_idx))
                            if ov_reason:
                                reason_kr = ov_reason

                    if exit_type == 5 or get_dt_str(x_idx) == last_date_str:
                        reason_kr = "백테스트 종료"

                    pnl_label = "수익" if pnl >= 0 else "손실"
                    signals_list.append({
                        "date": get_dt_str(x_idx), "symbol": str(sym), "type": "sell",
                        "price": float(round(x_price)), "quantity": final_qty,
                        "amount": float(round(x_price) * final_qty),
                        "condition": f"{reason_kr} [수익률: {ret_val:+.2f}%, {pnl_label}: {abs(pnl):,.0f}원]"
                    })

        signals_list.sort(key=lambda x: x['date'])

        # ── Aggregate Stats ───────────────────────────────────────────────────
        total_trades = len(pf.trades)
        win_count    = len(pf.trades.winning)
        agg_win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0

        avg_win = 0.0
        avg_loss = 0.0
        trade_returns = None
        try:
            if 'return' in pf.trades.records:
                trade_returns = pf.trades.records['return'].values.astype(float)
        except:
            trade_returns = None

        if trade_returns is not None and len(trade_returns) > 0:
            winning_returns = trade_returns[trade_returns > 0]
            losing_returns = trade_returns[trade_returns < 0]
            avg_win = float(np.mean(winning_returns) * 100) if len(winning_returns) > 0 else 0.0
            avg_loss = float(abs(np.mean(losing_returns)) * 100) if len(losing_returns) > 0 else 0.0

        # ── Win/Loss streak — fully vectorized numpy (no Python loop) ────────
        if total_trades > 0:
            _is_win = (pf.trades.records['pnl'].astype(float) > 0).astype(np.int8)

            def _max_streak_np(a: np.ndarray) -> int:
                """O(n) vectorized max consecutive run — zero Python loop."""
                if len(a) == 0:
                    return 0
                padded = np.concatenate([[0], a, [0]])
                diffs  = np.diff(padded.astype(np.int16))
                starts = np.where(diffs == 1)[0]
                ends   = np.where(diffs == -1)[0]
                return int((ends - starts).max()) if len(starts) > 0 else 0

            max_consecutive_wins   = _max_streak_np(_is_win)
            max_consecutive_losses = _max_streak_np(1 - _is_win)
        else:
            max_consecutive_wins   = 0
            max_consecutive_losses = 0

        # ── Average holding days ──────────────────────────────────────────────
        avg_holding_days = 0.0
        try:
            if total_trades > 0 and 'entry_idx' in pf.trades.records and 'exit_idx' in pf.trades.records:
                entry_idxs = pf.trades.records['entry_idx'].values.astype(float)
                exit_idxs  = pf.trades.records['exit_idx'].values.astype(float)
                avg_holding_days = float(np.mean(exit_idxs - entry_idxs))
        except:
            avg_holding_days = 0.0

        # ── Per-Asset Stats — extract to numpy arrays, avoid repeated VBT overhead ──
        per_asset_stats = {}
        if len(processed_symbols) > 0:
            def _to_np(obj) -> np.ndarray:
                if isinstance(obj, pd.Series):   return np.nan_to_num(obj.values, nan=0.0, posinf=0.0, neginf=0.0)
                if isinstance(obj, pd.DataFrame): return np.nan_to_num(obj.values.flatten(), nan=0.0, posinf=0.0, neginf=0.0)
                if isinstance(obj, np.ndarray):   return np.nan_to_num(obj, nan=0.0, posinf=0.0, neginf=0.0)
                return np.array([float(obj) if obj is not None else 0.0])

            _pa_c = _to_np(pf.trades.count(group_by=False))
            _pa_w = _to_np(pf.trades.win_rate(group_by=False))
            _pa_p = _to_np(pf.total_profit(group_by=False))
            _pa_g = _to_np(pf.annualized_return(group_by=False))
            _pa_m = _to_np(pf.max_drawdown(group_by=False))

            for i, sym in enumerate(processed_symbols):
                profit_i = float(_pa_p[i] if i < len(_pa_p) else 0.0)
                cost_i = per_symbol_cost.get(sym, 0.0)
                # 계좌 전체자본이 아닌 해당 종목에 실제 투입된 원가(진입가×수량) 대비
                # 수익률 — 매매기록 인라인 수익률(ret_val, 위 루프)과 동일한 기준.
                total_return_i = (profit_i / cost_i * 100.0) if cost_i > 0 else 0.0
                per_asset_stats[sym] = {
                    "symbol":      sym,
                    "totalReturn": total_return_i,
                    "trades":      int(_pa_c[i]   if i < len(_pa_c) else 0.0),
                    "winRate":     float(_pa_w[i] if i < len(_pa_w) else 0.0) * 100,
                    "profit":      float(_pa_p[i] if i < len(_pa_p) else 0.0),
                    "cagr":        float(_pa_g[i] if i < len(_pa_g) else 0.0) * 100,
                    "maxDrawdown": float(_pa_m[i] if i < len(_pa_m) else 0.0) * 100,
                }

        def to_list(obj):
            if isinstance(obj, (pd.DataFrame, pd.Series)):
                return np.nan_to_num(obj.values.flatten(), nan=0.0, posinf=0.0, neginf=0.0).tolist()
            return [cls.safe(x) for x in obj]

        def to_list_nullable(obj):
            """to_list와 달리 결측을 0이 아니라 None으로 내보낸다.

            벤치마크 수익곡선은 커버리지 밖 구간이 존재할 수 있는데, 0으로 채우면
            "그 구간 벤치마크가 0원이었다"는 거짓 곡선이 된다."""
            values = obj.values.flatten() if isinstance(obj, (pd.DataFrame, pd.Series)) else np.asarray(obj, dtype=float)
            return [None if (np.isnan(v) or np.isinf(v)) else float(v) for v in values]

        # ── Benchmark ─────────────────────────────────────────────────────────
        # 벤치마크 값이 없는 구간은 채우지 않는다.
        #
        # v11.0 이전에는 .bfill()로 지수 ETF 상장 이전 구간에 첫 가격을 뒤채웠다.
        # 가격이 상수라 그 구간 수익률이 전부 0%가 되는데, 누적곱은 커버리지 구간만
        # 곱한 것과 같아 **bench_total_return 값 자체는 달라지지 않는다**. 달라지는
        # 것은 수익곡선으로, 벤치마크가 존재하지도 않던 구간에 초기자본에서 평탄한
        # 선이 그려져 "그때 벤치마크는 제자리였다"는 거짓 정보가 됐다.
        #
        # 값이 같다는 것이 비교가 정당하다는 뜻은 아니다 — 벤치마크 수익률은 자기가
        # 존재한 구간만, 전략 수익률은 전체 구간을 복리로 쌓은 값이라 기간이 다르다.
        # 이 기간 불일치는 데이터로 메울 수 없으므로 엔진이 경고로 고지한다
        # (backtest_engine의 H1 경고).
        bench_valid: "pd.Series | None" = None
        if benchmark_prices is not None and len(benchmark_prices) > 0:
            # Align benchmark to common_index
            bench_aligned = benchmark_prices.reindex(common_index).ffill()
            bench_valid = bench_aligned.notna()
            # 첫 유효일은 직전 값이 없어 수익률이 정의되지 않는다 → 0(곡선 시작점).
            bench_mean_rets = bench_aligned.pct_change().fillna(0.0).where(bench_valid, 0.0)
        else:
            # Fallback: equal-weight buy-and-hold of strategy symbols
            bench_rets = pf.benchmark_returns()
            if isinstance(bench_rets, pd.DataFrame):
                bench_mean_rets = bench_rets.mean(axis=1)
            else:
                bench_mean_rets = bench_rets

        bench_cum_returns = (1 + bench_mean_rets).cumprod()
        if bench_valid is not None:
            # 커버리지 밖은 NaN → 수익곡선에 null로 나가 가짜 평탄 구간을 그리지 않는다.
            bench_cum_returns = bench_cum_returns.where(bench_valid, np.nan)
        _bench_cum_covered = bench_cum_returns.dropna()
        bench_total_return = _bench_cum_covered.iloc[-1] - 1 if len(_bench_cum_covered) > 0 else 0.0
        # 벤치마크가 백테스트 구간의 일부만 덮으면 두 수익률의 기간이 달라 차이값
        # (초과수익률)을 그대로 보여줄 수 없다 — 표시 쪽이 판단할 수 있게 알린다.
        bench_partial = bool(len(_bench_cum_covered) < len(bench_cum_returns))

        # ── Portfolio-level metrics ───────────────────────────────────────────
        total_return_decimal = cls.safe(pf.total_return())
        n_days  = len(common_index)
        n_years = n_days / 252.0
        if n_years >= 1.0 and total_return_decimal > -1:
            cagr_val = ((1 + total_return_decimal) ** (1 / n_years) - 1) * 100
        else:
            cagr_val = total_return_decimal * 100

        # 감사 C3: Profit Factor는 계산값을 그대로 보고한다. 과거의 10 클램프·
        # buy-and-hold 재정의는 통계를 조용히 조작하는 것이라 제거. 표본 부족
        # (거래 <30건)은 엔진이 경고로 고지한다.
        raw_pf = cls.safe(pf.trades.profit_factor())

        # ── Sharpe / Sortino / Volatility — single pf.returns() call ─────────
        # pf.sharpe_ratio() and pf.sortino_ratio() each call pf.returns() internally.
        # Computing returns once and deriving all three avoids 3× recomputation.
        _daily_rets_raw = pf.returns(group_by=True)
        if isinstance(_daily_rets_raw, pd.DataFrame):
            _daily_rets = _daily_rets_raw.mean(axis=1).values.astype(float)
        else:
            _daily_rets = np.asarray(_daily_rets_raw, dtype=float)
        _daily_rets = _daily_rets[np.isfinite(_daily_rets)]

        # 감사 M7: 연 무위험수익률(risk_free_rate, 기본 0)을 일 단위로 환산해 차감.
        _rf_daily = (1.0 + float(risk_free_rate)) ** (1.0 / 252.0) - 1.0 if risk_free_rate else 0.0
        _excess = _daily_rets - _rf_daily

        _std = _daily_rets.std()
        _mean_excess = _excess.mean()
        _sharpe  = float((_mean_excess * np.sqrt(252)) / _std) if _std > 0 else 0.0

        # 감사 H4: Sortino 표준 정의 — 하방편차는 '전체 기간'에 대해 목표(무위험)
        # 미달분의 RMS로 계산한다. (음수 수익률만의 표준편차는 비표준이며 하방
        # 위험을 과소/과대평가한다.)
        _downside = np.minimum(_excess, 0.0)
        _down_dev = float(np.sqrt(np.mean(_downside ** 2))) if len(_excess) > 0 else 0.0
        _sortino = float((_mean_excess * np.sqrt(252)) / _down_dev) if _down_dev > 0 else 0.0

        _vol = float(_std * np.sqrt(252)) * 100

        _mdd    = cls.safe(pf.max_drawdown()) * 100
        _calmar = cagr_val / abs(_mdd) if _mdd != 0 else 0.0
        _equity = to_list(pf.value())
        _total_profit = cls.safe(pf.total_profit())

        # ── 추가 통계: Exposure / DD Duration / Expectancy / Recovery Factor ──
        _equity_arr = np.asarray(_equity, dtype=float)
        _exposure = 0.0
        try:
            _asset_val = pf.asset_value(group_by=True)
            if isinstance(_asset_val, pd.DataFrame):
                _asset_val = _asset_val.sum(axis=1)
            _exposure = float((np.asarray(_asset_val, dtype=float) > 1e-9).mean()) * 100
        except Exception:
            pass

        _max_dd_duration = 0
        if len(_equity_arr) > 1:
            _running_max = np.maximum.accumulate(_equity_arr)
            _underwater = _equity_arr < _running_max - 1e-9
            if _underwater.any():
                _padded = np.concatenate([[0], _underwater.astype(np.int8), [0]])
                _d = np.diff(_padded)
                _starts, _ends = np.where(_d == 1)[0], np.where(_d == -1)[0]
                if len(_starts) > 0:
                    _max_dd_duration = int((_ends - _starts).max())

        _expectancy = 0.0  # 평균 거래 수익률 (%): 승률×평균수익 − 패률×평균손실과 동치
        if trade_returns is not None and len(trade_returns) > 0:
            _expectancy = float(np.mean(trade_returns) * 100)

        _recovery = 0.0
        if len(_equity_arr) > 1:
            _max_dd_value = float((np.maximum.accumulate(_equity_arr) - _equity_arr).max())
            if _max_dd_value > 0:
                _recovery = float(_total_profit / _max_dd_value)

        # ── dates: vectorized strftime, no Python loop ────────────────────────
        _dates = pd.DatetimeIndex(common_index).strftime('%Y-%m-%d').tolist()

        # ── scalar NaN guard (applied only to float scalars, not arrays) ──────
        def _sf(v: float) -> float:
            return 0.0 if (np.isnan(v) or np.isinf(v)) else v

        return {
            "symbols":              processed_symbols,
            "totalReturn":          _sf(total_return_decimal * 100),
            "totalProfit":          _sf(_total_profit),
            "cagr":                 _sf(cagr_val),
            "buyAndHoldReturn":     _sf(cls.safe(bench_total_return) * 100),
            "maxDrawdown":          _sf(_mdd),
            "winRate":              _sf(agg_win_rate),
            "trades":               total_trades,
            "avgProfit":            _sf(avg_win),
            "avgLoss":              _sf(avg_loss),
            "maxConsecutiveWins":   max_consecutive_wins,
            "maxConsecutiveLosses": max_consecutive_losses,
            "profitFactor":         _sf(raw_pf),
            "sharpe":               _sf(_sharpe),
            "sortino":              _sf(_sortino),
            "calmar":               _sf(_calmar),
            "avgHoldingDays":       _sf(avg_holding_days),
            "volatility":           _sf(_vol),
            "exposure":             _sf(_exposure),
            "maxDrawdownDuration":  _max_dd_duration,
            "expectancy":           _sf(_expectancy),
            "recoveryFactor":       _sf(_recovery),
            "equity":               _equity,
            "benchmark_equity":     to_list_nullable(init_cash * bench_cum_returns),
            "benchmark_partial":    bench_partial,
            "dates":                _dates,
            "signals":              signals_list,
            "perAssetStats":        per_asset_stats,
            "benchmark_label":      benchmark_label,
            "warnings":             [],
            # 결과를 산출한 백테스트 엔진 버전(SOT: engine/version.py). 어떤 버전으로
            # 테스트했는지 추적하기 위해 모든 결과에 기록한다.
            "version":              ENGINE_VERSION,
        }
