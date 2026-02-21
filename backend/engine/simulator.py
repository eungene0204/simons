import vectorbt as vbt
import pandas as pd
import numpy as np
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
            
            # Pre-calculate data for faster access
            symbols = entries_df.columns.tolist()
            num_symbols = len(symbols)
            price_values = price_df.values
            exec_price_values = exec_price_df.values
            entries_values = entries_df.values
            exits_values = exits_df.values.copy()
            
            filtered_entries_values = entries_values.copy()
            active_mask = np.zeros(num_symbols, dtype=bool)
            entry_day = np.full(num_symbols, -1)
            entry_price = np.zeros(num_symbols)
            active_count = 0
            
            for i in range(len(entries_df)):
                # 1. Update exits (free up slots)
                for s_idx in range(num_symbols):
                    if active_mask[s_idx]:
                        should_exit = False
                        
                        # A. Strategy Exit Signal
                        if exits_values[i, s_idx]:
                            should_exit = True
                        
                        # B. Max Holding Days Exit
                        elif max_hold > 0 and (i - entry_day[s_idx]) >= max_hold:
                            should_exit = True
                            exits_values[i, s_idx] = True
                            
                        # C. Stop Loss / Take Profit
                        elif sl_pct > 0 or tp_pct > 0:
                            current_px = price_values[i, s_idx]
                            pct_ret = (current_px - entry_price[s_idx]) / entry_price[s_idx] * 100
                            
                            if sl_pct > 0 and pct_ret <= -sl_pct:
                                should_exit = True
                                exits_values[i, s_idx] = True
                            elif tp_pct > 0 and pct_ret >= tp_pct:
                                should_exit = True
                                exits_values[i, s_idx] = True
                        
                        if should_exit:
                            active_mask[s_idx] = False
                            active_count -= 1
                
                # 2. Process new entries
                today_ents = entries_values[i]
                candidate_indices = np.where(today_ents & ~active_mask)[0]
                
                if len(candidate_indices) > 0:
                    if rank_df is not None:
                        today_ranks = rank_df.iloc[i].values
                        # Sort by rank descending
                        candidate_indices = candidate_indices[np.argsort(-today_ranks[candidate_indices])]
                    
                    for s_idx in candidate_indices:
                        if active_count < eff_max_pos:
                            active_mask[s_idx] = True
                            active_count += 1
                            entry_day[s_idx] = i
                            entry_price[s_idx] = exec_price_values[i, s_idx]
                        else:
                            filtered_entries_values[i, s_idx] = False

            entries_df = pd.DataFrame(filtered_entries_values, index=entries_df.index, columns=entries_df.columns)
            exits_df = pd.DataFrame(exits_values, index=exits_df.index, columns=exits_df.columns)
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
