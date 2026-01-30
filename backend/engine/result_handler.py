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

            for i, (idx_row, trade) in enumerate(vbt_trades.iterrows()):
                # Improved symbol identification: vectorbt usually puts symbol in 'Column' for multi-col
                # It can be a string or an object depending on vbt version
                sym_raw = trade.get('Column')
                sym = str(sym_raw) if sym_raw is not None else None
                
                if sym is None or sym not in processed_symbols:
                    # Fallback to Column Idx if Column name is missing or mismatched
                    col_idx = trade.get('Column Idx')
                    if col_idx is not None:
                        try:
                            idx = int(col_idx)
                            if 0 <= idx < len(processed_symbols):
                                sym = processed_symbols[idx]
                        except (IndexError, ValueError):
                            pass
                
                # If still None, it's likely a single asset backtest, so default to the first
                if sym is None:
                    if len(processed_symbols) == 1:
                        sym = processed_symbols[0]
                    else:
                        sym = "unknown"
                        print(f"[DEBUG] ResultHandler: Could not identify symbol for trade {i}. Column={trade.get('Column')}, Idx={trade.get('Column Idx')}")
                
                # Robust timestamp retrieval
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

                def get_dt_str(ts):
                    if isinstance(ts, (pd.Timestamp, datetime)): return ts.strftime('%Y-%m-%d')
                    return str(ts)

                # Entry Reason Mapping: Match by timestamp for absolute accuracy
                e_reason = "매수 조건 충족 (전략 시그널)"
                try:
                    # Use the identified 'sym' to get the correct reasons
                    if sym in all_entries and sym in all_entry_reasons:
                        target_dt = pd.to_datetime(e_idx)
                        sym_series = all_entries[sym]
                        
                        if target_dt in sym_series.index:
                            idx_in_sym = sym_series.index.get_loc(target_dt)
                            # Shift for next_open
                            p_idx = idx_in_sym - 1 if exec_type == 'next_open' and idx_in_sym > 0 else idx_in_sym
                            
                            reasons = all_entry_reasons[sym]
                            if 0 <= p_idx < len(reasons) and reasons[p_idx]:
                                e_reason = reasons[p_idx]
                except Exception as ex:
                    print(f"[DEBUG] Entry reason mapping failed for {sym} at {e_idx}: {str(ex)}")

                final_qty = int(np.floor(size))
                if final_qty >= 1:
                    signals_list.append({
                        "date": get_dt_str(e_idx), "symbol": str(sym), "type": "buy",
                        "price": float(round(e_price)), "quantity": final_qty,
                        "amount": float(round(e_price) * final_qty), "condition": e_reason
                    })

                    # Exit Reason Mapping
                    reason_kr = "전략 청산 시그널"
                    try:
                        if sym in all_exits and sym in all_exit_reasons:
                            target_dt_x = pd.to_datetime(x_idx)
                            sym_series_x = all_exits[sym]
                            
                            if target_dt_x in sym_series_x.index:
                                idx_in_sym_x = sym_series_x.index.get_loc(target_dt_x)
                                
                                # For 'next_open', the trade happens on the day AFTER the signal.
                                # The reason we want is from the day the signal was generated.
                                p_idx_x = idx_in_sym_x - 1 if exec_type == 'next_open' and idx_in_sym_x > 0 else idx_in_sym_x
                                
                                reasons_x = all_exit_reasons[sym]
                                if 0 <= p_idx_x < len(reasons_x) and reasons_x[p_idx_x]:
                                    reason_kr = reasons_x[p_idx_x]
                                    print(f"[DEBUG] Found specific exit reason: {reason_kr} for {sym} at {x_idx}")
                    except Exception as ex:
                        print(f"[DEBUG] Exit reason mapping failed for {sym} at {x_idx}: {str(ex)}")

                    def fmt_pct(v): return str(int(v)) if v == int(v) else str(v)
                    
                    # vectorbt exit_type mapping: 0:Signal, 1:SL, 2:TSL, 3:TP, 4:Time, 5:EndOfLife/Simulation
                    # If it's a specific exit type from risk management, override the generic reason
                    if exit_type == 1: reason_kr = f"손절매 실행 (-{fmt_pct(sl_pct)}%)" if sl_pct > 0 else "손절매 실행"
                    elif exit_type == 2: reason_kr = f"트레일링 스탑 (-{fmt_pct(ts_pct)}%)" if ts_pct > 0 else "트레일링 스탑 실행"
                    elif exit_type == 3: reason_kr = f"익절매 실행 (+{fmt_pct(tp_pct)}%)" if tp_pct > 0 else "익절매 실행"
                    elif exit_type == 4: reason_kr = "보유 기간 만료 (강제 청산)"
                    elif (exit_type == 0 or exit_type == -1) and max_hold > 0:
                        try:
                            # Fallback for manual time-exits added to exits_df
                            raw_record = raw_records.iloc[i]
                            # records usually has entry_idx and exit_idx
                            duration = int(raw_record['exit_idx'] - raw_record['entry_idx'])
                            if duration >= max_hold:
                                reason_kr = "보유 기간 만료 (강제 청산)"
                        except: pass

                    if exit_type == 5 or get_dt_str(x_idx) == get_dt_str(common_index[-1]):
                        # Only label as "백테스트 종료" if we haven't found a specific reason from signals
                        if reason_kr == "전략 청산 시그널":
                            reason_kr = "백테스트 종료 (강제 청산)"
                    
                    pnl_label = "수익" if pnl >= 0 else "손실"
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
        r = avg_win / avg_loss if avg_loss > 0 else 0.0
        w = agg_win_rate / 100
        kelly = w - (1 - w) / r if r > 0 else 0.0

        per_asset_stats = {}
        if len(processed_symbols) > 0:
            # We use group_by=False to get individual asset stats from the grouped portfolio
            returns = pf.total_return(group_by=False)
            counts = pf.trades.count(group_by=False)
            wins = pf.trades.win_rate(group_by=False)
            profits = pf.total_profit(group_by=False)
            cagrs = pf.annualized_return(group_by=False)
            mdds = pf.max_drawdown(group_by=False)

            for i, sym in enumerate(processed_symbols):
                # When using group_by=False on a grouped Portfolio, it returns a Series with original columns
                per_asset_stats[sym] = {
                    "symbol": sym,
                    "totalReturn": cls.safe(returns.iloc[i] if len(returns) > i else 0.0) * 100,
                    "trades": int(cls.safe(counts.iloc[i] if len(counts) > i else 0.0)),
                    "winRate": cls.safe(wins.iloc[i] if len(wins) > i else 0.0) * 100,
                    "profit": cls.safe(profits.iloc[i] if len(profits) > i else 0.0),
                    "cagr": cls.safe(cagrs.iloc[i] if len(cagrs) > i else 0.0) * 100,
                    "maxDrawdown": cls.safe(mdds.iloc[i] if len(mdds) > i else 0.0) * 100
                }

        def to_list(obj):
            if isinstance(obj, (pd.DataFrame, pd.Series)):
                # Convert to numpy, replace NaN/Inf with 0.0, then to list
                return np.nan_to_num(obj.values.flatten(), nan=0.0, posinf=0.0, neginf=0.0).tolist()
            return [cls.safe(x) for x in obj]

        def sanitize(v):
            if isinstance(v, dict): return {k: sanitize(item) for k, item in v.items()}
            if isinstance(v, list): return [sanitize(item) for item in v]
            if isinstance(v, float):
                if np.isnan(v) or np.isinf(v): return 0.0
                return v
            return v

        # Calculate Benchmark properly for both Series (grouped) and DataFrame (individual)
        bench_rets = pf.benchmark_returns()
        if isinstance(bench_rets, pd.DataFrame):
            bench_mean_rets = bench_rets.mean(axis=1)
        else:
            bench_mean_rets = bench_rets

        res = {
            "symbols": processed_symbols,
            "totalReturn": cls.safe(pf.total_return()) * 100,
            "cagr": cls.safe(pf.annualized_return()) * 100,
            "buyAndHoldReturn": cls.safe(bench_mean_rets.sum()) * 100,
            "maxDrawdown": cls.safe(pf.max_drawdown()) * 100,
            "winRate": agg_win_rate,
            "trades": total_trades,
            "profitFactor": cls.safe(pf.trades.profit_factor()),
            "sharpe": cls.safe(pf.sharpe_ratio()),
            "sortino": cls.safe(pf.sortino_ratio()),
            "kelly": cls.safe(kelly),
            "volatility": cls.safe(pf.returns().std() * np.sqrt(252)) * 100,
            "equity": to_list(pf.value()),
            "benchmark_equity": to_list(init_cash * (1 + bench_mean_rets.cumsum())),
            "dates": [d.strftime('%Y-%m-%d') for d in common_index],
            "signals": signals_list,
            "perAssetStats": per_asset_stats,
            "version": "6.1 (Sanitized)"
        }
        return sanitize(res)
