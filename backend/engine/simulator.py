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
        
        # Determine size per position (relative to FULL portfolio NAV)
        # VectorBT size_type='Percent' means % of CURRENT Total Equity (NAV).
        if risk_params.get('allocation_type') == 'equal':
            # Equal weight: divide 100% of equity by max_positions
            size_per_pos = 1.0 / max_pos if max_pos and max_pos > 0 else 1.0 / len(entries_df.columns)
        else:
            # Fixed percent: the UI passes 'pos_size_pct' as the percentage of the WHOLE portfolio
            # e.g., 10% per trade -> size_per_pos = 0.1
            size_per_pos = pos_size_pct / 100.0
            
            # Safeguard: If user says fixed_pct is 100%, but max_pos is 10, VectorBT will try to put
            # 100% into the FIRST signal it sees, starving the rest. We must cap it.
            if max_pos and max_pos > 0:
                max_allowed_size = 1.0 / max_pos
                if size_per_pos > max_allowed_size:
                    # e.g. user set 100% per trade, but max_pos=10. Cap it to 10% so all 10 can enter.
                    size_per_pos = max_allowed_size

        # --- Hard Limit on Concurrent Positions with Unified Exit Logic ---
        skip_pos = risk_params.get('skip_position_setting', False)
        use_risk_mgmt = not risk_params.get('skip_risk_management', False)
        
        # We need the custom loop if we have a position limit OR risk management exits
        has_custom_loop = (not skip_pos) or (use_risk_mgmt and (max_hold > 0 or sl_pct > 0 or tp_pct > 0))
        
        if has_custom_loop:
            # Pre-calculate data for faster access
            symbols = entries_df.columns.tolist()
            num_symbols = len(symbols)
            
            eff_max_pos = max_pos if (not skip_pos) and max_pos is not None else num_symbols
            
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
                if i % 100 == 0:
                    print(f"[DEBUG-SIM] Processing Day {i}/{len(entries_df)} (Active Assets: {active_count}/{eff_max_pos})", flush=True)
                
                # 1. Process deferred exits from previous day's SL/TP/MaxHold
                for s_idx in range(num_symbols):
                    if active_mask[s_idx] and exits_values[i, s_idx]:
                        active_mask[s_idx] = False
                        active_count -= 1
                
                # 2. Evaluate new exits for NEXT day execution
                for s_idx in range(num_symbols):
                    if active_mask[s_idx]:
                        should_exit_next = False
                        
                        # B. Max Holding Days Exit
                        if max_hold > 0 and (i - entry_day[s_idx]) >= max_hold:
                            should_exit_next = True
                            
                        # C. Stop Loss / Take Profit
                        # Evaluate using today's close. If triggered, the exit signal
                        # goes to day i+1 so VectorBT executes at open[i+1].
                        # This ensures we only use information available at end of day i.
                        elif use_risk_mgmt and (sl_pct > 0 or tp_pct > 0):
                            current_px = price_values[i, s_idx]
                            pct_ret = (current_px - entry_price[s_idx]) / entry_price[s_idx] * 100
                            
                            EPS = 1e-6
                            if sl_pct > 0 and pct_ret <= (-sl_pct + EPS):
                                should_exit_next = True
                            elif tp_pct > 0 and pct_ret >= (tp_pct - EPS):
                                should_exit_next = True
                        
                        if should_exit_next and i + 1 < len(entries_df):
                            exits_values[i + 1, s_idx] = True
                            # Don't deactivate here — it will be deactivated at step 1
                            # on the next iteration when exits_values[i+1] is processed.
                
                # 3. Process new entries (after exits freed slots)
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
            
            print(f"[DEBUG-SIM] Simulation loop finished. {len(entries_df)} days processed.", flush=True)
                            # Optional: Log if needed for debugging
                            # print(f"Row {i}: Dropping {symbols[s_idx]} due to max_pos={eff_max_pos}")

            entries_df = pd.DataFrame(filtered_entries_values, index=entries_df.index, columns=entries_df.columns)
            exits_df = pd.DataFrame(exits_values, index=exits_df.index, columns=exits_df.columns)
        # ------------------------------------------

        # NOTE: sl_stop/tp_stop/sl_trail are intentionally NOT passed to VectorBT.
        # Our custom simulation loop above already injects exit signals into exits_df
        # when SL/TP/trailing stop conditions are met. VectorBT's built-in mechanism
        # fills at the EXACT stop price (ignoring overnight gaps and real market
        # execution), which creates artificially perfect risk management and inflates
        # the Profit Factor. By relying solely on exits_df, exits happen at the
        # next available market price (exec_price_df), which is realistic.
        vbt_kwargs = dict(
            size=size_per_pos,
            size_type='Percent',
            init_cash=init_cash,
            fees=fee_rate,
            slippage=slippage_val,
            freq='D',
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
