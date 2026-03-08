import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional

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
    def format_results(cls, pf, processed_symbols, all_entries, all_exits, 
                       all_entry_reasons, all_exit_reasons, common_index, 
                       risk_params, exec_type, init_cash) -> Dict[str, Any]:
        
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
                if isinstance(ts, (pd.Timestamp, datetime)): return ts.strftime('%Y-%m-%d')
                return str(ts)

            def get_reasons_for_sym(s_name, reasons_dict, processed_symbols, col_idx=None):
                if not s_name and col_idx is None: return None
                if s_name in reasons_dict: return reasons_dict[s_name]
                for k in reasons_dict.keys():
                    if str(s_name) in str(k) or str(k) in str(s_name):
                        return reasons_dict[k]
                if col_idx is not None and 0 <= col_idx < len(processed_symbols):
                    target_sym = processed_symbols[col_idx]
                    if target_sym in reasons_dict: return reasons_dict[target_sym]
                if len(reasons_dict) == 1:
                    return next(iter(reasons_dict.values()))
                return None

            # Optimization: Pre-normalize all reason indices ONCE
            norm_entries = {}
            for s, ser in all_entry_reasons.items():
                ser_norm = ser.copy()
                ser_norm.index = ser_norm.index.map(norm_dt)
                norm_entries[s] = ser_norm

            norm_exits = {}
            for s, ser in all_exit_reasons.items():
                ser_norm = ser.copy()
                ser_norm.index = ser_norm.index.map(norm_dt)
                norm_exits[s] = ser_norm

            def fmt_pct(v): return str(int(v)) if v == int(v) else str(v)

            for i, (idx_row, trade) in enumerate(vbt_trades.iterrows()):
                # 1. Symbol Identification
                sym_raw = trade.get('Column')
                if isinstance(sym_raw, tuple) and len(sym_raw) > 0: sym_raw = sym_raw[0]
                sym = str(sym_raw) if sym_raw is not None else None
                
                if sym is None or sym not in processed_symbols:
                    col_idx = trade.get('Column Idx')
                    if col_idx is not None:
                        try:
                            idx = int(col_idx)
                            if 0 <= idx < len(processed_symbols):
                                sym = processed_symbols[idx]
                        except: pass
                
                if sym is None or sym not in processed_symbols:
                    if len(processed_symbols) == 1: sym = processed_symbols[0]
                    else: sym = "unknown"
                
                # 2. Retrieve Trade Data
                e_idx = trade.get('Entry Timestamp', trade.get('Entry Index', trade.get('Entry Idx')))
                x_idx = trade.get('Exit Timestamp', trade.get('Exit Index', trade.get('Exit Idx')))
                e_price = cls.safe(trade.get('Avg Entry Price', trade.get('Entry Price')))
                x_price = cls.safe(trade.get('Avg Exit Price', trade.get('Exit Price')))
                size = cls.safe(trade.get('Size'))
                pnl = cls.safe(trade.get('PnL'))
                ret_val = cls.safe(trade.get('Return')) * 100
                
                exit_type = -1
                try:
                    raw_record = raw_records.iloc[i]
                    exit_type = int(raw_record['exit_type']) if 'exit_type' in raw_records.columns else -1
                except: pass

                # 3. Entry Reason Mapping
                e_reason = "매수 조건 충족 (전략 시그널)"
                try:
                    sym_reasons = get_reasons_for_sym(sym, norm_entries, processed_symbols)
                    if sym_reasons is not None:
                        target_norm = norm_dt(e_idx)
                        lookup_dt = target_norm
                        if exec_type == 'next_open':
                            prev_dates = sym_reasons.index[sym_reasons.index < target_norm]
                            if not prev_dates.empty: lookup_dt = prev_dates[-1]
                        
                        if lookup_dt in sym_reasons.index:
                            res_val = sym_reasons[lookup_dt]
                            if res_val: e_reason = res_val
                        else:
                            potential = sym_reasons.index[(sym_reasons.index <= lookup_dt) & (sym_reasons.notna())]
                            if not potential.empty:
                                diff = (lookup_dt - potential[-1]).days
                                if diff <= 3:
                                    res_val = sym_reasons[potential[-1]]
                                    if res_val: e_reason = res_val
                except: pass

                final_qty = int(np.floor(size))
                if final_qty >= 1:
                    # Append Buy Signal
                    signals_list.append({
                        "date": get_dt_str(e_idx), "symbol": str(sym), "type": "buy",
                        "price": float(round(e_price)), "quantity": final_qty,
                        "amount": float(round(e_price) * final_qty), "condition": e_reason
                    })

                    # 4. Exit Reason Mapping
                    reason_kr = "전략 매도 조건 충족"
                    try:
                        c_idx_val = trade.get('Column Idx')
                        sym_reasons_x = get_reasons_for_sym(sym, norm_exits, processed_symbols, c_idx_val)
                        if sym_reasons_x is not None:
                            target_norm_x = norm_dt(x_idx)
                            lookup_dt_x = target_norm_x
                            if exec_type == 'next_open':
                                prev_dates_x = sym_reasons_x.index[sym_reasons_x.index < target_norm_x]
                                if not prev_dates_x.empty: lookup_dt_x = prev_dates_x[-1]
                            
                            if lookup_dt_x in sym_reasons_x.index:
                                res_val_x = sym_reasons_x[lookup_dt_x]
                                if res_val_x: reason_kr = res_val_x
                            else:
                                potential_x = sym_reasons_x.index[(sym_reasons_x.index <= lookup_dt_x) & (sym_reasons_x.notna())]
                                if not potential_x.empty:
                                    diff_x = (lookup_dt_x - potential_x[-1]).days
                                    if diff_x <= 3:
                                        res_val_x = sym_reasons_x[potential_x[-1]]
                                        if res_val_x: reason_kr = res_val_x
                    except: pass

                    # 5. Risk Management Overrides
                    duration = -1
                    try:
                        raw_record = raw_records.iloc[i]
                        duration = int(raw_record['exit_idx'] - raw_record['entry_idx'])
                    except: pass

                    if exit_type == 1: reason_kr = f"손절매 실행 (-{fmt_pct(sl_pct)}%)" if sl_pct > 0 else "손절매 실행"
                    elif exit_type == 2: reason_kr = f"트레일링 스탑 (-{fmt_pct(ts_pct)}%)" if ts_pct > 0 else "트레일링 스탑 실행"
                    elif exit_type == 3: reason_kr = f"익절매 실행 (+{fmt_pct(tp_pct)}%)" if tp_pct > 0 else "익절매 실행"
                    elif exit_type == 4: 
                        reason_kr = f"보유 기간 만료 ({duration}일 보유)" if duration > 0 else "보유 기간 만료"
                    else:
                        # Inference fallback for missing exit_type (VectorBT 0.28.2)
                        # Use a wider 2.0% tolerance to account for fees and execution timing (next open/slippage)
                        if sl_pct > 0 and abs(ret_val + sl_pct) < 2.0:
                            reason_kr = f"손절매 실행 (-{fmt_pct(sl_pct)}%)"
                        elif tp_pct > 0 and abs(ret_val - tp_pct) < 2.0:
                            reason_kr = f"익절매 실행 (+{fmt_pct(tp_pct)}%)"
                        elif ts_pct > 0 and pnl > 0 and (reason_kr == "전략 매도 조건 충족"):
                            # If no strategy signal found, and TS is set, and it's a winner, likely TSL
                            reason_kr = f"트레일링 스탑 실행 (-{fmt_pct(ts_pct)}%)"
                        elif max_hold > 0 and duration >= max_hold:
                            reason_kr = f"보유 기간 만료 ({duration}일 보유)"
                        elif (sl_pct > 0 or tp_pct > 0) and (reason_kr == "전략 매도 조건 충족") and (not (exit_type == 5 or get_dt_str(x_idx) == get_dt_str(common_index[-1]))):
                            # Final fallback: if no strategy signal, but risk params exist, label by PnL direction
                            if pnl < 0 and sl_pct > 0: reason_kr = f"손절매 실행 (-{fmt_pct(sl_pct)}%)"
                            elif pnl > 0 and tp_pct > 0: reason_kr = f"익절매 실행 (+{fmt_pct(tp_pct)}%)"
                    
                    if (exit_type == 5 or get_dt_str(x_idx) == get_dt_str(common_index[-1])):
                        if reason_kr == "전략 매도 조건 충족": reason_kr = "백테스트 종료"
                    
                    pnl_label = "수익" if pnl >= 0 else "손실"
                    # Append Sell Signal
                    signals_list.append({
                        "date": get_dt_str(x_idx), "symbol": str(sym), "type": "sell",
                        "price": float(round(x_price)), "quantity": final_qty,
                        "amount": float(round(x_price) * final_qty),
                        "condition": f"{reason_kr} [수익률: {ret_val:+.2f}%, {pnl_label}: {abs(pnl):,.0f}원]"
                    })

        signals_list.sort(key=lambda x: x['date'])

        # Aggregate Stats
        total_trades = len(pf.trades)
        win_count = len(pf.trades.winning)
        agg_win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
        
        avg_win = cls.safe(pf.trades.winning.pnl.mean())
        avg_loss = abs(cls.safe(pf.trades.losing.pnl.mean()))
        
        # New detailed stats
        max_consecutive_wins = int(cls.safe(pf.trades.winning_streak.max()))
        max_consecutive_losses = int(cls.safe(pf.trades.losing_streak.max()))
        
        r = avg_win / avg_loss if avg_loss > 0 else 0.0
        w = agg_win_rate / 100
        kelly = w - (1 - w) / r if r > 0 else 0.0

        per_asset_stats = {}
        if len(processed_symbols) > 0:
            returns = pf.total_return(group_by=False)
            counts = pf.trades.count(group_by=False)
            wins = pf.trades.win_rate(group_by=False)
            profits = pf.total_profit(group_by=False)
            cagrs = pf.annualized_return(group_by=False)
            mdds = pf.max_drawdown(group_by=False)

            def get_val(obj, i):
                if isinstance(obj, pd.Series):
                    return obj.iloc[i] if len(obj) > i else 0.0
                if isinstance(obj, (pd.Index, np.ndarray, list)):
                    return obj[i] if len(obj) > i else 0.0
                if isinstance(obj, pd.DataFrame):
                    return obj.iloc[:, i].iloc[0] if obj.shape[1] > i else 0.0
                return obj if i == 0 else 0.0

            for i, sym in enumerate(processed_symbols):
                per_asset_stats[sym] = {
                    "symbol": sym,
                    "totalReturn": cls.safe(get_val(returns, i)) * 100,
                    "trades": int(cls.safe(get_val(counts, i))),
                    "winRate": cls.safe(get_val(wins, i)) * 100,
                    "profit": cls.safe(get_val(profits, i)),
                    "cagr": cls.safe(get_val(cagrs, i)) * 100,
                    "maxDrawdown": cls.safe(get_val(mdds, i)) * 100
                }

        def to_list(obj):
            if isinstance(obj, (pd.DataFrame, pd.Series)):
                return np.nan_to_num(obj.values.flatten(), nan=0.0, posinf=0.0, neginf=0.0).tolist()
            return [cls.safe(x) for x in obj]

        def sanitize(v):
            if isinstance(v, dict): return {k: sanitize(item) for k, item in v.items()}
            if isinstance(v, list): return [sanitize(item) for item in v]
            if isinstance(v, float):
                if np.isnan(v) or np.isinf(v): return 0.0
                return v
            return v

        bench_rets = pf.benchmark_returns()
        if isinstance(bench_rets, pd.DataFrame): bench_mean_rets = bench_rets.mean(axis=1)
        else: bench_mean_rets = bench_rets

        # Calculate compounded benchmark return
        bench_cum_returns = (1 + bench_mean_rets).cumprod()
        bench_total_return = bench_cum_returns.iloc[-1] - 1 if len(bench_cum_returns) > 0 else 0.0

        # Manual CAGR: for sub-1Y periods, just use total return (no annualization)
        total_return_decimal = cls.safe(pf.total_return())
        n_days = len(common_index)
        n_years = n_days / 252.0
        if n_years >= 1.0 and total_return_decimal > -1:
            cagr_val = ((1 + total_return_decimal) ** (1 / n_years) - 1) * 100
        else:
            # For sub-1Y: CAGR = Total Return (no extrapolation)
            cagr_val = total_return_decimal * 100
        
        # Profit Factor: detect buy-and-hold-to-end scenario
        # If all trades exit on the last day, PF by individual trades is misleading.
        raw_pf = cls.safe(pf.trades.profit_factor())
        
        # Check if this is a buy-and-hold pattern (most trades span nearly the full period)
        last_date = common_index[-1] if len(common_index) > 0 else None
        is_buy_and_hold = False
        if total_trades > 0 and total_trades <= 30 and len(pf.trades.records) > 0:
            try:
                recs = pf.trades.records
                # A trade is "full-period" if it exits within 5 days of the last bar
                last_bar = n_days - 1
                full_period_trades = sum(1 for r in recs if (last_bar - int(r['exit_idx'])) <= 5)
                if full_period_trades >= total_trades * 0.7:  # 70%+ held to end
                    is_buy_and_hold = True
            except:
                pass
        
        if is_buy_and_hold:
            # For buy-and-hold: use aggregate profit/loss ratio
            try:
                total_profit = sum(float(r['pnl']) for r in pf.trades.records if float(r['pnl']) > 0)
                total_loss = abs(sum(float(r['pnl']) for r in pf.trades.records if float(r['pnl']) < 0))
                raw_pf = total_profit / total_loss if total_loss > 0 else 0.0
            except:
                pass
        
        # Final cap: never show PF > 10 for < 30 trades
        if total_trades < 30 and raw_pf > 10.0:
            raw_pf = min(raw_pf, 10.0)

        res = {
            "symbols": processed_symbols,
            "totalReturn": cls.safe(pf.total_return()) * 100,
            "cagr": cagr_val,
            "buyAndHoldReturn": cls.safe(bench_total_return) * 100,
            "maxDrawdown": cls.safe(pf.max_drawdown()) * 100,
            "winRate": agg_win_rate,
            "trades": total_trades,
            "avgProfit": avg_win,
            "avgLoss": avg_loss,
            "maxConsecutiveWins": max_consecutive_wins,
            "maxConsecutiveLosses": max_consecutive_losses,
            "profitFactor": raw_pf,
            "sharpe": cls.safe(pf.sharpe_ratio()),
            "sortino": cls.safe(pf.sortino_ratio()),
            "kelly": cls.safe(kelly),
            "volatility": cls.safe(pf.returns().std() * np.sqrt(252)) * 100,
            "equity": to_list(pf.value()),
            "benchmark_equity": to_list(init_cash * bench_cum_returns),
            "dates": [d.strftime('%Y-%m-%d') for d in common_index],
            "signals": signals_list,
            "perAssetStats": per_asset_stats,
            "warnings": list(getattr(cls, '_warnings', set())),
            "version": "6.4 (Fixed CAGR + PF Cap)"
        }

        return sanitize(res)
