import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Any

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
                       benchmark_label: str = "매수 후 보유") -> Dict[str, Any]:

        signals_list = []
        sl_pct = float(risk_params.get('stop_loss_pct') or 0)
        tp_pct = float(risk_params.get('take_profit_pct') or 0)
        ts_pct = float(risk_params.get('trailing_stop_pct') or 0)
        max_hold = int(risk_params.get('max_holding_days') or 0)

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
                ts_vals = idx.asi8  # vectorized int64, no Python loop
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
                """Mirror get_reasons_for_sym but returns pre-built array."""
                if sym in fast_dict:
                    return fast_dict[sym]
                for k in fast_dict:
                    if str(sym) in str(k) or str(k) in str(sym):
                        return fast_dict[k]
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
                        reason_kr = f"보유 기간 만료 ({duration}일 보유)" if duration > 0 else "보유 기간 만료"
                    else:
                        # Fix 8: 종료 이유 추론 — 허용 오차를 1%로 축소하고 우선순위 명확화
                        _TOLERANCE = 1.0
                        if max_hold > 0 and duration >= max_hold:
                            reason_kr = f"보유 기간 만료 ({duration}일 보유)"
                        elif sl_pct > 0 and pnl < 0 and abs(ret_val + sl_pct) < _TOLERANCE:
                            reason_kr = f"손절매 실행 (-{fmt_pct(sl_pct)}%)"
                        elif tp_pct > 0 and pnl > 0 and abs(ret_val - tp_pct) < _TOLERANCE:
                            reason_kr = f"익절매 실행 (+{fmt_pct(tp_pct)}%)"
                        elif ts_pct > 0 and pnl > 0 and reason_kr == "전략 매도 조건 충족":
                            reason_kr = f"트레일링 스탑 실행 (-{fmt_pct(ts_pct)}%)"

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

            _pa_r = _to_np(pf.total_return(group_by=False))
            _pa_c = _to_np(pf.trades.count(group_by=False))
            _pa_w = _to_np(pf.trades.win_rate(group_by=False))
            _pa_p = _to_np(pf.total_profit(group_by=False))
            _pa_g = _to_np(pf.annualized_return(group_by=False))
            _pa_m = _to_np(pf.max_drawdown(group_by=False))

            for i, sym in enumerate(processed_symbols):
                per_asset_stats[sym] = {
                    "symbol":      sym,
                    "totalReturn": float(_pa_r[i] if i < len(_pa_r) else 0.0) * 100,
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

        # ── Benchmark ─────────────────────────────────────────────────────────
        if benchmark_prices is not None and len(benchmark_prices) > 0:
            # Align benchmark to common_index
            bench_aligned = benchmark_prices.reindex(common_index).ffill().bfill()
            bench_first = bench_aligned.iloc[0]
            bench_mean_rets = bench_aligned.pct_change().fillna(0.0)
            if bench_first and bench_first != 0:
                bench_mean_rets.iloc[0] = 0.0
        else:
            # Fallback: equal-weight buy-and-hold of strategy symbols
            bench_rets = pf.benchmark_returns()
            if isinstance(bench_rets, pd.DataFrame):
                bench_mean_rets = bench_rets.mean(axis=1)
            else:
                bench_mean_rets = bench_rets

        bench_cum_returns = (1 + bench_mean_rets).cumprod()
        bench_total_return = bench_cum_returns.iloc[-1] - 1 if len(bench_cum_returns) > 0 else 0.0

        # ── Portfolio-level metrics ───────────────────────────────────────────
        total_return_decimal = cls.safe(pf.total_return())
        n_days  = len(common_index)
        n_years = n_days / 252.0
        if n_years >= 1.0 and total_return_decimal > -1:
            cagr_val = ((1 + total_return_decimal) ** (1 / n_years) - 1) * 100
        else:
            cagr_val = total_return_decimal * 100

        raw_pf = cls.safe(pf.trades.profit_factor())

        is_buy_and_hold = False
        if total_trades > 0 and total_trades <= 30 and len(pf.trades.records) > 0:
            try:
                exit_idxs = pf.trades.records['exit_idx'].values.astype(int)
                last_bar  = n_days - 1
                full_period_trades = int(np.sum((last_bar - exit_idxs) <= 5))
                if full_period_trades >= total_trades * 0.7:
                    is_buy_and_hold = True
            except: pass

        if is_buy_and_hold:
            try:
                pnls = pf.trades.records['pnl'].values.astype(float)
                total_profit_v = float(np.sum(pnls[pnls > 0]))
                total_loss_v   = float(np.abs(np.sum(pnls[pnls < 0])))
                raw_pf = total_profit_v / total_loss_v if total_loss_v > 0 else 0.0
            except: pass

        if total_trades < 30 and raw_pf > 10.0:
            raw_pf = min(raw_pf, 10.0)

        # ── Sharpe / Sortino / Volatility — single pf.returns() call ─────────
        # pf.sharpe_ratio() and pf.sortino_ratio() each call pf.returns() internally.
        # Computing returns once and deriving all three avoids 3× recomputation.
        _daily_rets_raw = pf.returns(group_by=True)
        if isinstance(_daily_rets_raw, pd.DataFrame):
            _daily_rets = _daily_rets_raw.mean(axis=1).values.astype(float)
        else:
            _daily_rets = np.asarray(_daily_rets_raw, dtype=float)
        _daily_rets = _daily_rets[np.isfinite(_daily_rets)]

        _std = _daily_rets.std()
        _mean = _daily_rets.mean()
        _sharpe  = float((_mean * np.sqrt(252)) / _std) if _std > 0 else 0.0

        _down = _daily_rets[_daily_rets < 0]
        _down_std = _down.std() if len(_down) > 1 else 0.0
        _sortino = float((_mean * 252) / (_down_std * np.sqrt(252))) if _down_std > 0 else 0.0

        _vol = float(_std * np.sqrt(252)) * 100

        _mdd    = cls.safe(pf.max_drawdown()) * 100
        _calmar = cagr_val / abs(_mdd) if _mdd != 0 else 0.0
        _equity = to_list(pf.value())
        _total_profit = cls.safe(pf.total_profit())

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
            "equity":               _equity,
            "benchmark_equity":     to_list(init_cash * bench_cum_returns),
            "dates":                _dates,
            "signals":              signals_list,
            "perAssetStats":        per_asset_stats,
            "benchmark_label":      benchmark_label,
            "warnings":             list(getattr(cls, '_warnings', set())),
            "version":              "6.6 (vectorized streaks, cached returns, no-sanitize-loop)",
        }
