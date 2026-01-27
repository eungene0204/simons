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

        if len(pf.trades.records) > 0:
            vbt_trades = pf.trades.records_readable
            raw_records = pf.trades.records

            for i, (idx_row, trade) in enumerate(vbt_trades.iterrows()):
                sym = trade.get('Column')
                if sym is None:
                    col_idx = trade.get('Column Idx', 0)
                    sym = processed_symbols[int(col_idx)]
                
                e_idx = trade.get('Entry Index', trade.get('Entry Idx', trade.get('Entry Timestamp')))
                x_idx = trade.get('Exit Index', trade.get('Exit Idx', trade.get('Exit Timestamp')))

                e_price = cls.safe(trade.get('Entry Price', trade.get('Avg Entry Price')))
                x_price = cls.safe(trade.get('Exit Price', trade.get('Avg Exit Price')))
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

                # Entry Logic
                e_reason = "매수 조건 충족 (전략 시그널)"
                try:
                    sym_dates = [d.strftime('%Y-%m-%d') for d in all_entries[sym].index]
                    dt_s = get_dt_str(e_idx)
                    if dt_s in sym_dates:
                        idx_in_sym = sym_dates.index(dt_s)
                        p_idx = idx_in_sym - 1 if exec_type == 'next_open' and idx_in_sym > 0 else idx_in_sym
                        if all_entry_reasons[sym][p_idx]:
                            e_reason = all_entry_reasons[sym][p_idx]
                except: pass

                final_qty = int(np.floor(size))
                if final_qty >= 1:
                    signals_list.append({
                        "date": get_dt_str(e_idx), "symbol": str(sym), "type": "buy",
                        "price": float(round(e_price)), "quantity": final_qty,
                        "amount": float(round(e_price) * final_qty), "condition": e_reason
                    })

                    # Exit Logic
                    reason_kr = "전략 청산 시그널"
                    try:
                        sym_dates_x = [d.strftime('%Y-%m-%d') for d in all_exits[sym].index]
                        dt_sx = get_dt_str(x_idx)
                        if dt_sx in sym_dates_x:
                            idx_in_sym = sym_dates_x.index(dt_sx)
                            p_idx = idx_in_sym - 1 if exec_type == 'next_open' and idx_in_sym > 0 else idx_in_sym
                            if p_idx >= 0 and p_idx < len(all_exit_reasons[sym]) and all_exit_reasons[sym][p_idx]:
                                reason_kr = all_exit_reasons[sym][p_idx]
                    except: pass

                    def fmt_pct(v): return str(int(v)) if v == int(v) else str(v)
                    if exit_type > 0:
                        if exit_type in [1, 5]: reason_kr = f"손절매 실행 (-{fmt_pct(sl_pct)}%)" if sl_pct > 0 else "손절매 실행"
                        elif exit_type == 2: reason_kr = f"트레일링 스탑 (-{fmt_pct(ts_pct)}%)" if ts_pct > 0 else "트레일링 스탑 실행"
                        elif exit_type == 3: reason_kr = f"익절매 실행 (+{fmt_pct(tp_pct)}%)" if tp_pct > 0 else "익절매 실행"
                        elif exit_type == 4: reason_kr = "보유 기간 만료 (강제 청산)"
                    
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
            returns = pf.total_return()
            counts = pf.trades.count()
            wins = pf.trades.win_rate()
            profits = pf.total_profit()
            for i, sym in enumerate(processed_symbols):
                idx = i if len(processed_symbols) > 1 else None
                per_asset_stats[sym] = {
                    "symbol": sym,
                    "totalReturn": cls.safe(returns.iloc[i] if idx is not None else returns) * 100,
                    "trades": int(cls.safe(counts.iloc[i] if idx is not None else counts)),
                    "winRate": cls.safe(wins.iloc[i] if idx is not None else wins) * 100,
                    "profit": cls.safe(profits.iloc[i] if idx is not None else profits)
                }

        def to_list(obj):
            if isinstance(obj, pd.DataFrame): return obj.iloc[:, 0].tolist()
            if isinstance(obj, pd.Series): return obj.tolist()
            return list(obj)

        return {
            "symbols": processed_symbols,
            "totalReturn": cls.safe(pf.total_return()) * 100,
            "cagr": cls.safe(pf.annualized_return()) * 100,
            "buyAndHoldReturn": cls.safe(pf.benchmark_returns().sum().mean()) * 100,
            "maxDrawdown": cls.safe(pf.max_drawdown()) * 100,
            "winRate": agg_win_rate,
            "trades": total_trades,
            "profitFactor": cls.safe(pf.trades.profit_factor()),
            "sharpe": cls.safe(pf.sharpe_ratio()),
            "sortino": cls.safe(pf.sortino_ratio()),
            "kelly": cls.safe(kelly),
            "volatility": cls.safe(pf.returns().std() * np.sqrt(252)) * 100,
            "equity": to_list(pf.value()),
            "benchmark_equity": to_list(init_cash * (1 + pf.benchmark_returns().mean(axis=1).cumsum())),
            "dates": [d.strftime('%Y-%m-%d') for d in common_index],
            "signals": signals_list,
            "perAssetStats": per_asset_stats,
            "version": "6.0 (Refactored)"
        }
