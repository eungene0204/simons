import vectorbt as vbt
import pandas as pd
from typing import Dict, Any

class Simulator:
    @staticmethod
    def run(price_df: pd.DataFrame, 
            exec_price_df: pd.DataFrame, 
            entries_df: pd.DataFrame, 
            exits_df: pd.DataFrame, 
            risk_params: Dict[str, Any],
            options: Dict[str, Any]) -> vbt.Portfolio:
        
        # 1. Copy Signal Inputs to avoid side effects
        entries_df = entries_df.copy()
        exits_df = exits_df.copy()
        
        # 2. Merge Max Holding Days into exits (Needs to be done before pre-filtering)
        max_hold = int(risk_params.get('max_holding_days') or 0)
        if max_hold > 0:
            for col in entries_df.columns:
                # Signal an exit N days after each entry
                # shift(N) maps entry at T to exit signal at T+N
                time_exits = entries_df[col].shift(max_hold).fillna(False).astype(bool)
                exits_df[col] = exits_df[col] | time_exits

        init_cash = float(risk_params.get('init_cash') or 10000000.0)
        pos_size_pct = float(risk_params.get('position_size_pct') or 100.0)
        max_pos = risk_params.get('max_positions')
        
        sl_pct = float(risk_params.get('stop_loss_pct') or 0)
        tp_pct = float(risk_params.get('take_profit_pct') or 0)
        ts_pct = float(risk_params.get('trailing_stop_pct') or 0)
        
        fee_rate = float(options.get('fee_rate') or 0.0015)
        slippage_val = float(options.get('slippage_rate') or 0.0020)
        
        # Determine size per position
        # For equal weight, we force it to 1/N to use cash as a natural limit
        if risk_params.get('allocation_type') == 'equal':
            size_per_pos = 1.0 / max_pos if max_pos and max_pos > 0 else 0.1
        else:
            size_per_pos = pos_size_pct / 100.0

        # --- Hard Limit on Concurrent Positions ---
        # Since vectorbt only limits by cash, we pre-filter signals to honor max_pos count
        # This is strictly for cross-asset count limiting.
        if max_pos is not None and max_pos < entries_df.shape[1]:
            filtered_entries = entries_df.copy()
            active_count = 0
            # Track active status per symbol
            is_active = {sym: False for sym in entries_df.columns}
            
            for i in range(len(entries_df)):
                # 1. Update exits (free up slots)
                for sym in entries_df.columns:
                    if is_active[sym] and exits_df.iloc[i][sym]:
                        is_active[sym] = False
                        active_count -= 1
                
                # 2. Process new entries
                today_entries = entries_df.iloc[i]
                for sym in today_entries.index:
                    if today_entries[sym] and not is_active[sym]:
                        if active_count < max_pos:
                            is_active[sym] = True
                            active_count += 1
                        else:
                            # Block this entry as we've hit the count limit
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
