import vectorbt as vbt
import pandas as pd
from typing import Dict, Any, Optional

class Simulator:
    def run(self,
            price_df: pd.DataFrame, 
            exec_price_df: pd.DataFrame, 
            entries_df: pd.DataFrame, 
            exits_df: pd.DataFrame, 
            risk_params: Dict[str, Any],
            options: Dict[str, Any],
            rank_df: Optional[pd.DataFrame] = None) -> vbt.Portfolio:
        
        # 1. Copy Signal Inputs to avoid side effects
        entries_df = entries_df.copy()
        exits_df = exits_df.copy()
        
        init_cash = float(risk_params.get('init_cash') or 10000000.0)
        pos_size_pct = float(risk_params.get('position_size_pct') or 100.0)
        max_pos = risk_params.get('max_positions')
        
        sl_pct = float(risk_params.get('stop_loss_pct') or 0)
        tp_pct = float(risk_params.get('take_profit_pct') or 0)
        ts_pct = float(risk_params.get('trailing_stop_pct') or 0)
        max_hold = int(risk_params.get('max_holding_days') or 0)
        
        fee_rate = float(options.get('fee_rate') or 0.0015)
        slippage_val = float(options.get('slippage_rate') or 0.0020)
        
        # Determine size per position
        if risk_params.get('allocation_type') == 'equal':
            size_per_pos = 1.0 / max_pos if max_pos and max_pos > 0 else 0.1
        else:
            size_per_pos = pos_size_pct / 100.0

        # --- Hard Limit on Concurrent Positions with Unified Exit Logic ---
        has_risk = max_pos is not None or max_hold > 0 or sl_pct > 0 or tp_pct > 0
        if has_risk:
            eff_max_pos = max_pos if max_pos is not None else entries_df.shape[1]
            filtered_entries = entries_df.copy()
            active_count = 0
            is_active = {sym: False for sym in entries_df.columns}
            entry_day = {sym: -1 for sym in entries_df.columns}
            entry_price = {sym: 0.0 for sym in entries_df.columns}
            
            for i in range(len(entries_df)):
                # 1. Update exits (free up slots)
                for sym_idx, sym in enumerate(entries_df.columns):
                    if is_active[sym]:
                        should_exit = False
                        
                        # A. Strategy Exit Signal (Already in exits_df)
                        if exits_df.iloc[i][sym]:
                            should_exit = True
                        
                        # B. Max Holding Days Exit
                        elif max_hold > 0 and (i - entry_day[sym]) >= max_hold:
                            should_exit = True
                            exits_df.iloc[i, sym_idx] = True # Record the exit
                            
                        # C. Stop Loss / Take Profit Approximation
                        elif sl_pct > 0 or tp_pct > 0:
                            current_price = price_df.iloc[i][sym]
                            pct_ret = (current_price - entry_price[sym]) / entry_price[sym] * 100
                            
                            if sl_pct > 0 and pct_ret <= -sl_pct:
                                should_exit = True
                                exits_df.iloc[i, sym_idx] = True
                            elif tp_pct > 0 and pct_ret >= tp_pct:
                                should_exit = True
                                exits_df.iloc[i, sym_idx] = True
                        
                        if should_exit:
                            is_active[sym] = False
                            active_count -= 1
                
                # 2. Process new entries (Prioritized by rank if available)
                today_entries = entries_df.iloc[i]
                candidates = today_entries.index[today_entries].tolist()
                
                if rank_df is not None and len(candidates) > 1:
                    today_ranks = rank_df.iloc[i]
                    candidates.sort(key=lambda s: today_ranks.get(s, 0.0), reverse=True)
                
                for sym in candidates:
                    if not is_active[sym]:
                        if active_count < eff_max_pos:
                            is_active[sym] = True
                            active_count += 1
                            entry_day[sym] = i
                            entry_price[sym] = exec_price_df.iloc[i][sym]
                        else:
                            # Block this entry
                            filtered_entries.iloc[i, filtered_entries.columns.get_loc(sym)] = False
            entries_df = filtered_entries
        # ------------------------------------------

        vbt_kwargs = dict(
            size=size_per_pos,
            size_type='Percent',
            init_cash=init_cash,
            fees=fee_rate,
            slippage=slippage_val,
            freq='D',
            sl_stop=sl_pct / 100 if sl_pct > 0 else None,
            tp_stop=tp_pct / 100 if tp_pct > 0 else None,
            sl_trail=ts_pct / 100 if ts_pct > 0 else None,
            allow_partial=False,
            direction='longonly',
            accumulate=False,
            group_by=True,
            cash_sharing=True
        )

        pf = vbt.Portfolio.from_signals(
            close=price_df, 
            price=exec_price_df,
            entries=entries_df, 
            exits=exits_df,
            **vbt_kwargs
        )
        
        return pf
